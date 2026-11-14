"""X11 birincil backend'i: XComposite ile oyun penceresinin kendisini yakalar.

Composite eklentisi pencerenin içeriğini ekran dışı bir pixmap'e
yönlendirir; bu pixmap'ten okunan görüntüde üstteki pencereler
(dolayısıyla overlay'imiz) **yer almaz** -> self-capture sorunu yok.
Otomatik yönlendirme kompozitör kapalıyken de çalışır.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import threading

import numpy as np

from ..config import CaptureConfig
from .base import CaptureBackend, CaptureError, Rect, crop_fraction

log = logging.getLogger(__name__)


def xcomposite_available() -> bool:
    try:
        from Xlib import display
        d = display.Display()
        try:
            return d.has_extension("Composite")
        finally:
            d.close()
    except Exception:  # noqa: BLE001
        return False


class XCompositeBackend(CaptureBackend):
    name = "XComposite (X11 pencere)"
    captures_overlay = False

    def __init__(self, cfg: CaptureConfig) -> None:
        self.cfg = cfg
        self._lock = threading.Lock()   # Xlib Display thread-safe değildir
        self._d = None
        self._client = None             # oyunun istemci penceresi
        self._frame = None              # kök pencerenin çocuğu (WM çerçevesi)
        self.window_id = cfg.x11_window_id

    # ------------------------------------------------------------------ #
    def open(self) -> None:
        from Xlib import X, display
        from Xlib.error import XError
        from Xlib.ext import composite

        with self._lock:
            self._d = display.Display()
            if not self._d.has_extension("Composite"):
                raise CaptureError("X sunucusunda Composite eklentisi yok")

            wid = self.window_id
            if wid and not self._window_exists(wid):
                log.info("Kayıtlı pencere (0x%x) artık yok, yeniden seçilecek", wid)
                wid = 0
            if not wid:
                wid = self._select_window()
            self.window_id = wid
            self._client = self._d.create_resource_object("window", wid)
            self._frame = self._toplevel(self._client)
            try:
                self._frame.composite_redirect_window(composite.RedirectAutomatic)
            except XError as exc:
                log.debug("Redirect atlandı (kompozitör zaten yönlendiriyor): %s", exc)
            self._d.sync()
            log.info("XComposite: pencere 0x%x (çerçeve 0x%x)", wid, self._frame.id)
            del X  # yalnızca import doğrulaması

    def _window_exists(self, wid: int) -> bool:
        from Xlib.error import XError
        try:
            self._d.create_resource_object("window", wid).get_geometry()
            return True
        except XError:
            return False

    def _select_window(self) -> int:
        """Kullanıcının oyun penceresine tıklamasını bekler."""
        log.info("Oyun penceresine tıklayın…")
        if shutil.which("xdotool"):
            out = subprocess.run(["xdotool", "selectwindow"], capture_output=True, text=True, check=False)
            if out.returncode == 0 and out.stdout.strip().isdigit():
                return int(out.stdout.strip())
        return self._select_window_xlib()

    def _select_window_xlib(self) -> int:
        from Xlib import X, Xcursorfont
        root = self._d.screen().root
        font = self._d.open_font("cursor")
        cursor = font.create_glyph_cursor(font, Xcursorfont.crosshair, Xcursorfont.crosshair + 1,
                                          (65535, 65535, 65535), (0, 0, 0))
        root.grab_pointer(False, X.ButtonPressMask, X.GrabModeAsync, X.GrabModeAsync,
                          X.NONE, cursor, X.CurrentTime)
        try:
            while True:
                ev = self._d.next_event()
                if ev.type == X.ButtonPress:
                    target = ev.child
                    if target == X.NONE:
                        raise CaptureError("Pencere seçilmedi")
                    return target.id
        finally:
            self._d.ungrab_pointer(X.CurrentTime)
            self._d.flush()

    def _toplevel(self, win):
        root = self._d.screen().root
        while True:
            tree = win.query_tree()
            if tree.parent == root or tree.parent is None:
                return win
            win = tree.parent

    # ------------------------------------------------------------------ #
    def close(self) -> None:
        with self._lock:
            if self._d is not None:
                self._d.close()
                self._d = None

    def forget_source(self) -> None:
        self.window_id = 0

    def persist_state(self, cfg: CaptureConfig) -> None:
        cfg.x11_window_id = int(self.window_id or 0)

    def _client_rect_in_frame(self) -> tuple[int, int, int, int]:
        g = self._client.get_geometry()
        t = self._client.translate_coords(self._frame, 0, 0)
        return -t.x, -t.y, g.width, g.height

    def source_geometry(self) -> Rect | None:
        from Xlib.error import XError
        with self._lock:
            if self._client is None:
                return None
            try:
                g = self._client.get_geometry()
                root = self._d.screen().root
                t = self._client.translate_coords(root, 0, 0)
                return -t.x, -t.y, g.width, g.height
            except XError:
                return None

    def _grab_region(self, x: int, y: int, w: int, h: int) -> np.ndarray | None:
        from Xlib import X
        from Xlib.error import XError
        with self._lock:
            if self._frame is None:
                return None
            try:
                ox, oy, cw, ch = self._client_rect_in_frame()
                pixmap = self._frame.composite_name_window_pixmap()
                try:
                    img = pixmap.get_image(ox + x, oy + y, w, h, X.ZPixmap, 0xFFFFFFFF)
                finally:
                    pixmap.free()
            except XError as exc:
                log.debug("XComposite okuma hatası: %s", exc)
                return None
        arr = np.frombuffer(img.data, dtype=np.uint8)
        if arr.size < w * h * 4:
            return None
        return arr[: w * h * 4].reshape(h, w, 4)[:, :, :3].copy()

    def _client_size(self) -> tuple[int, int] | None:
        with self._lock:
            if self._client is None:
                return None
            g = self._client.get_geometry()
            return g.width, g.height

    def grab_full(self) -> np.ndarray | None:
        size = self._client_size()
        return None if size is None else self._grab_region(0, 0, *size)

    def grab_roi(self, roi: list[float]) -> np.ndarray | None:
        size = self._client_size()
        if size is None:
            return None
        w, h = size
        x0, y0 = int(roi[0] * w), int(roi[1] * h)
        rw, rh = max(4, int(roi[2] * w)), max(4, int(roi[3] * h))
        rw, rh = min(rw, w - x0), min(rh, h - y0)
        if rw < 4 or rh < 4:
            return None
        return self._grab_region(x0, y0, rw, rh)


__all__ = ["XCompositeBackend", "xcomposite_available", "crop_fraction"]
