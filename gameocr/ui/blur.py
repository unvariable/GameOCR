"""KWin (Linux) ve DWM (Windows) arka plan bulanıklaştırma (blur-behind) entegrasyonu.

* Linux KDE Plasma (KWin): `_KDE_NET_WM_BLUR_BEHIND_REGION` X11 atomunu yazar.
* Windows 10/11 (DWM): `DwmEnableBlurBehindWindow` ve `SetWindowCompositionAttribute`
  (Acrylic / BlurBehind) API'lerini kullanarak buzlu cam efekti uygular.
"""
from __future__ import annotations

import logging
import sys
from typing import Any

log = logging.getLogger(__name__)

_BLUR_ATOM_NAME = "_KDE_NET_WM_BLUR_BEHIND_REGION"


def _get_display() -> Any:
    if sys.platform == "win32":
        return None
    try:
        from Xlib import display
        return display.Display()
    except Exception as exc:
        log.debug("Xlib Display açılamadı: %s", exc)
        return None


def enable_win32_blur(hwnd: int, enable: bool = True) -> bool:
    """Windows DWM `DwmEnableBlurBehindWindow` API'si ile pencere arkası bulanıklığı açar/kapatır."""
    if not hwnd:
        return False
    try:
        import ctypes

        class DWM_BLURBEHIND(ctypes.Structure):
            _fields_ = [
                ("dwFlags", ctypes.c_uint32),
                ("fEnable", ctypes.c_int),
                ("hRgnBlur", ctypes.c_void_p),
                ("fTransitionOnMaximized", ctypes.c_int),
            ]

        dwmapi = getattr(ctypes, "windll", None)
        if dwmapi is None or not hasattr(dwmapi, "dwmapi"):
            return False

        bb = DWM_BLURBEHIND()
        bb.dwFlags = 0x00000001  # DWM_BB_ENABLE
        bb.fEnable = 1 if enable else 0
        bb.hRgnBlur = None
        bb.fTransitionOnMaximized = 0
        hr = dwmapi.dwmapi.DwmEnableBlurBehindWindow(int(hwnd), ctypes.byref(bb))
        return hr == 0
    except Exception as exc:
        log.debug("Windows DWM blur uygulanamadı: %s", exc)
        return False


def enable_blur(win_id: int, width: int, height: int) -> bool:
    """Belirtilen pencereye platforma uygun (KWin veya Windows DWM) blur uygular."""
    if not win_id or width <= 0 or height <= 0:
        return False

    if sys.platform == "win32":
        return enable_win32_blur(win_id, enable=True)

    d = _get_display()
    if d is None:
        return False

    try:
        from Xlib import Xatom
        atom = d.intern_atom(_BLUR_ATOM_NAME)
        window = d.create_resource_object("window", int(win_id))
        # KWin bölge verisi olarak 32-bit CARDINAL formatında [x, y, w, h] bekler
        region_data = [0, 0, int(width), int(height)]
        window.change_property(atom, Xatom.CARDINAL, 32, region_data)
        d.sync()
        log.debug("KWin blur atomu yazıldı: win_id=0x%x (%dx%d)", win_id, width, height)
        return True
    except Exception as exc:
        log.debug("KWin blur atomu uygulanamadı: %s", exc)
        return False
    finally:
        d.close()


def disable_blur(win_id: int) -> bool:
    """Pencereden KWin veya Windows DWM blur efektini kaldırır."""
    if not win_id:
        return False

    if sys.platform == "win32":
        return enable_win32_blur(win_id, enable=False)

    d = _get_display()
    if d is None:
        return False

    try:
        atom = d.intern_atom(_BLUR_ATOM_NAME)
        window = d.create_resource_object("window", int(win_id))
        window.delete_property(atom)
        d.sync()
        return True
    except Exception as exc:
        log.debug("KWin blur atomu silinemedi: %s", exc)
        return False
    finally:
        d.close()


def set_kwin_blur_strength(strength: int) -> bool:
    """KWin genel bulanıklık yoğunluğunu (1..15) ayarlar (Windows'ta no-op)."""
    if sys.platform == "win32":
        return False
    import shutil
    import subprocess
    if not shutil.which("kwriteconfig6"):
        return False
    val = max(1, min(15, int(strength)))
    try:
        subprocess.run(
            ["kwriteconfig6", "--file", "kwinrc", "--group", "Effect-blur", "--key", "BlurStrength", str(val)],
            check=False,
        )
        if shutil.which("busctl"):
            subprocess.run(
                ["busctl", "--user", "call", "org.kde.KWin", "/KWin", "org.kde.KWin", "reconfigure"],
                check=False,
            )
        return True
    except Exception as exc:
        log.debug("KWin BlurStrength ayarlanamadı: %s", exc)
        return False
