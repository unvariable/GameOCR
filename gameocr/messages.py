"""Thread'ler arasında kuyruklarla taşınan veri tipleri.

Her aşama yalnızca bu dataclass'ları üretir/tüketir; böylece modüller
birbirinin iç yapısını bilmeden haberleşir.
"""
from __future__ import annotations

import enum
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np


def now() -> float:
    return time.monotonic()


@dataclass(slots=True)
class TextStyleMeta:
    """Dinamik Görsel Metin Hizalama (Exact Alignment) için OCR metaverisi.

    * `bbox_rel`: ROI içindeki (x_rel, y_rel, w_rel, h_rel) [0.0 .. 1.0] oransal sınır kutusu.
    * `line_height_px`: Orijinal (ölçeklenmemiş) ROI karesindeki satır yüksekliği (piksel).
    * `text_color_hex`: Orijinal metinden örneklenen baskın #RRGGBB ön plan rengi.
    * `bg_color_hex`: Orijinal metin kutusunun arka planından örneklenen #RRGGBB rengi.
    * `word_colors`: Farklı renkte vurgulanan kelimelerin/ifadelerin [(metin, #RRGGBB), ...] listesi.
    * `raw_boxes`: Ham OCR kutu koordinatları [(xmin, ymin, xmax, ymax), ...].
    """
    bbox_rel: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)
    line_height_px: int = 20
    text_color_hex: str = "#F5F5F7"
    bg_color_hex: str = "#0F0F14"
    word_colors: list[tuple[str, str]] = field(default_factory=list)
    raw_boxes: list[tuple[float, float, float, float]] = field(default_factory=list)


@dataclass(slots=True)
class Frame:
    """CaptureWorker -> OcrWorker. ROI'ye kırpılmış BGR görüntü."""
    image: np.ndarray
    ts: float = field(default_factory=now)


@dataclass(slots=True)
class OcrResult:
    """OcrWorker -> FilterWorker. Boş `text` = altyazı ekranda yok."""
    text: str
    confidence: float = 0.0
    ts: float = field(default_factory=now)
    is_stable: bool = False
    style_meta: TextStyleMeta | None = None


@dataclass(slots=True)
class TranslateJob:
    """FilterWorker -> TranslatorWorker."""
    source: str
    norm_key: str
    src_lang: str
    tgt_lang: str
    context: str = ""
    ts: float = field(default_factory=now)
    style_meta: TextStyleMeta | None = None


class UiKind(enum.Enum):
    SHOW = "show"          # text: çeviri
    CLEAR = "clear"        # overlay'i söndür
    STATUS = "status"      # text: kısa bilgi/uyarı (overlay'de geçici)
    USAGE = "usage"        # data: (used, limit) DeepL kotası
    BACKEND = "backend"    # text: aktif yakalama backend'i
    GEOMETRY = "geometry"  # data: (x, y, w, h) overlay'in ekran konumu (mantıksal px)
    NEED_ROI = "need_roi"  # kaynak hazır, ROI seçilmesi gerekiyor
    ERROR = "error"        # text: kalıcı hata


@dataclass(slots=True)
class UiMessage:
    kind: UiKind
    text: str = ""
    data: Any = None


class ControlKind(enum.Enum):
    SET_LANG = "set_lang"        # payload: (src, tgt)
    SET_CONFIG = "set_config"    # payload: Config (canlı ayar güncellemesi)
    PAUSE = "pause"
    RESUME = "resume"
    SHOWN_TEXT = "shown_text"    # payload: str, ekrandaki çeviri (yankı koruması)
    RESELECT_WINDOW = "reselect_window"  # payload: int | None (yeni pencere ID veya Portal sıfırlama)


@dataclass(slots=True)
class Control:
    kind: ControlKind
    payload: Any = None
