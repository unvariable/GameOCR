"""Ekran yakalama soyutlaması ve otomatik backend seçimi.

Tüm backend'ler bir *kaynak* (oyun penceresi veya monitör) yakalar.
ROI, bu kaynağa göre 0..1 aralığında oransal tutulur; böylece pencere
taşınsa ya da ölçek değişse bile ROI geçerli kalır.

Overlay'in ekrandaki yeri:  kaynak_geometrisi (mantıksal px) + ROI oranları
"""
from __future__ import annotations

import logging
import os
import sys
import threading
from abc import ABC, abstractmethod

import numpy as np

from ..config import CaptureConfig

log = logging.getLogger(__name__)

Rect = tuple[int, int, int, int]  # x, y, w, h


class CaptureError(RuntimeError):
    pass


class OverlayHandle:
    """UI thread'inin overlay pencere kimliğini (X11 XID) yakalama
    thread'iyle paylaşmak için. Yalnızca mss yedeğinde kullanılır."""

    def __init__(self) -> None:
        self.xid: int = 0
        self.visible = threading.Event()


class CaptureBackend(ABC):
    name: str = "base"
    #: True ise overlay yakalanan görüntüye girer (ekran yakalama);
    #: CaptureWorker yakalama anında overlay'i gizlemelidir.
    captures_overlay: bool = False

    @abstractmethod
    def open(self) -> None:
        """Kaynağı hazırlar. Gerekirse kullanıcıdan seçim ister (bloklar)."""

    @abstractmethod
    def close(self) -> None: ...

    @abstractmethod
    def grab_full(self) -> np.ndarray | None:
        """Kaynağın tamamı (BGR). ROI seçimi için kullanılır."""

    def grab_roi(self, roi: list[float]) -> np.ndarray | None:
        """ROI'ye kırpılmış BGR görüntü. Backend'ler daha verimli
        sürümle ezebilir."""
        full = self.grab_full()
        if full is None:
            return None
        return crop_fraction(full, roi)

    @abstractmethod
    def source_geometry(self) -> Rect | None:
        """Kaynağın ekrandaki yeri (Qt/XWayland mantıksal pikseli)."""

    def forget_source(self) -> None:
        """Kayıtlı seçimi unutur; bir sonraki open() yeniden sorar."""

    def persist_state(self, cfg: CaptureConfig) -> None:
        """Seçim bilgisini (token, pencere kimliği) config'e yazar."""


def crop_fraction(img: np.ndarray, roi: list[float]) -> np.ndarray | None:
    h, w = img.shape[:2]
    x0 = int(round(roi[0] * w))
    y0 = int(round(roi[1] * h))
    x1 = int(round((roi[0] + roi[2]) * w))
    y1 = int(round((roi[1] + roi[3]) * h))
    x0, x1 = max(0, x0), min(w, x1)
    y0, y1 = max(0, y0), min(h, y1)
    if x1 - x0 < 4 or y1 - y0 < 4:
        return None
    return img[y0:y1, x0:x1]


def roi_to_screen(src: Rect, roi: list[float]) -> Rect:
    x, y, w, h = src
    return (
        int(round(x + roi[0] * w)),
        int(round(y + roi[1] * h)),
        max(1, int(round(roi[2] * w))),
        max(1, int(round(roi[3] * h))),
    )


def session_type() -> str:
    if sys.platform == "win32":
        return "win32"
    st = os.environ.get("XDG_SESSION_TYPE", "").lower()
    if st in ("wayland", "x11"):
        return st
    if os.environ.get("WAYLAND_DISPLAY"):
        return "wayland"
    if os.environ.get("DISPLAY"):
        return "x11"
    return "unknown"


def create_backend(cfg: CaptureConfig, overlay: OverlayHandle) -> CaptureBackend:
    """`cfg.backend == "auto"` ise oturum tipine göre seçer."""
    choice = cfg.backend.lower()
    if choice == "auto":
        if sys.platform == "win32":
            choice = "win32"
        else:
            st = session_type()
            if st == "wayland":
                choice = "portal"
            else:
                from .xcomposite_backend import xcomposite_available
                choice = "xcomposite" if xcomposite_available() else "mss"
        log.info("Yakalama backend'i belirlendi: %s (oturum: %s)", choice, session_type())

    if choice == "win32":
        from .win32_backend import Win32Backend
        return Win32Backend(cfg, overlay)
    if choice == "portal":
        from .portal_backend import PortalBackend
        return PortalBackend(cfg)
    if choice == "xcomposite":
        from .xcomposite_backend import XCompositeBackend
        return XCompositeBackend(cfg)
    if choice == "mss":
        from .mss_backend import MssBackend
        return MssBackend(cfg, overlay)
    raise CaptureError(f"Bilinmeyen yakalama backend'i: {cfg.backend}")
