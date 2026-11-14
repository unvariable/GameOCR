"""X11 yedek backend'i: `mss` ile monitör yakalama.

Ekran yakalandığı için overlay de görüntüye girer. Bunu önlemek için
yakalama anında overlay penceresinin `_NET_WM_WINDOW_OPACITY` değeri
kısa süreliğine 0 yapılır (doğrudan Xlib ile, Qt thread'ine dokunmadan).
Bu, hafif bir titremeye yol açabilir; bu yüzden yalnızca XComposite
kullanılamadığında devreye girer.
"""
from __future__ import annotations

import logging
import threading
import time

import numpy as np

from ..config import CaptureConfig
from .base import CaptureBackend, CaptureError, OverlayHandle, Rect, crop_fraction

log = logging.getLogger(__name__)

# Kompozitörün overlay'siz bir kare çizmesi için beklenen süre.
_COMPOSITOR_SETTLE_S = 0.025


class MssBackend(CaptureBackend):
    name = "mss (X11 ekran)"
    captures_overlay = True

    def __init__(self, cfg: CaptureConfig, overlay: OverlayHandle) -> None:
        self.cfg = cfg
        self.overlay = overlay
        self._local = threading.local()   # mss örneği thread'e özeldir
        self._monitor: dict | None = None
        self._xdisplay = None
        self._opacity_atom = None

    # ------------------------------------------------------------------ #
    def _sct(self):
        sct = getattr(self._local, "sct", None)
        if sct is None:
            import mss
            sct = mss.mss()
            self._local.sct = sct
        return sct

    def open(self) -> None:
        monitors = self._sct().monitors
        idx = self.cfg.mss_monitor if 0 < self.cfg.mss_monitor < len(monitors) else 1
        if len(monitors) <= 1:
            raise CaptureError("mss monitör bulamadı (X11 oturumu gerekli)")
        self._monitor = dict(monitors[idx])
        log.info("mss: monitör %d %s", idx, self._monitor)
        try:
            from Xlib import display
            self._xdisplay = display.Display()
            self._opacity_atom = self._xdisplay.intern_atom("_NET_WM_WINDOW_OPACITY")
        except Exception as exc:  # noqa: BLE001 - Xlib çok çeşitli hata atar
            log.warning("Overlay gizleme kullanılamıyor: %s", exc)

    def close(self) -> None:
        sct = getattr(self._local, "sct", None)
        if sct is not None:
            sct.close()
        if self._xdisplay is not None:
            self._xdisplay.close()
            self._xdisplay = None

    def source_geometry(self) -> Rect | None:
        m = self._monitor
        return None if m is None else (m["left"], m["top"], m["width"], m["height"])

    # ------------------------------------------------------------------ #
    def _set_overlay_opacity(self, value: float | None) -> bool:
        if self._xdisplay is None or not self.overlay.xid or not self.overlay.visible.is_set():
            return False
        from Xlib import Xatom
        win = self._xdisplay.create_resource_object("window", self.overlay.xid)
        if value is None:
            win.delete_property(self._opacity_atom)
        else:
            win.change_property(self._opacity_atom, Xatom.CARDINAL, 32, [int(value * 0xFFFFFFFF)])
        self._xdisplay.sync()
        return True

    def _grab(self, region: dict) -> np.ndarray:
        hidden = self._set_overlay_opacity(0.0)
        if hidden:
            time.sleep(_COMPOSITOR_SETTLE_S)
        try:
            shot = self._sct().grab(region)
        finally:
            if hidden:
                self._set_overlay_opacity(None)
        return np.asarray(shot)[:, :, :3]  # BGRA -> BGR

    def grab_full(self) -> np.ndarray | None:
        if self._monitor is None:
            return None
        return self._grab(self._monitor)

    def grab_roi(self, roi: list[float]) -> np.ndarray | None:
        m = self._monitor
        if m is None:
            return None
        region = {
            "left": m["left"] + int(roi[0] * m["width"]),
            "top": m["top"] + int(roi[1] * m["height"]),
            "width": max(4, int(roi[2] * m["width"])),
            "height": max(4, int(roi[3] * m["height"])),
        }
        return self._grab(region)


__all__ = ["MssBackend", "crop_fraction"]
