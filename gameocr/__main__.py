"""GameOCR Ana Giriş Noktası (CLI / Masaüstü Uygulaması).

PyQt6 tabanlı GUI döngüsünü başlatır, sistem tepsisini, şeffaf overlay'i
ve arka plan işlem boru hattını entegre eder.
"""
from __future__ import annotations

import argparse
import locale
import logging
import os
import queue
import signal
import sys

# Overlay'in XWayland üzerinde mutlak koordinat ve tıklama geçirgenliği
# ile stabil çalışması için Linux'ta xcb platformu kullanılır (Windows'ta yerel QPA).
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
os.environ.setdefault("PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT", "False")
os.environ.setdefault("FLAGS_allocator_strategy", "auto_growth")
os.environ.setdefault("FLAGS_eager_delete_tensor_gb", "0.0")
os.environ.setdefault("FLAGS_fast_eager_deletion_mode", "1")
if sys.platform != "win32":
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
    # Popüler GTK tabanlı masaüstü ortamlarında (Cinnamon, GNOME, XFCE, MATE vb.)
    # yerel tema ve sistem tepsisi entegrasyonu için gtk3 platform temasını otomatik seç.
    _desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    if any(de in _desktop for de in ("cinnamon", "gnome", "xfce", "mate", "budgie", "unity", "pantheon", "lxde")):
        os.environ.setdefault("QT_QPA_PLATFORMTHEME", "gtk3")

from typing import Any

from PyQt6.QtCore import QTimer
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import QApplication

from gameocr.cache_store import CacheStore
from gameocr.capture.base import OverlayHandle
from gameocr.config import CACHE_DB_FILE, LOGS_DIR, Config, load_config, save_config
from gameocr.i18n import set_language, t
from gameocr.logging_utils import setup_logging
from gameocr.messages import UiKind, UiMessage
from gameocr.pipeline import Pipeline
from gameocr.ui.control_window import ControlWindow
from gameocr.ui.hotkeys import GlobalHotkeyListener
from gameocr.ui.overlay import OverlayWindow
from gameocr.ui.roi_selector import RoiSelectorWindow
from gameocr.ui.settings_dialog import SettingsDialog
from gameocr.ui.tray import TrayManager, get_tray_icon
from gameocr.ui.window_picker import trigger_window_selection

log = logging.getLogger("gameocr")


def _ipc_server_name() -> str:
    uid = os.getuid() if hasattr(os, "getuid") else os.getpid()
    return f"gameocr-control-v1-{uid}"


def _try_notify_running_instance(server_name: str, command: str = "SHOW") -> bool:
    """Çalışan bir GameOCR örneği varsa ona komut gönderir ve True döner."""
    sock = QLocalSocket()
    sock.connectToServer(server_name)
    if sock.waitForConnected(250):
        sock.write((command + "\n").encode("utf-8"))
        sock.flush()
        sock.waitForBytesWritten(250)
        sock.disconnectFromServer()
        return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="GameOCR - Oyun Altyazı Çeviri Katmanı")
    parser.add_argument("--select-roi", action="store_true", help="Başlangıçta doğrudan ROI seçimi aç")
    parser.add_argument("--select-window", action="store_true", help="Oyun penceresini yeniden seç")
    parser.add_argument("--minimized", action="store_true", help="Kontrol Merkezini başlangıçta gizli tut")
    parser.add_argument("--allow-multiple", action="store_true", help="Tek örnek (single-instance) kontrolünü atla")
    parser.add_argument("--log-level", default=None, choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()

    cfg = load_config()
    if args.select_window:
        cfg.capture.x11_window_id = 0
        cfg.capture.portal_restore_token = ""

    setup_logging(args.log_level or cfg.general.log_level, log_dir=LOGS_DIR)

    log.info("GameOCR başlatılıyor…")

    if sys.platform != "win32":
        # OpenCV (cv2) import edildiğinde QT_QPA_PLATFORM_PLUGIN_PATH'i ezebildiği için
        # QApplication başlatılmadan önce PyQt6'nın kendi Qt6/plugins/platforms yolu korunur.
        try:
            import PyQt6 as _pyqt6
            _qt_plugins = os.path.join(os.path.dirname(_pyqt6.__file__), "Qt6", "plugins")
            _qt_platforms = os.path.join(_qt_plugins, "platforms")
            if os.path.isdir(_qt_platforms):
                os.environ["QT_PLUGIN_PATH"] = _qt_plugins
                os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = _qt_platforms
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setApplicationName("GameOCR")
    app.setWindowIcon(get_tray_icon())
    app.setQuitOnLastWindowClosed(False)

    # QApplication sistem yerel ayarını (örn. tr_TR.UTF-8) yüklediğinde LC_NUMERIC
    # ondalık ayracını virgüle çevirir ve RapidOCR/ONNX eşik çözümlemesini bozar.
    try:
        locale.setlocale(locale.LC_NUMERIC, "C")
    except Exception:
        pass

    ipc_name = _ipc_server_name()
    if not args.allow_multiple and _try_notify_running_instance(ipc_name, "SHOW"):
        log.info("GameOCR zaten çalışıyor; mevcut Kontrol Merkezi öne getirildi.")
        os._exit(0)

    # Python'ın Ctrl+C (SIGINT) sinyalini anında yakalayabilmesi için timer
    sig_timer = QTimer()
    sig_timer.timeout.connect(lambda: None)
    sig_timer.start(200)

    cache_store = CacheStore(CACHE_DB_FILE, max_entries=cfg.cache.max_entries)
    ui_q: queue.Queue[UiMessage] = queue.Queue()
    overlay_handle = OverlayHandle()

    # Overlay penceresi
    overlay = OverlayWindow(cfg.overlay, ui_q=ui_q)
    overlay_handle.xid = int(overlay.winId())

    # Boru hattı
    pipeline = Pipeline(cfg, cache_store=cache_store, ui_q=ui_q, overlay_handle=overlay_handle)

    def shutdown() -> None:
        log.info("GameOCR anında kapatılıyor…")
        pipeline.stop_event.set()
        try:
            hotkey_listener.stop()
        except Exception:
            pass
        try:
            overlay.hide()
        except Exception:
            pass
        try:
            save_config(pipeline.cfg)
        except Exception:
            pass
        try:
            cache_store.close()
        except Exception:
            pass
        try:
            pipeline.backend.close()
        except Exception:
            pass
        # Beklemeden derhal sonlandır
        os._exit(0)

    set_language(cfg.general.ui_language)

    _active_settings_dialog: SettingsDialog | None = None
    _active_history_dialog: Any = None

    def set_paused(paused: bool) -> None:
        tray.is_paused = paused
        if paused:
            pipeline.pause()
            try:
                tray.pause_action.setText(t("tray.resume"))
                overlay.show_status(t("tray.paused_badge"))
            except Exception as exc:
                log.debug("Tray/Overlay duraklatma metni güncellenemedi: %s", exc)
            log.info("Çeviri duraklatıldı")
        else:
            pipeline.resume()
            try:
                tray.pause_action.setText(t("tray.pause"))
                overlay.fade_out(100)
            except Exception as exc:
                log.debug("Tray/Overlay devam metni güncellenemedi: %s", exc)
            log.info("Çeviri devam ettiriliyor")
        try:
            tray.update_status()
        except Exception as exc:
            log.debug("Tray durumu güncellenemedi: %s", exc)
        try:
            control_window.update_status(paused=paused)
        except Exception as exc:
            log.debug("Kontrol Merkezi durumu güncellenemedi: %s", exc)

    def on_tray_toggle_pause() -> None:
        set_paused(tray.is_paused)

    def on_hotkey_toggle_pause() -> None:
        set_paused(not tray.is_paused)

    def on_select_window() -> None:
        log.info("Program İzle / Pencere Seç tetiklendi…")
        trigger_window_selection(
            on_wayland_portal=lambda: pipeline.reselect_window(None),
            on_window_id_selected=lambda wid: (
                pipeline.reselect_window(wid),
                tray.show_notification("GameOCR", t("winpicker.selected_msg", wid=wid)),
            ),
        )

    def on_select_roi() -> None:
        log.info("Canlı ROI seçici açılıyor…")
        selector = RoiSelectorWindow(
            on_selected=lambda roi: (
                pipeline.set_roi(roi),
                tray.show_notification("GameOCR", "Yeni altyazı alanı (ROI) kaydedildi."),
            ),
        )
        setattr(app, "_roi_selector", selector)
        selector.show()

    def on_open_history() -> None:
        nonlocal _active_history_dialog
        if _active_history_dialog is not None and _active_history_dialog.isVisible():
            _active_history_dialog.raise_()
            _active_history_dialog.activateWindow()
            return
        log.info("Çeviri geçmişi açılıyor…")
        from gameocr.ui.history_dialog import HistoryDialog
        _active_history_dialog = HistoryDialog(cache_store)
        _active_history_dialog.show()
        _active_history_dialog.raise_()
        _active_history_dialog.activateWindow()

    def on_open_settings() -> None:
        nonlocal _active_settings_dialog
        if _active_settings_dialog is not None and _active_settings_dialog.isVisible():
            _active_settings_dialog.raise_()
            _active_settings_dialog.activateWindow()
            return

        def handle_applied(new_cfg: Config) -> None:
            pipeline.update_config(new_cfg)
            overlay.update_config(new_cfg.overlay)
            hotkey_listener.update_config(new_cfg.hotkeys)
            tray.update_config(new_cfg)
            tray.update_status()
            control_window.update_config(new_cfg)

        _active_settings_dialog = SettingsDialog(
            cfg=pipeline.cfg,
            cache_store=cache_store,
            translator=pipeline.translator,
            on_applied=handle_applied,
            on_select_window=on_select_window,
        )
        _active_settings_dialog.show()
        _active_settings_dialog.raise_()
        _active_settings_dialog.activateWindow()

    def on_toggle_overlay(visible: bool | None = None) -> None:
        if visible is None:
            new_visible = not overlay.is_user_visible()
        else:
            new_visible = visible

        overlay.set_user_visible(new_visible)
        tray.overlay_action.blockSignals(True)
        tray.overlay_action.setChecked(not new_visible)
        tray.overlay_action.blockSignals(False)
        log.info("Altyazı overlay görünürlüğü güncellendi: %s", "Açık" if new_visible else "Kapalı")

    # Evrensel Kontrol Merkezi penceresi (tüm masaüstü ortamlarında garanti erişim)
    control_window = ControlWindow(
        cfg=cfg,
        on_toggle_pause=on_hotkey_toggle_pause,
        on_select_window=on_select_window,
        on_select_roi=on_select_roi,
        on_toggle_overlay=lambda: on_toggle_overlay(None),
        on_open_settings=on_open_settings,
        on_open_history=on_open_history,
        on_quit=shutdown,
        hide_on_close=False,
    )

    # Tek örnek (Single Instance) IPC sunucusu
    ipc_server = QLocalServer(app)
    ipc_server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
    QLocalServer.removeServer(ipc_name)
    if ipc_server.listen(ipc_name):
        def _on_ipc_connection() -> None:
            while ipc_server.hasPendingConnections():
                conn = ipc_server.nextPendingConnection()
                if conn is None:
                    continue
                if conn.waitForReadyRead(200):
                    msg_text = bytes(conn.readAll()).decode("utf-8", errors="ignore").strip()
                    if msg_text == "SHOW":
                        control_window.bring_to_front()
                conn.disconnectFromServer()
                conn.deleteLater()

        ipc_server.newConnection.connect(_on_ipc_connection)

    # Sistem tepsisi yöneticisi
    tray = TrayManager(
        cfg=cfg,
        cache_store=cache_store,
        on_toggle_pause=on_tray_toggle_pause,
        on_select_window=on_select_window,
        on_select_roi=on_select_roi,
        on_open_settings=on_open_settings,
        on_open_history=on_open_history,
        on_toggle_overlay=on_toggle_overlay,
        on_show_control=control_window.bring_to_front,
        on_quit=shutdown,
    )

    # Global Sistem Kısayolları
    hotkey_callbacks = {
        "pause": on_hotkey_toggle_pause,
        "select_roi": on_select_roi,
        "toggle_overlay": lambda: on_toggle_overlay(None),
        "history": on_open_history,
        "show_panel": control_window.bring_to_front,
    }
    hotkey_listener = GlobalHotkeyListener(cfg.hotkeys, hotkey_callbacks)
    hotkey_listener.start()

    # UI mesajlarını tray'e yansıt
    original_handle_ui = overlay._handle_ui_message

    def extended_handle_ui(msg: UiMessage) -> None:
        original_handle_ui(msg)
        if msg.kind == UiKind.BACKEND:
            tray.update_status(backend=msg.text)
            control_window.update_status(backend=msg.text)
        elif msg.kind == UiKind.USAGE and msg.data:
            used, limit = msg.data
            remaining = max(0, limit - used)
            tray.update_status(quota=f"Kalan: {remaining:,} / {limit:,}")
        elif msg.kind == UiKind.ERROR:
            tray.show_notification("Hata", msg.text)

    overlay._handle_ui_message = extended_handle_ui

    # Temiz çıkış sinyal bağlantıları
    app.aboutToQuit.connect(shutdown)
    signal.signal(signal.SIGINT, lambda *_: shutdown())
    signal.signal(signal.SIGTERM, lambda *_: shutdown())

    # Boru hattını başlat
    pipeline.start()

    if not args.minimized:
        control_window.bring_to_front()

    if args.select_roi or not cfg.capture.has_roi():
        log.info("ROI tanımlı değil veya --select-roi istendi; ROI seçici açılıyor")
        on_select_roi()
    else:
        log.info("GameOCR aktif. Kontrol Merkezi veya sistem tepsisi üzerinden yönetebilirsiniz.")

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
