"""Windows 10/11 Ekran ve Pencere Yakalama Backend'i (`Win32Backend`).

Özellikler:
  1. `SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)` API'si ile overlay
     penceresinin kendi ekran yakalamasına girmesini (self-capture) işletim sistemi
     kompozitörü (DWM) düzeyinde sıfır titremeyle engeller.
  2. Belirli bir oyun penceresi (`win32_hwnd`) seçilmişse `PrintWindow` + `CreateDIBSection`
     ile pencerenin kendi istemci içeriğini izole yakalar ve Z-order örtülme kontrolü
     ile üstteki başka pencerelerin okunmasını engeller.
  3. Tam ekran (monitör) modunda `dxcam` (DirectX Desktop Duplication) varsa onu, yoksa
     platformlar arası yüksek hızlı `mss` kütüphanesini kullanır.
"""
from __future__ import annotations

import ctypes
import logging
import os
import sys
import threading
from typing import Any

import numpy as np

from ..config import CaptureConfig
from ..logging_utils import log_stage_exception
from .base import CaptureBackend, CaptureError, OverlayHandle, Rect, crop_fraction, roi_to_screen

log = logging.getLogger(__name__)

WDA_NONE = 0x00000000
WDA_EXCLUDEFROMCAPTURE = 0x00000011

PW_CLIENTONLY = 0x00000001
PW_RENDERFULLCONTENT = 0x00000002

DWMWA_EXTENDED_FRAME_BOUNDS = 9
DWMWA_CLOAKED = 14

GW_HWNDPREV = 3
GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED = 0x00080000

BI_RGB = 0
DIB_RGB_COLORS = 0

_IGNORED_WINDOW_CLASSES = frozenset({"progman", "workerw"})


class _Win32Api:
    """64-bit güvenli argtypes/restype tanımlarıyla Win32 DLL tutamacını tembel yükler."""

    _lock = threading.Lock()
    _instance: "_Win32Api | None" = None

    def __init__(self) -> None:
        from ctypes import wintypes

        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        class RECT(ctypes.Structure):
            _fields_ = [
                ("left", ctypes.c_long),
                ("top", ctypes.c_long),
                ("right", ctypes.c_long),
                ("bottom", ctypes.c_long),
            ]

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ("biSize", wintypes.DWORD),
                ("biWidth", ctypes.c_long),
                ("biHeight", ctypes.c_long),
                ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long),
                ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD),
            ]

        class BITMAPINFO(ctypes.Structure):
            _fields_ = [
                ("bmiHeader", BITMAPINFOHEADER),
                ("bmiColors", wintypes.DWORD * 3),
            ]

        class MONITORINFOEXW(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("rcMonitor", RECT),
                ("rcWork", RECT),
                ("dwFlags", wintypes.DWORD),
                ("szDevice", wintypes.WCHAR * 32),
            ]

        self.POINT = POINT
        self.RECT = RECT
        self.BITMAPINFOHEADER = BITMAPINFOHEADER
        self.BITMAPINFO = BITMAPINFO
        self.MONITORINFOEXW = MONITORINFOEXW

        win_functype = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)
        WNDENUMPROC = win_functype(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        MONITORENUMPROC = win_functype(
            wintypes.BOOL,
            wintypes.HMONITOR,
            wintypes.HDC,
            ctypes.POINTER(RECT),
            wintypes.LPARAM,
        )
        self.WNDENUMPROC = WNDENUMPROC
        self.MONITORENUMPROC = MONITORENUMPROC

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
        try:
            dwmapi: Any = ctypes.WinDLL("dwmapi", use_last_error=True)
        except Exception:
            dwmapi = None

        # user32 prototipleri
        user32.IsWindow.argtypes = [wintypes.HWND]
        user32.IsWindow.restype = wintypes.BOOL

        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL

        user32.IsIconic.argtypes = [wintypes.HWND]
        user32.IsIconic.restype = wintypes.BOOL

        user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
        user32.GetWindowRect.restype = wintypes.BOOL

        user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
        user32.GetClientRect.restype = wintypes.BOOL

        user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(POINT)]
        user32.ClientToScreen.restype = wintypes.BOOL

        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextLengthW.restype = ctypes.c_int

        user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetWindowTextW.restype = ctypes.c_int

        user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetClassNameW.restype = ctypes.c_int

        user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.GetWindowLongW.restype = ctypes.c_long

        user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
        user32.SetWindowLongW.restype = ctypes.c_long

        user32.SetWindowPos.argtypes = [
            wintypes.HWND,
            wintypes.HWND,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.UINT,
        ]
        user32.SetWindowPos.restype = wintypes.BOOL

        user32.SetLayeredWindowAttributes.argtypes = [
            wintypes.HWND,
            wintypes.DWORD,
            wintypes.BYTE,
            wintypes.DWORD,
        ]
        user32.SetLayeredWindowAttributes.restype = wintypes.BOOL

        user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
        user32.EnumWindows.restype = wintypes.BOOL

        user32.EnumDisplayMonitors.argtypes = [
            wintypes.HDC,
            ctypes.POINTER(RECT),
            MONITORENUMPROC,
            wintypes.LPARAM,
        ]
        user32.EnumDisplayMonitors.restype = wintypes.BOOL

        user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFOEXW)]
        user32.GetMonitorInfoW.restype = wintypes.BOOL

        user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
        user32.GetWindow.restype = wintypes.HWND

        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD

        user32.GetDC.argtypes = [wintypes.HWND]
        user32.GetDC.restype = wintypes.HDC

        user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
        user32.ReleaseDC.restype = ctypes.c_int

        user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
        user32.PrintWindow.restype = wintypes.BOOL

        user32.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
        user32.SetWindowDisplayAffinity.restype = wintypes.BOOL

        # gdi32 prototipleri
        gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
        gdi32.CreateCompatibleDC.restype = wintypes.HDC

        gdi32.DeleteDC.argtypes = [wintypes.HDC]
        gdi32.DeleteDC.restype = wintypes.BOOL

        gdi32.CreateDIBSection.argtypes = [
            wintypes.HDC,
            ctypes.POINTER(BITMAPINFO),
            wintypes.UINT,
            ctypes.POINTER(ctypes.c_void_p),
            wintypes.HANDLE,
            wintypes.DWORD,
        ]
        gdi32.CreateDIBSection.restype = wintypes.HBITMAP

        gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
        gdi32.SelectObject.restype = wintypes.HGDIOBJ

        gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
        gdi32.DeleteObject.restype = wintypes.BOOL

        # dwmapi prototipleri
        if dwmapi is not None:
            dwmapi.DwmGetWindowAttribute.argtypes = [
                wintypes.HWND,
                wintypes.DWORD,
                ctypes.c_void_p,
                wintypes.DWORD,
            ]
            dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long
            if hasattr(dwmapi, "DwmEnableBlurBehindWindow"):
                dwmapi.DwmEnableBlurBehindWindow.argtypes = [wintypes.HWND, ctypes.c_void_p]
                dwmapi.DwmEnableBlurBehindWindow.restype = ctypes.c_long

        self.user32 = user32
        self.gdi32 = gdi32
        self.dwmapi = dwmapi

    @classmethod
    def get(cls) -> "_Win32Api | None":
        if sys.platform != "win32":
            return None
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance


def set_win32_exclude_from_capture(hwnd: int, exclude: bool = True) -> bool:
    """Windows 10 (2004+) ve Windows 11'de overlay penceresini ekran yakalamadan gizler."""
    if sys.platform != "win32" or not hwnd:
        return False
    try:
        api = _Win32Api.get()
        if api is None:
            return False
        affinity = WDA_EXCLUDEFROMCAPTURE if exclude else WDA_NONE
        ok = bool(api.user32.SetWindowDisplayAffinity(int(hwnd), int(affinity)))
        if ok:
            log.debug("Win32 SetWindowDisplayAffinity uygulandı: hwnd=0x%x, exclude=%s", hwnd, exclude)
        return ok
    except Exception as exc:
        log.debug("Win32 SetWindowDisplayAffinity uygulanamadı: %s", exc)
        return False


def is_win32_window_alive(hwnd: int) -> bool:
    """Belirtilen HWND'nin hala geçerli bir pencereye işaret edip etmediğini döndürür."""
    if sys.platform != "win32" or not hwnd:
        return False
    try:
        api = _Win32Api.get()
        return bool(api is not None and api.user32.IsWindow(int(hwnd)))
    except Exception:
        return False


def is_win32_window_cloaked(hwnd: int) -> bool:
    """DWMWA_CLOAKED ile pencerenin başka sanal masaüstünde veya gizli UWP durumunda olup olmadığını kontrol eder."""
    if sys.platform != "win32" or not hwnd:
        return False
    try:
        api = _Win32Api.get()
        if api is None or api.dwmapi is None:
            return False
        cloaked = ctypes.c_ulong(0)
        hr = api.dwmapi.DwmGetWindowAttribute(
            int(hwnd),
            DWMWA_CLOAKED,
            ctypes.byref(cloaked),
            ctypes.sizeof(cloaked),
        )
        return hr == 0 and int(cloaked.value) != 0
    except Exception:
        return False


def get_win32_window_title(hwnd: int) -> str:
    """Win32 pencere başlığını döndürür."""
    if sys.platform != "win32" or not hwnd:
        return ""
    try:
        api = _Win32Api.get()
        if api is None or not api.user32.IsWindow(int(hwnd)):
            return ""
        length = int(api.user32.GetWindowTextLengthW(int(hwnd)))
        if length <= 0:
            return ""
        buf = ctypes.create_unicode_buffer(length + 1)
        api.user32.GetWindowTextW(int(hwnd), buf, length + 1)
        return buf.value.strip()
    except Exception:
        return ""


def get_win32_raw_window_rect(hwnd: int) -> Rect | None:
    """Pencerenin ham Win32 `GetWindowRect` dikdörtgenini (DWM görünmez kenarlıklar dahil) döndürür."""
    if sys.platform != "win32" or not hwnd:
        return None
    try:
        api = _Win32Api.get()
        if api is None or not api.user32.IsWindow(int(hwnd)):
            return None
        rect = api.RECT()
        if not api.user32.GetWindowRect(int(hwnd), ctypes.byref(rect)):
            return None
        w = max(0, int(rect.right - rect.left))
        h = max(0, int(rect.bottom - rect.top))
        if w < 32 or h < 32:
            return None
        return int(rect.left), int(rect.top), w, h
    except Exception as exc:
        log.debug("Win32 raw window rect hatası: %s", exc)
        return None


def get_win32_monitors() -> list[tuple[str, Rect]]:
    """Win32 sistemdeki fiziksel monitörleri `[(device_name, (left, top, width, height)), ...]` döndürür."""
    if sys.platform != "win32":
        return []
    monitors: list[tuple[str, Rect]] = []
    try:
        api = _Win32Api.get()
        if api is None:
            return []

        def _mon_cb(hmon: int, _hdc: int, _lprect: Any, _lparam: int) -> bool:
            info = api.MONITORINFOEXW()
            info.cbSize = ctypes.sizeof(api.MONITORINFOEXW)
            if api.user32.GetMonitorInfoW(int(hmon), ctypes.byref(info)):
                r = info.rcMonitor
                mw = max(1, int(r.right - r.left))
                mh = max(1, int(r.bottom - r.top))
                monitors.append((info.szDevice.strip(), (int(r.left), int(r.top), mw, mh)))
            return True

        cb_fn = api.MONITORENUMPROC(_mon_cb)
        api.user32.EnumDisplayMonitors(None, None, cb_fn, 0)
    except Exception as exc:
        log.debug("Win32 monitör listeleme hatası: %s", exc)
    return monitors


def get_win32_outer_rect(hwnd: int) -> Rect | None:
    """Pencerenin DWM görünür çerçeve dikdörtgenini (yedek: GetWindowRect) döndürür."""
    if sys.platform != "win32" or not hwnd:
        return None
    try:
        api = _Win32Api.get()
        if api is None or not api.user32.IsWindow(int(hwnd)):
            return None
        rect = api.RECT()
        got = False
        if api.dwmapi is not None:
            hr = api.dwmapi.DwmGetWindowAttribute(
                int(hwnd),
                DWMWA_EXTENDED_FRAME_BOUNDS,
                ctypes.byref(rect),
                ctypes.sizeof(rect),
            )
            got = (hr == 0)
        if not got and not api.user32.GetWindowRect(int(hwnd), ctypes.byref(rect)):
            return None
        w = max(0, int(rect.right - rect.left))
        h = max(0, int(rect.bottom - rect.top))
        if w < 32 or h < 32:
            return None
        return int(rect.left), int(rect.top), w, h
    except Exception as exc:
        log.debug("Win32 outer rect hatası: %s", exc)
        return None


def get_win32_window_rect(hwnd: int) -> Rect | None:
    """Seçilen Win32 penceresinin görünür istemci (client) koordinatlarını döndürür.

    Pencere kapanmışsa, gizlenmişse, simge durumundaysa (`IsIconic`) veya DWM `cloaked`
    durumundaysa `None` döner.
    """
    if sys.platform != "win32" or not hwnd:
        return None
    try:
        api = _Win32Api.get()
        if api is None:
            return None
        h_int = int(hwnd)
        if not api.user32.IsWindow(h_int):
            return None
        if not api.user32.IsWindowVisible(h_int):
            return None
        if api.user32.IsIconic(h_int):
            return None
        if is_win32_window_cloaked(h_int):
            return None

        crect = api.RECT()
        pt = api.POINT(0, 0)
        if api.user32.GetClientRect(h_int, ctypes.byref(crect)) and api.user32.ClientToScreen(
            h_int, ctypes.byref(pt)
        ):
            cw = max(0, int(crect.right - crect.left))
            ch = max(0, int(crect.bottom - crect.top))
            if cw >= 32 and ch >= 32:
                return int(pt.x), int(pt.y), cw, ch

        return get_win32_outer_rect(h_int)
    except Exception as exc:
        log.debug("Win32 get_win32_window_rect hatası: %s", exc)
        return None


def compute_rect_occlusion_ratio(target_rect: Rect, occluder_rects: list[Rect]) -> float:
    """Hedef dikdörtgenin `occluder_rects` birleşimi tarafından örtülme oranını (0.0..1.0) hesaplar."""
    tx, ty, tw, th = target_rect
    if tw <= 0 or th <= 0 or not occluder_rects:
        return 0.0

    # 5x5 iç ızgara örneklemesi: birden fazla örtücü pencerenin birleşimini çift saymadan ölçer
    valid_occluders = [
        (ox, oy, ox + ow, oy + oh)
        for ox, oy, ow, oh in occluder_rects
        if ow > 0 and oh > 0 and ox < tx + tw and ox + ow > tx and oy < ty + th and oy + oh > ty
    ]
    if not valid_occluders:
        return 0.0

    grid = 5
    covered = 0
    total = grid * grid
    for iy in range(grid):
        py = ty + (iy + 0.5) * th / grid
        for ix in range(grid):
            px = tx + (ix + 0.5) * tw / grid
            for ox0, oy0, ox1, oy1 in valid_occluders:
                if ox0 <= px < ox1 and oy0 <= py < oy1:
                    covered += 1
                    break
    return covered / float(total)


def get_win32_rect_occlusion_ratio(
    hwnd: int,
    target_rect: Rect,
    ignore_pid: int | None = None,
) -> float:
    """Z-order'da `hwnd` üstünde duran pencerelerin `target_rect` alanını örtme oranını döndürür."""
    if sys.platform != "win32" or not hwnd:
        return 0.0
    try:
        from ctypes import wintypes

        api = _Win32Api.get()
        if api is None or not api.user32.IsWindow(int(hwnd)):
            return 0.0

        self_pid = int(ignore_pid if ignore_pid is not None else os.getpid())
        occluders: list[Rect] = []
        cur = api.user32.GetWindow(int(hwnd), GW_HWNDPREV)
        steps = 0
        while cur and steps < 512:
            steps += 1
            cur_int = int(cur)
            if (
                api.user32.IsWindowVisible(cur_int)
                and not api.user32.IsIconic(cur_int)
                and not is_win32_window_cloaked(cur_int)
            ):
                pid = wintypes.DWORD(0)
                api.user32.GetWindowThreadProcessId(cur_int, ctypes.byref(pid))
                if int(pid.value) != self_pid:
                    ex_style = int(api.user32.GetWindowLongW(cur_int, GWL_EXSTYLE))
                    is_clickthrough_overlay = (
                        ex_style & (WS_EX_TRANSPARENT | WS_EX_LAYERED)
                    ) == (WS_EX_TRANSPARENT | WS_EX_LAYERED)
                    if not is_clickthrough_overlay:
                        cls_buf = ctypes.create_unicode_buffer(128)
                        api.user32.GetClassNameW(cur_int, cls_buf, 128)
                        if cls_buf.value.strip().lower() not in _IGNORED_WINDOW_CLASSES:
                            orect = get_win32_outer_rect(cur_int)
                            if orect is not None:
                                occluders.append(orect)
            cur = api.user32.GetWindow(cur_int, GW_HWNDPREV)

        return compute_rect_occlusion_ratio(target_rect, occluders)
    except Exception as exc:
        log.debug("Win32 Z-order örtülme kontrolü hatası: %s", exc)
        return 0.0


def _print_window_to_bgr(api: _Win32Api, hwnd: int, width: int, height: int, flags: int) -> np.ndarray | None:
    """PrintWindow + CreateDIBSection ile belirtilen boyutta BGR görüntü yakalar ve GDI nesnelerini temizler."""
    if width <= 0 or height <= 0:
        return None
    hdc_screen = None
    hdc_mem = None
    hbitmap = None
    old_obj = None
    try:
        hdc_screen = api.user32.GetDC(0)
        if not hdc_screen:
            return None
        hdc_mem = api.gdi32.CreateCompatibleDC(hdc_screen)
        if not hdc_mem:
            return None

        bmi = api.BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(api.BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = int(width)
        bmi.bmiHeader.biHeight = -int(height)  # top-down DIB
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = BI_RGB
        bmi.bmiHeader.biSizeImage = int(width) * int(height) * 4

        bits_ptr = ctypes.c_void_p()
        hbitmap = api.gdi32.CreateDIBSection(
            hdc_mem,
            ctypes.byref(bmi),
            DIB_RGB_COLORS,
            ctypes.byref(bits_ptr),
            None,
            0,
        )
        if not hbitmap or not bits_ptr.value:
            return None

        old_obj = api.gdi32.SelectObject(hdc_mem, hbitmap)
        if not old_obj:
            return None

        ok = bool(api.user32.PrintWindow(int(hwnd), hdc_mem, int(flags)))
        if not ok:
            return None

        buf_size = int(width) * int(height) * 4
        raw = (ctypes.c_ubyte * buf_size).from_address(bits_ptr.value)
        arr = np.frombuffer(raw, dtype=np.uint8).reshape((int(height), int(width), 4))
        return arr[:, :, :3].copy()
    except Exception as exc:
        log.debug("PrintWindow yakalama hatası (hwnd=0x%x, flags=0x%x): %s", hwnd, flags, exc)
        return None
    finally:
        if hdc_mem and old_obj:
            try:
                api.gdi32.SelectObject(hdc_mem, old_obj)
            except Exception:
                pass
        if hbitmap:
            try:
                api.gdi32.DeleteObject(hbitmap)
            except Exception:
                pass
        if hdc_mem:
            try:
                api.gdi32.DeleteDC(hdc_mem)
            except Exception:
                pass
        if hdc_screen:
            try:
                api.user32.ReleaseDC(0, hdc_screen)
            except Exception:
                pass


def capture_win32_window_printwindow(hwnd: int, client_rect: Rect) -> np.ndarray | None:
    """Seçili Win32 penceresinin istemci içeriğini masaüstü Z-order'ından izole yakalar."""
    if sys.platform != "win32" or not hwnd:
        return None
    api = _Win32Api.get()
    if api is None or not api.user32.IsWindow(int(hwnd)):
        return None

    cx, cy, cw, ch = client_rect
    if cw < 4 or ch < 4:
        return None

    # 1. Deneme: Doğrudan istemci alanı + tam kompozisyon (DWM / Chromium / WPF / Qt uyumlu)
    bgr = _print_window_to_bgr(api, int(hwnd), cw, ch, PW_CLIENTONLY | PW_RENDERFULLCONTENT)
    if bgr is not None and bgr.size > 0 and int(np.max(bgr)) > 0:
        return bgr

    # 2. Deneme: Tam pencere + istemci dikdörtgeni kırpma (PrintWindow GetWindowRect alanını çizer)
    outer = get_win32_raw_window_rect(int(hwnd)) or get_win32_outer_rect(int(hwnd))
    if outer is not None:
        wx, wy, ww, wh = outer
        full_bgr = _print_window_to_bgr(api, int(hwnd), ww, wh, PW_RENDERFULLCONTENT)
        if full_bgr is not None and full_bgr.size > 0 and int(np.max(full_bgr)) > 0:
            ox = max(0, cx - wx)
            oy = max(0, cy - wy)
            x1 = min(ww, ox + cw)
            y1 = min(wh, oy + ch)
            if x1 - ox >= 4 and y1 - oy >= 4:
                return full_bgr[oy:y1, ox:x1].copy()
            return full_bgr

    return None


class Win32Backend(CaptureBackend):
    captures_overlay = False

    def __init__(self, cfg: CaptureConfig, overlay: OverlayHandle | None = None) -> None:
        self.cfg = cfg
        self.overlay = overlay or OverlayHandle()
        self.window_id: int = int(getattr(cfg, "win32_hwnd", 0) or 0)
        self._window_title: str = ""
        self._window_closed: bool = False
        self._local = threading.local()
        self._monitor: dict[str, int] | None = None
        self._dxcam_camera: Any = None

    @property
    def name(self) -> str:  # type: ignore[override]
        if self.window_id > 0:
            title = (self._window_title or f"0x{self.window_id:x}").strip()
            if len(title) > 42:
                title = title[:39] + "…"
            return f"Win32 Pencere: {title}"
        return "Win32 Tam Ekran (Monitör)"

    def _sct(self) -> Any:
        sct = getattr(self._local, "sct", None)
        if sct is None:
            import mss

            sct = mss.mss()
            self._local.sct = sct
        return sct

    def open(self) -> None:
        try:
            if self.overlay.xid:
                set_win32_exclude_from_capture(self.overlay.xid, exclude=True)

            if self.window_id > 0 and sys.platform == "win32":
                if not is_win32_window_alive(self.window_id):
                    log.warning(
                        "Kayıtlı Win32 pencere kimliği (0x%x) artık geçersiz; monitör moduna sıfırlanıyor",
                        self.window_id,
                    )
                    self.window_id = 0
                    self._window_title = ""
                    self._window_closed = False
                    self.cfg.win32_hwnd = 0
                else:
                    self._window_title = get_win32_window_title(self.window_id)
                    self._window_closed = False

            # Opsiyonel DXcam hızlandırmasını kontrol et (yalnızca tam ekran modunda kullanılır)
            try:
                import dxcam  # type: ignore[import-not-found]

                self._dxcam_camera = dxcam.create(output_color="BGR")
                log.info("Win32Backend: DXcam (DirectX Desktop Duplication) aktif")
            except Exception:
                self._dxcam_camera = None

            monitors = self._sct().monitors
            idx = self.cfg.mss_monitor if 0 < self.cfg.mss_monitor < len(monitors) else 1
            if len(monitors) <= 1:
                raise CaptureError("Win32Backend: Monitör bulunamadı")
            self._monitor = dict(monitors[idx])
            log.info(
                "Win32Backend hazır: mode=%s, monitor=%s, hwnd=0x%x",
                self.name,
                self._monitor,
                self.window_id,
            )
        except CaptureError:
            raise
        except Exception as exc:
            log_stage_exception(log, "win32_backend_open", exc)
            raise CaptureError(f"Win32Backend açılamadı: {exc}") from exc

    def close(self) -> None:
        if self._dxcam_camera is not None:
            try:
                self._dxcam_camera.release()
            except Exception:
                pass
            self._dxcam_camera = None
        sct = getattr(self._local, "sct", None)
        if sct is not None:
            try:
                sct.close()
            except Exception:
                pass
            self._local.sct = None

    def forget_source(self) -> None:
        self.window_id = 0
        self._window_title = ""
        self._window_closed = False
        self.cfg.win32_hwnd = 0
        self.cfg.x11_window_id = 0

    def persist_state(self, cfg: CaptureConfig) -> None:
        cfg.win32_hwnd = int(self.window_id or 0)

    def is_window_closed(self) -> bool:
        if self.window_id <= 0:
            return False
        if self._window_closed:
            return True
        if sys.platform == "win32" and not is_win32_window_alive(self.window_id):
            self._window_closed = True
            return True
        return False

    def source_geometry(self) -> Rect | None:
        # Belirli bir pencere seçiliyse ASLA monitöre düşme: pencere simge durumunda
        # veya kapanmışsa None döndür ki yakalama güvenli şekilde dursun.
        if self.window_id > 0:
            win_rect = get_win32_window_rect(self.window_id)
            if win_rect is None and sys.platform == "win32" and not is_win32_window_alive(self.window_id):
                self._window_closed = True
            return win_rect
        m = self._monitor
        return None if m is None else (int(m["left"]), int(m["top"]), int(m["width"]), int(m["height"]))

    def _grab_region(self, region: dict[str, int]) -> np.ndarray | None:
        # DXcam varsayılan olarak yalnızca birincil monitör (0, 0) koordinatlarını destekler.
        # İkincil veya negatif koordinatlı monitörlerde MSS kullanarak yanlış ekran kırpmasını önle.
        if (
            self._dxcam_camera is not None
            and self.window_id == 0
            and self._monitor is not None
            and int(self._monitor.get("left", 0)) == 0
            and int(self._monitor.get("top", 0)) == 0
        ):
            try:
                mon_w = int(self._monitor.get("width", 0))
                mon_h = int(self._monitor.get("height", 0))
                left = int(region["left"])
                top = int(region["top"])
                right = left + int(region["width"])
                bottom = top + int(region["height"])
                if 0 <= left < right <= mon_w and 0 <= top < bottom <= mon_h:
                    frame = self._dxcam_camera.grab(region=(left, top, right, bottom))
                    # VMware/VirtualBox sanal GPU sürücülerinde DXGI tamamen siyah (0) kare döndürebilir;
                    # bu durumda otomatik olarak GDI tabanlı MSS yakalamasına düşülür.
                    if frame is not None and frame.size > 0 and int(np.max(frame)) > 0:
                        return frame
            except Exception:
                pass

        shot = self._sct().grab(region)
        return np.asarray(shot)[:, :, :3].copy()

    def _grab_window_frame(self, roi: list[float] | None) -> np.ndarray | None:
        geom = get_win32_window_rect(self.window_id)
        if geom is None:
            if sys.platform == "win32" and not is_win32_window_alive(self.window_id):
                self._window_closed = True
            return None

        target_rect = roi_to_screen(geom, roi) if roi is not None else geom
        occ = get_win32_rect_occlusion_ratio(self.window_id, target_rect)
        if roi is not None and occ >= 0.75:
            log.debug(
                "Seçili pencerenin ROI alanı başka pencereyle örtülü (oran=%.2f); okuma duraklatıldı",
                occ,
            )
            return None

        full_win = capture_win32_window_printwindow(self.window_id, geom)
        if full_win is not None and full_win.size > 0:
            if roi is not None:
                return crop_fraction(full_win, roi)
            return full_win

        # PrintWindow başarısız/siyahsa (bazı exclusive DirectX/Vulkan oyunları)
        # YALNIZCA hedef alan başka bir pencereyle örtülü değilse MSS ekran karesine düş.
        if occ <= 0.05:
            tx, ty, tw, th = target_rect
            return self._grab_region(
                {"left": tx, "top": ty, "width": max(4, tw), "height": max(4, th)}
            )

        log.debug(
            "PrintWindow siyah/başarısız ve hedef alan örtülü (oran=%.2f); başka pencere okunmuyor",
            occ,
        )
        return None

    def grab_full(self) -> np.ndarray | None:
        if self.window_id > 0:
            return self._grab_window_frame(None)
        geom = self.source_geometry()
        if geom is None:
            return None
        x, y, w, h = geom
        return self._grab_region({"left": x, "top": y, "width": w, "height": h})

    def grab_roi(self, roi: list[float]) -> np.ndarray | None:
        if self.window_id > 0:
            return self._grab_window_frame(roi)
        geom = self.source_geometry()
        if geom is None:
            return None
        gx, gy, gw, gh = geom
        region = {
            "left": gx + int(round(roi[0] * gw)),
            "top": gy + int(round(roi[1] * gh)),
            "width": max(4, int(round(roi[2] * gw))),
            "height": max(4, int(round(roi[3] * gh))),
        }
        return self._grab_region(region)


__all__ = [
    "Win32Backend",
    "set_win32_exclude_from_capture",
    "is_win32_window_alive",
    "is_win32_window_cloaked",
    "get_win32_window_title",
    "get_win32_raw_window_rect",
    "get_win32_monitors",
    "get_win32_outer_rect",
    "get_win32_window_rect",
    "compute_rect_occlusion_ratio",
    "get_win32_rect_occlusion_ratio",
    "capture_win32_window_printwindow",
    "crop_fraction",
]
