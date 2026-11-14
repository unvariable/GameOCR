"""Global sistem kısayolları dinleyicisi.

Linux masaüstlerinde tam ekran Proton/Steam oyunları dahil olmak üzere sistem
genelinde basılan kısayolları (Duraklat, ROI Seç, Overlay Göster/Gizle, Geçmiş) yakalar.

Çift katmanlı (dual-layer) mimari:
1. KDE Plasma 6 (Wayland): `~/.local/share/applications/` altındaki komut kısayolları
   ve `kglobalshortcutsrc` aracılığıyla KWin kompozitör seviyesinde yakalanır, yerel
   UDP soketi üzerinden (<0.1 ms) uygulamayı anında tetikler.
2. X11 / XWayland: `python-xlib` ile `root.grab_key` dinler. NumLock, CapsLock ve AltGr
   (ISO_Level3_Shift) kombinasyonlarının tamamını kapsar ve `select.select` ile gecikmesiz çalışır.
"""
from __future__ import annotations

import logging
import os
import select
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from ..config import HotkeysConfig

log = logging.getLogger(__name__)

UDP_PORT = 49281
SIGNIFICANT_MODS = 0x4D  # ControlMask (0x4) | Mod1Mask/Alt (0x8) | ShiftMask (0x1) | Mod4Mask/Super (0x40)


def _get_lock_combos(X: any) -> list[int]:
    """NumLock (Mod2), CapsLock (Lock) ve AltGr (Mod5) varyasyonları."""
    combos = [0]
    extras = [X.Mod2Mask, X.LockMask, X.Mod5Mask]
    for m in extras:
        combos += [c | m for c in list(combos)]
    return list(set(combos))


def _parse_win32_shortcut(text: str) -> tuple[int, int] | None:
    """Windows `RegisterHotKey` için (fsModifiers, vk) çiftini ayrıştırır."""
    if not text or not text.strip():
        return None
    MOD_ALT = 0x0001
    MOD_CONTROL = 0x0002
    MOD_SHIFT = 0x0004
    MOD_WIN = 0x0008

    parts = [p.strip().lower() for p in text.split("+") if p.strip()]
    mods = 0
    key_name = ""
    for p in parts:
        if p in ("ctrl", "control"):
            mods |= MOD_CONTROL
        elif p in ("alt", "mod1"):
            mods |= MOD_ALT
        elif p in ("shift",):
            mods |= MOD_SHIFT
        elif p in ("super", "meta", "win", "mod4"):
            mods |= MOD_WIN
        else:
            key_name = p.upper()

    if not key_name:
        return None
    if len(key_name) == 1 and key_name.isalnum():
        return mods, ord(key_name)
    if key_name.startswith("F") and key_name[1:].isdigit():
        fn = int(key_name[1:])
        if 1 <= fn <= 24:
            return mods, 0x70 + (fn - 1)
    return None


def _parse_xlib_shortcut(d: any, text: str) -> tuple[int, int] | None:
    """X11 tuş kombinasyonunu ayrıştırır."""
    from Xlib import X, XK

    if not text or not text.strip():
        return None

    parts = [p.strip().lower() for p in text.split("+")]
    mask = 0
    key_name = ""

    for p in parts:
        if p in ("ctrl", "control"):
            mask |= X.ControlMask
        elif p in ("alt", "mod1"):
            mask |= X.Mod1Mask
        elif p in ("shift",):
            mask |= X.ShiftMask
        elif p in ("super", "meta", "win", "mod4"):
            mask |= X.Mod4Mask
        else:
            key_name = p

    if not key_name:
        return None

    keysym = (
        XK.string_to_keysym(key_name)
        or XK.string_to_keysym(key_name.upper())
        or XK.string_to_keysym(key_name.capitalize())
    )
    if not keysym:
        return None

    keycode = d.keysym_to_keycode(keysym)
    if not keycode:
        return None

    return keycode, mask


def _sync_kde_command_shortcuts(cfg: HotkeysConfig) -> None:
    """KDE Plasma 6 KWin global komut kısayollarını senkronize eder."""
    home = Path.home()
    bin_dir = home / ".local" / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    trigger_script = bin_dir / "gameocr-trigger"

    # Tetikleyici script'i oluştur
    trigger_content = (
        "#!/bin/sh\n"
        f'python3 -c "import socket; s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); '
        f's.sendto(b\'$1\', (\'127.0.0.1\', {UDP_PORT}))" 2>/dev/null || true\n'
    )
    try:
        trigger_script.write_text(trigger_content)
        trigger_script.chmod(0o755)
    except Exception as exc:
        log.debug("gameocr-trigger oluşturulamadı: %s", exc)

    apps_dir = home / ".local" / "share" / "applications"
    apps_dir.mkdir(parents=True, exist_ok=True)

    action_map = {
        "pause": ("Duraklat / Devam Et", cfg.pause),
        "roi": ("Altyazı Alanı Seç", cfg.select_roi),
        "overlay": ("Overlay Göster / Gizle", cfg.toggle_overlay),
        "history": ("Çeviri Geçmişi", cfg.history),
    }

    desktop_template = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=GameOCR {name}\n"
        f"Exec={trigger_script} {{action}}\n"
        "NoDisplay=true\n"
        "StartupNotify=false\n"
        "X-KDE-StartupNotify=false\n"
        "X-KDE-GlobalAccel-CommandShortcut=true\n"
    )

    for action, (friendly, sc) in action_map.items():
        try:
            desk_file = apps_dir / f"gameocr-{action}.desktop"
            desk_file.write_text(desktop_template.format(name=friendly, action=action))
            subprocess.run(
                ["kwriteconfig6", "--file", "kglobalshortcutsrc", "--group", f"gameocr-{action}.desktop", "--key", "_k_friendly_name", f"GameOCR {friendly}"],
                check=False,
            )
            val = f"{sc},none,GameOCR {friendly}" if (cfg.enabled and sc) else "none,none,none"
            subprocess.run(
                ["kwriteconfig6", "--file", "kglobalshortcutsrc", "--group", f"gameocr-{action}.desktop", "--key", "_launch", val],
                check=False,
            )
        except Exception:
            pass

    if shutil.which("kbuildsycoca6"):
        subprocess.run(["kbuildsycoca6"], check=False, capture_output=True)
    if shutil.which("busctl"):
        subprocess.run(["busctl", "--user", "call", "org.kde.KWin", "/KWin", "org.kde.KWin", "reconfigure"], check=False)


class HotkeyBridge(QObject):
    action_triggered = pyqtSignal(str)


class GlobalHotkeyListener:
    def __init__(
        self,
        cfg: HotkeysConfig,
        callbacks: dict[str, Callable[[], None]],
    ) -> None:
        self.cfg = cfg
        self.callbacks = callbacks
        self.bridge = HotkeyBridge()
        self.bridge.action_triggered.connect(self._handle_main_thread_action)
        self._stop_event = threading.Event()
        self._xlib_thread: threading.Thread | None = None
        self._udp_thread: threading.Thread | None = None
        self._udp_sock: socket.socket | None = None
        self._last_trigger: dict[str, float] = {}

    def start(self) -> None:
        if not self.cfg.enabled:
            log.info("Global kısayollar devre dışı")
            return

        self._stop_event.clear()

        if sys.platform == "win32":
            self._start_win32_listener()
            log.info("Global kısayollar dinleyicisi (Win32 RegisterHotKey) başlatıldı")
            return

        # 1. KDE Wayland KWin Komut Kısayolları Eşitlemesi
        threading.Thread(target=_sync_kde_command_shortcuts, args=(self.cfg,), daemon=True).start()

        # 2. Yerel UDP Soket Dinleyicisi (KDE tetikleyicileri için)
        self._start_udp_listener()

        # 3. X11 / XWayland GrabKey Dinleyicisi
        self._start_xlib_listener()

        log.info("Global kısayollar dinleyicisi (Dual-Layer) başlatıldı")

    def _start_win32_listener(self) -> None:
        self._xlib_thread = threading.Thread(
            target=self._run_win32,
            name="HotkeyWin32",
            daemon=True,
        )
        self._xlib_thread.start()

    def _run_win32(self) -> None:
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
        except Exception as exc:
            log.debug("Win32 user32 yüklenemedi: %s", exc)
            return

        action_map = {
            1: ("pause", self.cfg.pause),
            2: ("select_roi", self.cfg.select_roi),
            3: ("toggle_overlay", self.cfg.toggle_overlay),
            4: ("history", self.cfg.history),
        }
        id_to_action: dict[int, str] = {}
        for hk_id, (act, sc) in action_map.items():
            parsed = _parse_win32_shortcut(sc)
            if parsed is None:
                continue
            mods, vk = parsed
            if user32.RegisterHotKey(None, hk_id, mods, vk):
                id_to_action[hk_id] = act

        msg = wintypes.MSG()
        WM_HOTKEY = 0x0312
        PM_REMOVE = 0x0001
        try:
            while not self._stop_event.is_set():
                if user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                    if msg.message == WM_HOTKEY:
                        act = id_to_action.get(int(msg.wParam))
                        if act:
                            self._dispatch_action(act)
                else:
                    time.sleep(0.05)
        finally:
            for hk_id in id_to_action:
                try:
                    user32.UnregisterHotKey(None, hk_id)
                except Exception:
                    pass

    def stop(self) -> None:
        self._stop_event.set()
        if self._udp_sock:
            try:
                self._udp_sock.close()
            except Exception:
                pass
            self._udp_sock = None
        log.info("Global kısayollar dinleyicisi durduruldu")

    def update_config(self, cfg: HotkeysConfig) -> None:
        self.cfg = cfg
        self.stop()
        if self.cfg.enabled:
            self.start()

    def _dispatch_action(self, action: str) -> None:
        """Kısayol eylemini 0.25s debounce ile ana Qt thread'ine iletir."""
        now = time.time()
        last = self._last_trigger.get(action, 0.0)
        if now - last < 0.25:
            return
        self._last_trigger[action] = now

        cb = self.callbacks.get(action)
        if cb:
            log.info("Global kısayol algılandı: %s (Qt sinyali iletiliyor)", action)
            self.bridge.action_triggered.emit(action)

    def _handle_main_thread_action(self, action: str) -> None:
        """Qt Main GUI Thread üzerinde kısayol eylemini güvenle yürütür."""
        cb = self.callbacks.get(action)
        if cb:
            log.info("Global kısayol eylemi yürütülüyor: %s", action)
            try:
                cb()
            except Exception as exc:
                log.exception("Kısayol yürütülürken hata oluştu (%s): %s", action, exc)

    # ------------------------------------------------------------------ #
    # Yerel UDP Soket Dinleyicisi (KDE Wayland)
    # ------------------------------------------------------------------ #
    def _start_udp_listener(self) -> None:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("127.0.0.1", UDP_PORT))
            self._udp_sock = sock
        except Exception as exc:
            log.debug("UDP kısayol soketi açılamadı: %s", exc)
            return

        self._udp_thread = threading.Thread(
            target=self._run_udp,
            args=(sock,),
            name="HotkeyUDP",
            daemon=True,
        )
        self._udp_thread.start()

    def _run_udp(self, sock: socket.socket) -> None:
        while not self._stop_event.is_set():
            try:
                r, _, _ = select.select([sock], [], [], 0.5)
                if not r:
                    continue
                data, _ = sock.recvfrom(64)
                raw_act = data.decode("utf-8", errors="ignore").strip()
                # Alias haritası
                alias = {
                    "pause": "pause",
                    "roi": "select_roi",
                    "select_roi": "select_roi",
                    "overlay": "toggle_overlay",
                    "toggle_overlay": "toggle_overlay",
                    "history": "history",
                }
                action = alias.get(raw_act)
                if action:
                    self._dispatch_action(action)
            except Exception:
                break

    # ------------------------------------------------------------------ #
    # X11 / XWayland GrabKey Dinleyicisi
    # ------------------------------------------------------------------ #
    def _start_xlib_listener(self) -> None:
        self._xlib_thread = threading.Thread(
            target=self._run_xlib,
            name="HotkeyX11",
            daemon=True,
        )
        self._xlib_thread.start()

    def _run_xlib(self) -> None:
        try:
            from Xlib import X, display
            from Xlib.error import XError
            d = display.Display()
        except Exception as exc:
            log.debug("Xlib Display açılamadı: %s", exc)
            return

        root = d.screen().root

        action_map = {
            "pause": self.cfg.pause,
            "select_roi": self.cfg.select_roi,
            "toggle_overlay": self.cfg.toggle_overlay,
            "history": self.cfg.history,
        }

        bindings: dict[tuple[int, int], str] = {}
        lock_combos = _get_lock_combos(X)

        for action, shortcut_str in action_map.items():
            parsed = _parse_xlib_shortcut(d, shortcut_str)
            if not parsed:
                continue
            keycode, mask = parsed
            bindings[(keycode, mask)] = action
            for extra in lock_combos:
                try:
                    root.grab_key(
                        keycode,
                        mask | extra,
                        True,
                        X.GrabModeAsync,
                        X.GrabModeAsync,
                    )
                except XError:
                    pass

        try:
            d.sync()
        except Exception:
            pass

        fd = d.fileno()

        while not self._stop_event.is_set():
            try:
                r, _, _ = select.select([fd], [], [], 0.1)
                if not r and d.pending_events() == 0:
                    continue

                while d.pending_events() > 0:
                    ev = d.next_event()
                    if ev.type == X.KeyPress:
                        keycode = ev.detail
                        clean_state = ev.state & SIGNIFICANT_MODS
                        action = bindings.get((keycode, clean_state))
                        if action:
                            self._dispatch_action(action)
            except Exception as exc:
                log.debug("X11 kısayol döngüsü hatası: %s", exc)

        try:
            d.close()
        except Exception:
            pass
