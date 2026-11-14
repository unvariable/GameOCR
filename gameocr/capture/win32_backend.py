"""Windows (Beta) Ekran ve Pencere Yakalama Backend'i (`Win32Backend`).

Özellikler:
  1. `SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)` API'si ile overlay
     penceresinin kendi ekran yakalamasına girmesini (self-capture) işletim sistemi
     kompozitörü (DWM) düzeyinde sıfır titremeyle engeller.
  2. Belirli bir oyun penceresi (`win32_hwnd`) seçilmişse `GetWindowRect` ile pencerenin
     ekran koordinatlarını takip eder.
  3. Kare yakalama için `dxcam` (DirectX Desktop Duplication) varsa onu, yoksa
     platformlar arası yüksek hızlı `mss` kütüphanesini kullanır.
"""
from __future__ import annotations

import logging
import sys
import threading
from typing import Any

import numpy as np

from ..config import CaptureConfig
from ..logging_utils import log_stage_exception
from .base import CaptureBackend, CaptureError, OverlayHandle, Rect, crop_fraction

log = logging.getLogger(__name__)

WDA_NONE = 0x00000000
WDA_EXCLUDEFROMCAPTURE = 0x00000011


def set_win32_exclude_from_capture(hwnd: int, exclude: bool = True) -> bool:
    """Windows 10 (2004+) ve Windows 11'de overlay penceresini ekran yakalamadan gizler."""
    if sys.platform != "win32" or not hwnd:
        return False
    try:
        import ctypes

        user32 = ctypes.windll.user32
        affinity = WDA_EXCLUDEFROMCAPTURE if exclude else WDA_NONE
        ok = bool(user32.SetWindowDisplayAffinity(int(hwnd), int(affinity)))
        if ok:
            log.debug("Win32 SetWindowDisplayAffinity uygulandı: hwnd=0x%x, exclude=%s", hwnd, exclude)
        return ok
    except Exception as exc:
        log.debug("Win32 SetWindowDisplayAffinity uygulanamadı: %s", exc)
        return False


def get_win32_window_rect(hwnd: int) -> Rect | None:
    """Seçilen Win32 penceresinin (x, y, w, h) ekran koordinatlarını döndürür."""
    if sys.platform != "win32" or not hwnd:
        return None
    try:
        import ctypes

        class RECT(ctypes.Structure):
            _fields_ = [
                ("left", ctypes.c_long),
                ("top", ctypes.c_long),
                ("right", ctypes.c_long),
                ("bottom", ctypes.c_long),
            ]

        user32 = ctypes.windll.user32
        if not user32.IsWindow(int(hwnd)):
            return None
        rect = RECT()
        if not user32.GetWindowRect(int(hwnd), ctypes.byref(rect)):
            return None
        w = max(0, int(rect.right - rect.left))
        h = max(0, int(rect.bottom - rect.top))
        if w < 32 or h < 32:
            return None
        return int(rect.left), int(rect.top), w, h
    except Exception as exc:
        log.debug("Win32 GetWindowRect hatası: %s", exc)
        return None


class Win32Backend(CaptureBackend):
    name = "Win32 (DWM / MSS / DXcam)"
    captures_overlay = False

    def __init__(self, cfg: CaptureConfig, overlay: OverlayHandle | None = None) -> None:
        self.cfg = cfg
        self.overlay = overlay or OverlayHandle()
        self.window_id: int = int(getattr(cfg, "win32_hwnd", 0) or cfg.x11_window_id or 0)
        self._local = threading.local()
        self._monitor: dict[str, int] | None = None
        self._dxcam_camera: Any = None

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

            # Opsiyonel DXcam hızlandırmasını kontrol et
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
            log.info("Win32Backend hazır: monitor=%s, hwnd=0x%x", self._monitor, self.window_id)
        except CaptureError:
            raise
        except Exception as exc:
            log_stage_exception(log, "win32_backend_open", exc)
            raise CaptureError(f"Win32Backend açılamadı: {exc}") from exc

    def close(self) -> None:
        if self._dxcam_camera is not None:
            try:
                self._dxcam_camera. release()
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
        self.cfg.win32_hwnd = 0

    def persist_state(self, cfg: CaptureConfig) -> None:
        cfg.win32_hwnd = int(self.window_id or 0)

    def source_geometry(self) -> Rect | None:
        if self.window_id > 0:
            win_rect = get_win32_window_rect(self.window_id)
            if win_rect is not None:
                return win_rect
        m = self._monitor
        return None if m is None else (int(m["left"]), int(m["top"]), int(m["width"]), int(m["height"]))

    def _grab_region(self, region: dict[str, int]) -> np.ndarray | None:
        if self._dxcam_camera is not None and self.window_id == 0:
            try:
                left = max(0, region["left"])
                top = max(0, region["top"])
                right = left + region["width"]
                bottom = top + region["height"]
                frame = self._dxcam_camera.grab(region=(left, top, right, bottom))
                # VMware/VirtualBox sanal GPU sürücülerinde DXGI tamamen siyah (0) kare döndürebilir;
                # bu durumda otomatik olarak GDI tabanlı MSS yakalamasına düşülür.
                if frame is not None and frame.size > 0 and int(np.max(frame)) > 0:
                    return frame
            except Exception:
                pass

        shot = self._sct().grab(region)
        return np.asarray(shot)[:, :, :3].copy()

    def grab_full(self) -> np.ndarray | None:
        geom = self.source_geometry()
        if geom is None:
            return None
        x, y, w, h = geom
        return self._grab_region({"left": x, "top": y, "width": w, "height": h})

    def grab_roi(self, roi: list[float]) -> np.ndarray | None:
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
    "get_win32_window_rect",
    "crop_fraction",
]

