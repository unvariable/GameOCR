"""OpenCV ön işleme boru hattı (saf fonksiyonlar, kolay test edilir).

Adımlar: grayscale -> büyütme -> gürültü giderme -> binarization ->
(gerekirse) ters çevirme. OCR, beyaz zemin üzerinde siyah yazıda en iyi
sonucu verir; oyun altyazıları ise genelde koyu zeminde açık renklidir.

Ayrıca ``ChangeGate`` ucuz bir kare farkı kontrolüyle görüntü
değişmediğinde pahalı OCR çağrısını tamamen atlatır.
"""
from __future__ import annotations

import cv2
import numpy as np

from .config import PreprocessConfig


def to_gray(img: np.ndarray) -> np.ndarray:
    if img.ndim == 2:
        return img
    if img.shape[2] == 4:
        return cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def upscale(gray: np.ndarray, factor: float) -> np.ndarray:
    if factor <= 1.0:
        return gray
    h, w = gray.shape[:2]
    # Zaten yeterince büyük çok satırlı ROI'lerde (h >= 240 ve w >= 400) 2x büyütme
    # RapidOCR/PP-OCRv4 CPU çıkarımını 10 kat yavaşlatır (77ms -> 836ms+) ve katkı sağlamaz.
    if h >= 240 and w >= 400:
        return gray
    max_w, max_h = 1280, 480
    if w * factor > max_w or h * factor > max_h:
        capped = min(factor, max_w / max(1, w), max_h / max(1, h))
        if capped <= 1.05:
            return gray
        return cv2.resize(gray, None, fx=capped, fy=capped, interpolation=cv2.INTER_CUBIC)
    return cv2.resize(gray, None, fx=factor, fy=factor, interpolation=cv2.INTER_CUBIC)


def binarize(gray: np.ndarray, mode: str) -> np.ndarray:
    if mode == "adaptive":
        # Blok boyutu görüntü yüksekliğine göre ölçeklenir (tek sayı olmalı).
        block = max(15, (gray.shape[0] // 8) | 1)
        return cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block, 10
        )
    _, out = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    return out


def normalize_polarity(binary: np.ndarray) -> np.ndarray:
    """Çoğunluk siyahsa (açık yazı / koyu zemin) görüntüyü ters çevirir;
    sonuç her zaman beyaz zemin üzerinde siyah yazıdır."""
    if cv2.countNonZero(binary) < binary.size / 2:
        return cv2.bitwise_not(binary)
    return binary


def preprocess(img: np.ndarray, cfg: PreprocessConfig) -> np.ndarray:
    """BGR/BGRA görüntüyü OCR'a hazır 3 kanallı BGR görüntüye çevirir."""
    gray = upscale(to_gray(img), cfg.scale)
    if cfg.mode == "none":
        out = gray
    else:
        if cfg.denoise:
            gray = cv2.medianBlur(gray, 3)
        out = normalize_polarity(binarize(gray, cfg.mode))
    # PaddleOCR 3 kanallı giriş bekler.
    return cv2.cvtColor(out, cv2.COLOR_GRAY2BGR)


class ChangeGate:
    """Ardışık kareler arasında anlamlı fark yoksa False döner.

    Kare 64 px genişliğe küçültülüp gri tonlamada karşılaştırılır; bu,
    tam çözünürlükte OCR'a göre binlerce kat ucuzdur.
    """

    def __init__(self, threshold_percent: float) -> None:
        self.threshold = threshold_percent
        self._prev: np.ndarray | None = None

    def reset(self) -> None:
        self._prev = None

    def changed(self, img: np.ndarray) -> bool:
        gray = to_gray(img)
        h, w = gray.shape[:2]
        small_w = 64
        small_h = max(4, int(h * small_w / max(w, 1)))
        small = cv2.resize(gray, (small_w, small_h), interpolation=cv2.INTER_AREA)
        if self._prev is None or self._prev.shape != small.shape:
            self._prev = small
            return True
        diff = float(cv2.absdiff(self._prev, small).mean()) / 255.0 * 100.0
        if diff >= self.threshold:
            self._prev = small
            return True
        return False
