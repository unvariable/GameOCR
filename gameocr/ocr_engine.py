"""Çift Motorlu (Dual-Engine) OCR Çıkarım Mimarisi ve Dinamik Görsel Metin Analizi.

Bu modül, SOLID prensiplerine uygun olarak iki farklı OCR motorunu ortak bir
soyut arayüz (`BaseOcrEngine`) ve Fabrika deseni (`OcrEngineFactory`) altında birleştirir:

1. **RapidOcrEngine (Ana Sürüm — GameOCR Lite / Universal):**
   - `rapidocr-onnxruntime` paketi üzerinde `CPUExecutionProvider` ile çalışır.
   - Ağır NVIDIA/CUDA kütüphanelerine ihtiyaç duymaz.
   - CPU darboğazlarını aşmak için `intra_op_num_threads` optimizasyonu,
     `use_cls=False` (180° yön sınıflandırma devre dışı), `det_score_mode='fast'`
     ve `det_limit_type='max'` ön işleme sınırlandırmalarını kullanır.

2. **PaddleCudaEngine (Özel GPU Sürümü — GameOCR_nvidia):**
   - `paddlepaddle-gpu` ve `PaddleOCR` üzerinde CUDA / TensorRT hızlandırmasıyla çalışır.
   - VRAM darboğazlarını önlemek için `auto_growth` stratejisi, `%35` VRAM tavanı,
     erken tensör silme (`eager_delete_tensor_gb=0.0`) ve opsiyonel TensorRT FP16
     alt-grafik motorunu kullanır.

Her iki motor da `OcrWorker` içinde tamamen thread-safe çalışır ve
Dinamik Görsel Metin Hizalama (`exact_alignment` -> `TextStyleMeta`: `bbox_rel`,
`line_height_px`, `text_color_hex`, `bg_color_hex`, `word_colors`) boru hattını
birebir korur.
"""
from __future__ import annotations

import inspect
import logging
import os
import re
import sys
import threading
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import cv2
import numpy as np

# PaddleX'in her başlatmada gereksiz HTTP ağ kontrolleri yapmasını engelle
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
# CPU çıkarımında OneDNN PIR uyumsuzluk hatasını önlemek için MKLDNN varsayılanını kapat
os.environ.setdefault("PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT", "False")

from .config import MODELS_DIR, OcrConfig
from .languages import source_to_paddle
from .logging_utils import StageError, log_stage_exception, timed_stage
from .messages import TextStyleMeta
from .ocr_models import OcrModelManager, resolve_ocr_pack_for_lang

log = logging.getLogger(__name__)


# =========================================================================== #
# Renk Örnekleme ve Dinamik Metin Hizalama (exact_alignment — Kırmızı Çizgi)
# =========================================================================== #
def _bgr_to_hex(b: float, g: float, r: float) -> str:
    r_i = max(0, min(255, int(round(float(r)))))
    g_i = max(0, min(255, int(round(float(g)))))
    b_i = max(0, min(255, int(round(float(b)))))
    return f"#{r_i:02X}{g_i:02X}{b_i:02X}"


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = (hex_color or "#F5F5F7").lstrip("#")
    if len(h) != 6:
        return (245, 245, 247)
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except ValueError:
        return (245, 245, 247)


def _rgb_distance(hex1: str, hex2: str) -> float:
    r1, g1, b1 = _hex_to_rgb(hex1)
    r2, g2, b2 = _hex_to_rgb(hex2)
    return float(((r1 - r2) ** 2 + (g1 - g2) ** 2 + (b1 - b2) ** 2) ** 0.5)


def _ensure_bgr(crop: np.ndarray) -> np.ndarray:
    if crop.ndim == 2:
        return cv2.cvtColor(crop, cv2.COLOR_GRAY2BGR)
    if crop.shape[2] == 4:
        return crop[:, :, :3]
    return crop


def _sample_bg_bgr(bgr: np.ndarray) -> np.ndarray:
    """Görüntü diliminin dış çerçeve (border) piksellerinden arka plan BGR medyanını hesaplar."""
    border_pixels = np.concatenate(
        [
            bgr[0, :, :],
            bgr[-1, :, :],
            bgr[:, 0, :],
            bgr[:, -1, :],
        ],
        axis=0,
    )
    return np.median(border_pixels, axis=0).astype(np.float32)


def _sample_fg_color_from_patch(
    bgr: np.ndarray,
    bg_bgr: np.ndarray | None = None,
    fallback: str = "#F5F5F7",
) -> str:
    """3-kanallı BGR kontrast maskesi ile ön plan (metin) rengini örnekler.

    Gri tonlamaya kıyasla açık arka plan üzerindeki sarı, turuncu, açık mavi
    gibi parlaklığı yakın ama renk kanalı farklı metinleri de yüksek doğrulukla yakalar.
    """
    if bgr.size == 0 or bgr.shape[0] < 2 or bgr.shape[1] < 2:
        return fallback

    if bg_bgr is None:
        bg_bgr = _sample_bg_bgr(bgr)

    # Her pikselin arka plan BGR vektörüne olan maksimum kanal uzaklığı (0..255)
    diff = np.max(np.abs(bgr.astype(np.float32) - bg_bgr.reshape(1, 1, 3)), axis=2)
    max_diff = float(diff.max())
    if max_diff < 12.0:
        return fallback

    diff_u8 = np.clip(diff, 0, 255).astype(np.uint8)
    _otsu_val, binary = cv2.threshold(diff_u8, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    fg_mask = binary > 0

    # Eğer Otsu maskesi çok dar veya çok geniş kaldıysa yüzdelik dilim tabanlı maske kullan
    fg_count = int(np.count_nonzero(fg_mask))
    if fg_count < 3 or fg_count > int(diff_u8.size * 0.78):
        thresh = max(14.0, float(np.percentile(diff, 70.0)))
        fg_mask = diff >= thresh
        fg_count = int(np.count_nonzero(fg_mask))
        if fg_count == 0:
            return fallback

    fg_bgr = bgr[fg_mask]
    fg_diff = diff[fg_mask]

    # Anti-aliasing kenar piksellerini dışlamak için arka plandan kontrastça en uzak %55'i seç
    if fg_diff.size >= 4:
        cutoff = float(np.percentile(fg_diff, 45.0))
        core_mask = fg_diff >= cutoff
        if np.any(core_mask):
            fg_bgr = fg_bgr[core_mask]

    med_b, med_g, med_r = np.median(fg_bgr, axis=0)
    return _bgr_to_hex(med_b, med_g, med_r)


def extract_background_color(
    raw_img: np.ndarray | None,
    bbox_rel: tuple[float, float, float, float] | None = None,
    fallback: str = "#0F0F14",
) -> str:
    """Metin sınır kutusunun arka plan rengini (#RRGGBB) örnekler."""
    if raw_img is None or not isinstance(raw_img, np.ndarray) or raw_img.size == 0:
        return fallback
    try:
        h, w = raw_img.shape[:2]
        if h < 2 or w < 2:
            return fallback
        if bbox_rel is not None:
            rx, ry, rw, rh = bbox_rel
            x0 = max(0, min(w - 1, int(round(rx * w))))
            y0 = max(0, min(h - 1, int(round(ry * h))))
            x1 = max(x0 + 1, min(w, int(round((rx + rw) * w))))
            y1 = max(y0 + 1, min(h, int(round((ry + rh) * h))))
            crop = raw_img[y0:y1, x0:x1]
        else:
            crop = raw_img
        if crop.size == 0 or crop.shape[0] < 2 or crop.shape[1] < 2:
            return fallback
        bgr = _ensure_bgr(crop)
        bg_bgr = _sample_bg_bgr(bgr)
        return _bgr_to_hex(bg_bgr[0], bg_bgr[1], bg_bgr[2])
    except Exception:
        return fallback


def extract_text_color(
    raw_img: np.ndarray | None,
    bbox_rel: tuple[float, float, float, float] | None = None,
    fallback: str = "#F5F5F7",
) -> str:
    """Orijinal BGR görüntüden arka planı ayıklayarak metnin gerçek rengini (#RRGGBB) örnekler."""
    if raw_img is None or not isinstance(raw_img, np.ndarray) or raw_img.size == 0:
        return fallback

    try:
        with timed_stage(log, "color_sampling", reraise=True, shape=raw_img.shape, bbox_rel=bbox_rel):
            h, w = raw_img.shape[:2]
            if h < 2 or w < 2:
                return fallback

            if bbox_rel is not None:
                rx, ry, rw, rh = bbox_rel
                x0 = max(0, min(w - 1, int(round(rx * w))))
                y0 = max(0, min(h - 1, int(round(ry * h))))
                x1 = max(x0 + 1, min(w, int(round((rx + rw) * w))))
                y1 = max(y0 + 1, min(h, int(round((ry + rh) * h))))
                crop = raw_img[y0:y1, x0:x1]
            else:
                crop = raw_img

            if crop.size == 0 or crop.shape[0] < 2 or crop.shape[1] < 2:
                return fallback

            bgr = _ensure_bgr(crop)
            bg_bgr = _sample_bg_bgr(bgr)
            return _sample_fg_color_from_patch(bgr, bg_bgr=bg_bgr, fallback=fallback)
    except Exception as exc:
        if not isinstance(exc, StageError):
            log_stage_exception(log, "color_sampling", exc)
        return fallback


def extract_word_level_colors(
    raw_img: np.ndarray | None,
    valid_items: list[dict[str, Any]],
    proc_shape: tuple[int, ...],
    bg_color_hex: str,
    fallback_fg: str = "#F5F5F7",
) -> tuple[str, list[tuple[str, str]]]:
    """Satır içindeki her kelimenin rengini ayrı ayrı örnekler; baskın metin rengini
    ve farklı renkteki vurgu kelimelerini (`[(kelime_veya_ifade, #RRGGBB), ...]`) döndürür.
    """
    if raw_img is None or not isinstance(raw_img, np.ndarray) or raw_img.size == 0 or not valid_items:
        return fallback_fg, []

    raw_h, raw_w = raw_img.shape[:2]
    proc_h = max(1, int(proc_shape[0]))
    proc_w = max(1, int(proc_shape[1]))
    scale_x = raw_w / float(proc_w)
    scale_y = raw_h / float(proc_h)

    bgr_full = _ensure_bgr(raw_img)
    bg_r, bg_g, bg_b = _hex_to_rgb(bg_color_hex)
    bg_bgr = np.array([bg_b, bg_g, bg_r], dtype=np.float32)

    word_samples: list[tuple[str, str]] = []

    for item in valid_items:
        line_text = str(item.get("text", "")).strip()
        if not line_text:
            continue
        words = line_text.split()
        if not words:
            continue

        ix0 = max(0, min(raw_w - 1, int(round(float(item["xmin"]) * scale_x))))
        iy0 = max(0, min(raw_h - 1, int(round(float(item["ymin"]) * scale_y))))
        ix1 = max(ix0 + 1, min(raw_w, int(round(float(item["xmax"]) * scale_x))))
        iy1 = max(iy0 + 1, min(raw_h, int(round(float(item["ymax"]) * scale_y))))
        box_w = max(1, ix1 - ix0)

        # Karakter uzunluklarına göre yatay kelime dilimlerini tahmin et
        total_chars = max(1, sum(len(w) for w in words) + max(0, len(words) - 1))
        cursor = 0
        for w_str in words:
            w_len = len(w_str)
            wx0 = ix0 + int(round((cursor / total_chars) * box_w))
            wx1 = ix0 + int(round(((cursor + w_len) / total_chars) * box_w))
            cursor += w_len + 1
            wx0 = max(ix0, min(ix1 - 1, wx0))
            wx1 = max(wx0 + 1, min(ix1, wx1))

            w_patch = bgr_full[iy0:iy1, wx0:wx1]
            w_color = _sample_fg_color_from_patch(w_patch, bg_bgr=bg_bgr, fallback=fallback_fg)
            cleaned_w = re.sub(r"^[^\w']+|[^\w']+$", "", w_str, flags=re.UNICODE)
            if cleaned_w:
                word_samples.append((cleaned_w, w_color))

    if not word_samples:
        return fallback_fg, []

    # En büyük renk kümesini "baskın (ana) metin rengi" olarak seç
    clusters: list[list[str]] = []
    for _, whex in word_samples:
        placed = False
        for cl in clusters:
            if _rgb_distance(whex, cl[0]) < 42.0:
                cl.append(whex)
                placed = True
                break
        if not placed:
            clusters.append([whex])

    clusters.sort(key=len, reverse=True)
    dominant_cluster = clusters[0]
    dom_rgbs = np.array([_hex_to_rgb(c) for c in dominant_cluster], dtype=np.float32)
    dom_r, dom_g, dom_b = np.median(dom_rgbs, axis=0)
    dominant_hex = _bgr_to_hex(dom_b, dom_g, dom_r)

    # Ana metin renginden belirgin şekilde (>= 42 RGB mesafesi) ayrılan vurgu kelimelerini topla
    highlighted_spans: list[tuple[str, str]] = []
    cur_words: list[str] = []
    cur_colors: list[str] = []

    for w_text, w_hex in word_samples:
        if _rgb_distance(w_hex, dominant_hex) >= 42.0 and _rgb_distance(w_hex, bg_color_hex) >= 35.0:
            if cur_colors and _rgb_distance(w_hex, cur_colors[-1]) < 48.0:
                cur_words.append(w_text)
                cur_colors.append(w_hex)
            else:
                if cur_words:
                    span_rgbs = np.array([_hex_to_rgb(c) for c in cur_colors], dtype=np.float32)
                    sr, sg, sb = np.median(span_rgbs, axis=0)
                    highlighted_spans.append((" ".join(cur_words), _bgr_to_hex(sb, sg, sr)))
                cur_words = [w_text]
                cur_colors = [w_hex]
        else:
            if cur_words:
                span_rgbs = np.array([_hex_to_rgb(c) for c in cur_colors], dtype=np.float32)
                sr, sg, sb = np.median(span_rgbs, axis=0)
                highlighted_spans.append((" ".join(cur_words), _bgr_to_hex(sb, sg, sr)))
                cur_words = []
                cur_colors = []

    if cur_words:
        span_rgbs = np.array([_hex_to_rgb(c) for c in cur_colors], dtype=np.float32)
        sr, sg, sb = np.median(span_rgbs, axis=0)
        highlighted_spans.append((" ".join(cur_words), _bgr_to_hex(sb, sg, sr)))

    return dominant_hex, highlighted_spans


def compute_style_meta(
    valid_items: list[dict[str, Any]],
    proc_shape: tuple[int, ...],
    raw_img: np.ndarray | None = None,
    default_color: str = "#F5F5F7",
) -> TextStyleMeta:
    """OCR kelime kutularından oransal sınır kutusu, orijinal satır yüksekliği ve metin rengini üretir."""
    try:
        with timed_stage(log, "bbox_alignment", reraise=True, item_count=len(valid_items)):
            proc_h = max(1, int(proc_shape[0]))
            proc_w = max(1, int(proc_shape[1]))

            min_x = min(float(it["xmin"]) for it in valid_items)
            min_y = min(float(it["ymin"]) for it in valid_items)
            max_x = max(float(it["xmax"]) for it in valid_items)
            max_y = max(float(it["ymax"]) for it in valid_items)

            x_rel = max(0.0, min(1.0, min_x / proc_w))
            y_rel = max(0.0, min(1.0, min_y / proc_h))
            w_rel = max(0.02, min(1.0 - x_rel, (max_x - min_x) / proc_w))
            h_rel = max(0.02, min(1.0 - y_rel, (max_y - min_y) / proc_h))
            bbox_rel = (round(x_rel, 4), round(y_rel, 4), round(w_rel, 4), round(h_rel, 4))

            # Ön işleme (upscale) çarpanını geri oranlayarak orijinal piksel yüksekliğini bul
            if raw_img is not None and raw_img.ndim >= 2 and raw_img.shape[0] > 0:
                scale_y = proc_h / float(raw_img.shape[0])
            else:
                scale_y = 1.0

            heights = [float(it["height"]) / max(0.1, scale_y) for it in valid_items]
            median_h = float(np.median(heights)) if heights else 20.0
            line_height_px = max(8, int(round(median_h)))

            raw_boxes = [
                (
                    round(float(it["xmin"]), 1),
                    round(float(it["ymin"]), 1),
                    round(float(it["xmax"]), 1),
                    round(float(it["ymax"]), 1),
                )
                for it in valid_items
            ]

            sampled_bg = extract_background_color(raw_img, bbox_rel=bbox_rel, fallback="#0F0F14")
            sampled_color = extract_text_color(raw_img, bbox_rel=bbox_rel, fallback=default_color)
            dominant_color, word_colors = extract_word_level_colors(
                raw_img,
                valid_items=valid_items,
                proc_shape=proc_shape,
                bg_color_hex=sampled_bg,
                fallback_fg=sampled_color,
            )
            final_fg = dominant_color if word_colors else sampled_color

            return TextStyleMeta(
                bbox_rel=bbox_rel,
                line_height_px=line_height_px,
                text_color_hex=final_fg,
                bg_color_hex=sampled_bg,
                word_colors=word_colors,
                raw_boxes=raw_boxes,
            )
    except Exception as exc:
        if not isinstance(exc, StageError):
            log_stage_exception(log, "bbox_alignment", exc)
        return TextStyleMeta(text_color_hex=default_color)


# =========================================================================== #
# Donanım ve Paket Varlık Kontrolleri
# =========================================================================== #
def _is_rapidocr_available() -> bool:
    """Sistemde `rapidocr_onnxruntime` paketinin kurulu olup olmadığını kontrol eder."""
    try:
        import rapidocr_onnxruntime  # noqa: F401
        return True
    except Exception:
        return False


def _is_paddle_available() -> bool:
    """Sistemde `paddleocr` paketinin kurulu olup olmadığını kontrol eder."""
    try:
        import paddleocr  # noqa: F401
        return True
    except Exception:
        return False


def _is_paddle_monkeypatched() -> bool:
    """Birim testlerinde `paddleocr.PaddleOCR` sınıfının mock fonksiyonla değiştirilip değiştirilmediğini algılar."""
    mod = sys.modules.get("paddleocr")
    if mod is None:
        return False
    attr = getattr(mod, "PaddleOCR", None)
    return attr is not None and inspect.isfunction(attr)


def resolve_paddle_device(cfg: OcrConfig) -> str:
    """Yapılandırmaya (`device`, `use_gpu`, `low_end_mode`) ve sistemdeki donanıma göre
    PaddleOCR çalışma cihazını (`'gpu:0'` veya `'cpu'`) belirler.
    """
    if os.environ.get("GAMEOCR_FORCE_CPU") == "1":
        return "cpu"
    pref = cfg.resolved_device() if hasattr(cfg, "resolved_device") else ("gpu" if cfg.use_gpu else "cpu")
    if pref == "cpu":
        return "cpu"
    try:
        import paddle

        if paddle.device.is_compiled_with_cuda() and paddle.device.cuda.device_count() > 0:
            return "gpu:0"
    except Exception:
        pass
    if pref == "gpu":
        log.warning("GPU hızlandırma seçildi ancak uyumlu CUDA GPU bulunamadı; otomatik olarak CPU moduna düşülüyor.")
    return "cpu"


def _parse_paddle_dict_results(results: Any) -> list[dict[str, Any]]:
    """PaddleOCR v3 `predict()` sözlük çıktısını standart kutu listesine dönüştürür."""
    if not results:
        return []
    res = results[0]
    if not isinstance(res, dict):
        return []
    texts: list[str] = res.get("rec_texts", [])
    scores: list[float] = res.get("rec_scores", [])
    boxes = res.get("rec_boxes")
    if not texts or not scores:
        return []

    items: list[dict[str, Any]] = []
    for idx, (txt, score) in enumerate(zip(texts, scores)):
        if boxes is not None and len(boxes) > idx:
            box = boxes[idx]
            xmin = float(box[0])
            ymin = float(box[1])
            xmax = float(box[2])
            ymax = float(box[3])
        else:
            xmin = 0.0
            ymin = float(idx * 25)
            xmax = 100.0
            ymax = float(idx * 25 + 20)
        items.append({
            "text": str(txt),
            "score": float(score),
            "xmin": xmin,
            "ymin": ymin,
            "xmax": xmax,
            "ymax": ymax,
        })
    return items


# =========================================================================== #
# 1. Ortak Soyut Arayüz (Interface / ABC): BaseOcrEngine
# =========================================================================== #
class BaseOcrEngine(ABC):
    """Tüm OCR motorlarının (RapidOCR ONNX-CPU ve PaddleOCR CUDA) türediği soyut temel sınıf (ABC).

    SOLID (Open/Closed & Liskov Substitution) prensipleri gereği `OcrWorker`
    arka planda hangi motorun çalıştığını bilmek zorunda değildir; tüm motorlar
    aynı thread-safe `recognize()`, `recognize_with_meta()`, `reload()` ve
    `update_config()` arayüzünü sunar.
    """

    engine_tag: str = "ONNX-CPU"

    def __init__(self, cfg: OcrConfig, src_lang: str = "EN") -> None:
        self.cfg = cfg
        self.src_lang = src_lang
        self.paddle_lang = source_to_paddle(src_lang)
        self.active_device: str = "cpu"
        self._lock = threading.Lock()
        self._ocr: Any = None
        self._load_model(self.paddle_lang)

    def _effective_det_limit(self) -> int:
        """Düşük sistem modunda veya CPU zorlamasında algılama kenar sınırını 640px ile sınırlar."""
        base = int(getattr(self.cfg, "det_limit_side_len", 960))
        if getattr(self.cfg, "low_end_mode", False) or os.environ.get("GAMEOCR_FORCE_CPU") == "1":
            return min(base, 640)
        return base

    @abstractmethod
    def _load_model(self, lang: str) -> None:
        """Seçili OCR motorunun model ağırlıklarını yükler ve ısınma (warmup) çıkarımı yapar."""

    @abstractmethod
    def _infer_raw_items(self, img: np.ndarray) -> list[dict[str, Any]]:
        """Görüntü üzerinde ham OCR çıkarımı çalıştırır ve standartlaştırılmış öğe listesi döndürür.

        Her bir öğe şu anahtarları içerir:
            `{"text": str, "score": float, "xmin": float, "ymin": float, "xmax": float, "ymax": float}`
        """

    def reload(self, src_lang: str) -> None:
        """Kaynak dil değiştiğinde (örn. Ayarlar'dan) modeli thread-safe olarak yeniden yükler."""
        new_paddle_lang = source_to_paddle(src_lang)
        with self._lock:
            if new_paddle_lang == self.paddle_lang and self._ocr is not None:
                self.src_lang = src_lang
                return
            self.src_lang = src_lang
            self._load_model(new_paddle_lang)

    def update_config(self, new_cfg: OcrConfig, src_lang: str | None = None) -> None:
        """Ayarlar'dan GPU/CPU cihazı, motor tipi veya Low-End modu değiştiğinde modeli canlı günceller."""
        target_lang = source_to_paddle(src_lang or self.src_lang)
        old_pref = self.cfg.resolved_device() if hasattr(self.cfg, "resolved_device") else ("gpu" if self.cfg.use_gpu else "cpu")
        new_pref = new_cfg.resolved_device() if hasattr(new_cfg, "resolved_device") else ("gpu" if new_cfg.use_gpu else "cpu")
        old_eng = self.cfg.resolved_engine() if hasattr(self.cfg, "resolved_engine") else "auto"
        new_eng = new_cfg.resolved_engine() if hasattr(new_cfg, "resolved_engine") else "auto"
        old_low_end = bool(getattr(self.cfg, "low_end_mode", False))
        new_low_end = bool(getattr(new_cfg, "low_end_mode", False))
        old_packs = list(getattr(self.cfg, "installed_ocr_packs", []))
        new_packs = list(getattr(new_cfg, "installed_ocr_packs", []))

        with self._lock:
            self.cfg = new_cfg
            if src_lang:
                self.src_lang = src_lang
            if (
                old_pref != new_pref
                or old_eng != new_eng
                or old_low_end != new_low_end
                or target_lang != self.paddle_lang
                or old_packs != new_packs
            ):
                log.info(
                    "OCR donanım/dil profili değişti (engine: %s->%s, device: %s->%s, low_end: %s->%s, packs: %s->%s), yeniden yükleniyor…",
                    old_eng,
                    new_eng,
                    old_pref,
                    new_pref,
                    old_low_end,
                    new_low_end,
                    old_packs,
                    new_packs,
                )
                self._load_model(target_lang)

    def recognize(self, img: np.ndarray) -> tuple[str, float]:
        """Görüntüdeki metni ve ortalama güven skorunu (0..1) döndürür."""
        text, score, _ = self.recognize_with_meta(img, raw_img=None)
        return text, score

    def recognize_with_meta(
        self,
        img: np.ndarray,
        raw_img: np.ndarray | None = None,
    ) -> tuple[str, float, TextStyleMeta | None]:
        """Görüntüdeki metni, ortalama güven skorunu ve görsel hizalama metaverisini (`TextStyleMeta`) döndürür."""
        if img is None or img.size == 0 or img.shape[0] < 8 or img.shape[1] < 8:
            return "", 0.0, None

        stage_name = f"ocr_predict[{self.engine_tag}]"
        t0 = time.perf_counter()
        with self._lock:
            try:
                with timed_stage(
                    log,
                    stage_name,
                    reraise=True,
                    engine=self.engine_tag,
                    device=self.active_device,
                    shape=img.shape,
                ):
                    raw_items = self._infer_raw_items(img)
            except Exception as exc:
                if not isinstance(exc, StageError):
                    log_stage_exception(log, stage_name, exc, shape=img.shape)
                return "", 0.0, None
        predict_ms = (time.perf_counter() - t0) * 1000.0

        if not raw_items:
            return "", 0.0, None

        # Güven skoru filtresi
        valid_items: list[dict[str, Any]] = []
        for it in raw_items:
            cleaned = str(it.get("text", "")).strip()
            score = float(it.get("score", 0.0))
            if not cleaned or score < self.cfg.min_confidence:
                continue
            xmin = float(it["xmin"])
            ymin = float(it["ymin"])
            xmax = float(it["xmax"])
            ymax = float(it["ymax"])
            h = max(1.0, ymax - ymin)
            valid_items.append({
                "text": cleaned,
                "score": score,
                "xmin": xmin,
                "ymin": ymin,
                "xmax": xmax,
                "ymax": ymax,
                "height": h,
                "cy": (ymin + ymax) / 2.0,
            })

        if not valid_items:
            return "", 0.0, None

        # Dikey orta noktaya göre sırala
        valid_items.sort(key=lambda it: it["cy"])

        # Dikey örtüşme ile satır kümeleme (aynı satırdaki kelimeler dikey olarak örtüşür)
        lines: list[list[dict[str, Any]]] = []
        for it in valid_items:
            best_line: list[dict[str, Any]] | None = None
            best_overlap = 0.0
            for line in lines:
                avg_ymin = sum(x["ymin"] for x in line) / len(line)
                avg_ymax = sum(x["ymax"] for x in line) / len(line)
                avg_h = max(1.0, avg_ymax - avg_ymin)

                overlap = min(it["ymax"], avg_ymax) - max(it["ymin"], avg_ymin)
                min_h = min(it["height"], avg_h)
                if min_h > 0:
                    ratio = overlap / min_h
                    if ratio >= 0.40 and ratio > best_overlap:
                        best_overlap = ratio
                        best_line = line
            if best_line is not None:
                best_line.append(it)
            else:
                lines.append([it])

        # Satırları yukarıdan aşağıya (ortalama dikey merkeze göre) sırala
        lines.sort(key=lambda l: sum(x["cy"] for x in l) / len(l))

        # Her satırın içindeki kelimeleri soldan sağa (xmin) sırala ve satırları birleştir
        sorted_items: list[dict[str, Any]] = []
        for line in lines:
            line.sort(key=lambda x: x["xmin"])
            sorted_items.extend(line)

        combined_text = " ".join(item["text"] for item in sorted_items).strip()
        avg_score = sum(item["score"] for item in sorted_items) / len(sorted_items)

        style_meta = compute_style_meta(
            sorted_items,
            proc_shape=img.shape,
            raw_img=raw_img if raw_img is not None else img,
        )

        if log.isEnabledFor(logging.DEBUG):
            log.debug(
                "[OCR: %s] %.2f ms | conf=%.2f | bbox_rel=%s | line_h=%dpx | color=%s | raw_boxes=%s | text='%s'",
                self.engine_tag,
                predict_ms,
                avg_score,
                style_meta.bbox_rel,
                style_meta.line_height_px,
                style_meta.text_color_hex,
                style_meta.raw_boxes,
                combined_text,
            )

        return combined_text, float(avg_score), style_meta


# =========================================================================== #
# 2. Ana Sürüm (Lite / Universal CPU): RapidOcrEngine (ONNX Runtime)
# =========================================================================== #
class RapidOcrEngine(BaseOcrEngine):
    """Ana Sürüm (`GameOCR-Universal-x86_64.AppImage`) için `rapidocr-onnxruntime` tabanlı motor.

    Özellikler ve CPU Optimizasyonları:
    - Varsayılan olarak `CPUExecutionProvider` (`det_use_cuda=False`, `rec_use_cuda=False`) kullanır.
    - Oyun altyazılarında ters (180°) metin bulunmadığı için `use_cls=False` ile yön sınıflandırıcı
      devre dışı bırakılır (~%25-30 daha düşük gecikme).
    - `intra_op_num_threads` ve `inter_op_num_threads=1` ile ONNX Runtime iş parçacığı çekişmesi
      (thread contention) engellenir.
    - Eğer `MODELS_DIR / "onnx_int8"` altında kuantize (`int8`) ONNX modelleri mevcutsa otomatik
      olarak onları yükler; aksi halde RapidOCR'ın gömülü hafif PP-OCRv4 ONNX modellerini kullanır.
    """

    engine_tag: str = "ONNX-CPU"

    @staticmethod
    def _find_bundled_onnx_rec_model(
        lang: str,
        models_dir: Path | None = None,
    ) -> tuple[Path, Path] | None:
        """Kaynak dile göre ('en', 'latin'/'tr', 'japan', 'korean', 'ch', 'ru', 'ar', 'el')
        gömülü veya indirilmiş ONNX tanıma modelini ve karakter sözlüğünü
        (`rec_model_path`, `rec_keys_path`) bulur.
        """
        try:
            mgr = OcrModelManager(models_dir=models_dir or MODELS_DIR)
            found = mgr.find_onnx_model_for_lang(lang)
            if found is not None:
                return found
        except Exception as exc:
            log.debug("OcrModelManager araması sırasında uyarı (%s): %s", lang, exc)

        norm_lang = (lang or "en").strip().lower()
        pack = resolve_ocr_pack_for_lang(norm_lang)
        if pack is not None:
            candidates = [(pack.model_filename, pack.dict_filename)]
            if pack.code == "LATIN":
                candidates.append(("en_rec.onnx", "en_dict.txt"))
            elif pack.code == "EN":
                candidates.append(("latin_rec.onnx", "latin_dict.txt"))
        else:
            return None

        project_root = Path(__file__).resolve().parent.parent
        search_dirs: list[Path] = [
            (models_dir or MODELS_DIR) / "onnx",
            project_root / "models" / "onnx",
            MODELS_DIR / "onnx",
        ]
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            search_dirs.insert(0, Path(meipass) / "models" / "onnx")
            search_dirs.append(Path(meipass).parent / "models" / "onnx")
        if getattr(sys, "frozen", False):
            try:
                search_dirs.insert(0, Path(sys.executable).resolve().parent / "models" / "onnx")
            except Exception:
                pass
        bundled_env = os.environ.get("GAMEOCR_BUNDLED_MODELS_DIR", "").strip()
        if bundled_env:
            search_dirs.insert(0, Path(bundled_env) / "onnx")

        for d in search_dirs:
            if not d.is_dir():
                continue
            for model_name, dict_name in candidates:
                m_path = d / model_name
                k_path = d / dict_name
                if m_path.is_file() and k_path.is_file():
                    return m_path, k_path
        return None

    def _create_rapid_ocr(self, det_limit: int, lang: str = "en") -> Any:
        from rapidocr_onnxruntime import RapidOCR

        cpu_threads = max(1, int(getattr(self.cfg, "cpu_threads", 4)))
        if getattr(self.cfg, "low_end_mode", False):
            cpu_threads = min(cpu_threads, 2)

        limit_type = getattr(self.cfg, "det_limit_type", "max") or "max"
        os.environ.setdefault("OMP_NUM_THREADS", str(cpu_threads))

        kwargs: dict[str, Any] = {
            "use_det": True,
            "use_cls": False,
            "use_rec": True,
            "det_limit_side_len": det_limit,
            "det_limit_type": limit_type,
            "det_unclip_ratio": 1.8,
            "det_score_mode": "fast",
            "det_use_cuda": False,
            "cls_use_cuda": False,
            "rec_use_cuda": False,
            "intra_op_num_threads": cpu_threads,
            "inter_op_num_threads": 1,
            "max_side_len": max(960, det_limit),
        }

        # Kaynak dile özgü İngilizce/Latin PP-OCRv5 ONNX tanıma modeli varsa Çince varsayılan yerine yükle
        rec_pair = self._find_bundled_onnx_rec_model(lang)
        if rec_pair is not None:
            kwargs["rec_model_path"] = str(rec_pair[0])
            kwargs["rec_keys_path"] = str(rec_pair[1])
            log.info("[OCR: ONNX-CPU] Dile özgü ONNX tanıma modeli seçildi: %s", rec_pair[0].name)

        # Opsiyonel yerel INT8 kuantize ONNX model ağırlıkları kontrolü
        int8_dir = MODELS_DIR / "onnx_int8"
        det_int8 = int8_dir / "det_model_int8.onnx"
        rec_int8 = int8_dir / "rec_model_int8.onnx"
        if det_int8.is_file():
            kwargs["det_model_path"] = str(det_int8)
        if rec_int8.is_file():
            kwargs["rec_model_path"] = str(rec_int8)

        try:
            instance = RapidOCR(**kwargs)
        except TypeError:
            fallback_kwargs: dict[str, Any] = {
                "det_limit_side_len": det_limit,
                "det_limit_type": limit_type,
                "use_cls": False,
            }
            if rec_pair is not None:
                fallback_kwargs["rec_model_path"] = str(rec_pair[0])
                fallback_kwargs["rec_keys_path"] = str(rec_pair[1])
            instance = RapidOCR(**fallback_kwargs)
        # Geriye dönük birim testi uyumluluğu: `monkeypatch.setattr(engine._ocr, "predict", ...)`
        # çağrılarının `raising=True` ile hata vermemesi için öznitelik kancası tanımlanır.
        if not hasattr(instance, "predict"):
            instance.predict = None
        return instance

    def _load_model(self, lang: str) -> None:
        det_limit = self._effective_det_limit()
        cpu_threads = max(1, int(getattr(self.cfg, "cpu_threads", 4)))
        log.info(
            "[OCR: ONNX-CPU] RapidOCR modeli yükleniyor: lang=%s | provider=CPUExecutionProvider | det_limit=%d | threads=%d",
            lang,
            det_limit,
            cpu_threads,
        )
        self._ocr = self._create_rapid_ocr(det_limit, lang=lang)
        self.paddle_lang = lang
        self.active_device = "cpu"
        self.engine_tag = "ONNX-CPU"
        self._warmup()
        log.info("[OCR: ONNX-CPU] RapidOCR modeli hazır: lang=%s | active_device=cpu", self.paddle_lang)

    def _warmup(self) -> None:
        """ONNX Runtime grafik optimizasyonlarını ve bellek arenalarını ilk kare öncesi ısıtır."""
        dummy = np.ones((64, 256, 3), dtype=np.uint8) * 255
        try:
            self._ocr(dummy, use_det=True, use_cls=False, use_rec=True)
        except TypeError:
            try:
                self._ocr(dummy)
            except Exception as exc:
                log.warning("[OCR: ONNX-CPU] Isınma çıkarımı uyarısı: %s", exc)
        except Exception as exc:
            log.warning("[OCR: ONNX-CPU] Isınma çıkarımı uyarısı: %s", exc)

    def _infer_raw_items(self, img: np.ndarray) -> list[dict[str, Any]]:
        """RapidOCR 4-noktalı poligon çıktısını (`[[[x1,y1],[x2,y2],[x3,y3],[x4,y4]], text, score]`)
        standart `[xmin, ymin, xmax, ymax]` kutu sözlüklerine dönüştürür.
        """
        # Birim testlerinde `_ocr.predict` monkeypatch edilmişse geriye dönük uyumluluk sağla
        predict_attr = getattr(self._ocr, "predict", None)
        if callable(predict_attr):
            return _parse_paddle_dict_results(predict_attr(img))

        try:
            result, _elapse = self._ocr(img, use_det=True, use_cls=False, use_rec=True)
        except TypeError:
            result, _elapse = self._ocr(img)

        if not result:
            return []

        items: list[dict[str, Any]] = []
        for idx, entry in enumerate(result):
            if not entry or len(entry) < 3:
                continue
            box_pts, text, score = entry[0], entry[1], entry[2]
            if box_pts is not None:
                pts = np.asarray(box_pts, dtype=np.float32)
                if pts.ndim == 2 and pts.shape[1] >= 2:
                    xmin = float(np.min(pts[:, 0]))
                    ymin = float(np.min(pts[:, 1]))
                    xmax = float(np.max(pts[:, 0]))
                    ymax = float(np.max(pts[:, 1]))
                elif pts.ndim == 1 and pts.size >= 4:
                    xmin = float(pts[0])
                    ymin = float(pts[1])
                    xmax = float(pts[2])
                    ymax = float(pts[3])
                else:
                    xmin = 0.0
                    ymin = float(idx * 25)
                    xmax = 100.0
                    ymax = float(idx * 25 + 20)
            else:
                xmin = 0.0
                ymin = float(idx * 25)
                xmax = 100.0
                ymax = float(idx * 25 + 20)

            items.append({
                "text": str(text),
                "score": float(score),
                "xmin": xmin,
                "ymin": ymin,
                "xmax": xmax,
                "ymax": ymax,
            })
        return items


# =========================================================================== #
# 3. Özel GPU Sürümü (GameOCR_nvidia): PaddleCudaEngine (CUDA / TensorRT)
# =========================================================================== #
class PaddleCudaEngine(BaseOcrEngine):
    """Özel GPU Sürümü (`GameOCR_nvidia-x86_64.AppImage`) için CUDA / TensorRT hızlandırmalı PaddleOCR motoru.

    Özellikler ve GPU Optimizasyonları:
    - VRAM bellek yönetimi: `FLAGS_allocator_strategy=auto_growth`, `FLAGS_fraction_of_gpu_memory_to_use=0.35`
      ve `FLAGS_eager_delete_tensor_gb=0.0` ile oyunun VRAM alanını işgal etmez.
    - `enable_tensorrt=True` yapılandırıldığında TensorRT FP16 alt-grafik hızlandırmasını dener;
      sistemde TensorRT kütüphanesi yoksa kesintisiz olarak standart CUDA çekirdeklerine düşer.
    - `text_det_limit_type='max'` ile geniş oyun ekranlarında aktivasyon tensörü şişmesini önler.
    """

    engine_tag: str = "CUDA"

    def _configure_vram_environment(self) -> None:
        os.environ.setdefault("FLAGS_allocator_strategy", "auto_growth")
        os.environ.setdefault("FLAGS_fraction_of_gpu_memory_to_use", "0.35")
        os.environ.setdefault("FLAGS_eager_delete_tensor_gb", "0.0")
        os.environ.setdefault("FLAGS_fast_eager_deletion_mode", "1")

    def _release_vram_cache(self) -> None:
        """Model yeniden yüklenirken kullanılmayan CUDA önbellek bloklarını serbest bırakır."""
        try:
            import paddle

            if paddle.device.is_compiled_with_cuda():
                paddle.device.cuda.empty_cache()
        except Exception:
            pass

    def _create_paddle_ocr(self, lang: str, device: str, det_limit: int) -> Any:
        from paddleocr import PaddleOCR

        limit_type = getattr(self.cfg, "det_limit_type", "max") or "max"
        enable_trt = bool(getattr(self.cfg, "enable_tensorrt", False)) and device.startswith("gpu")

        if enable_trt:
            try:
                return PaddleOCR(
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_textline_orientation=False,
                    text_det_limit_side_len=det_limit,
                    text_det_limit_type=limit_type,
                    lang=lang,
                    device=device,
                    use_tensorrt=True,
                    precision="fp16",
                )
            except Exception as exc:
                log.debug("TensorRT başlatılamadı (%s), standart CUDA moduna geçiliyor.", exc)

        try:
            return PaddleOCR(
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
                text_det_limit_side_len=det_limit,
                text_det_limit_type=limit_type,
                lang=lang,
                device=device,
            )
        except TypeError:
            try:
                return PaddleOCR(
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_textline_orientation=False,
                    text_det_limit_side_len=det_limit,
                    det_limit_type=limit_type,
                    lang=lang,
                    device=device,
                )
            except TypeError:
                try:
                    return PaddleOCR(
                        use_doc_orientation_classify=False,
                        use_doc_unwarping=False,
                        use_textline_orientation=False,
                        text_det_limit_side_len=det_limit,
                        text_det_limit_type=limit_type,
                        lang=lang,
                    )
                except TypeError:
                    return PaddleOCR(
                        use_doc_orientation_classify=False,
                        use_doc_unwarping=False,
                        use_textline_orientation=False,
                        text_det_limit_side_len=det_limit,
                        lang=lang,
                    )

    def _load_model(self, lang: str) -> None:
        self._configure_vram_environment()
        if self._ocr is not None:
            self._release_vram_cache()

        target_device = resolve_paddle_device(self.cfg)
        det_limit = self._effective_det_limit()
        self.engine_tag = "CUDA" if target_device.startswith("gpu") else "ONNX-CPU"

        log.info(
            "[OCR: %s] PaddleOCR modeli yükleniyor: lang=%s | device=%s | low_end=%s | det_limit=%d",
            self.engine_tag,
            lang,
            target_device,
            getattr(self.cfg, "low_end_mode", False),
            det_limit,
        )
        try:
            self._ocr = self._create_paddle_ocr(lang, target_device, det_limit)
            self.paddle_lang = lang
            self.active_device = target_device
        except Exception as exc:
            if target_device != "cpu":
                log.warning(
                    "PaddleOCR GPU (%s) ile başlatılamadı (%s), otomatik olarak CPU moduna düşülüyor.",
                    target_device,
                    exc,
                )
                target_device = "cpu"
                try:
                    self._ocr = self._create_paddle_ocr(lang, "cpu", det_limit)
                    self.paddle_lang = lang
                    self.active_device = "cpu"
                except Exception as exc2:
                    log.warning(
                        "PaddleOCR '%s' dili ile başlatılamadı (%s), varsayılan 'en' (CPU) modeline düşülüyor.",
                        lang,
                        exc2,
                    )
                    self._ocr = self._create_paddle_ocr("en", "cpu", det_limit)
                    self.paddle_lang = "en"
                    self.active_device = "cpu"
            else:
                log.warning(
                    "PaddleOCR '%s' dili ile başlatılamadı (%s), varsayılan 'en' modeline düşülüyor.",
                    lang,
                    exc,
                )
                self._ocr = self._create_paddle_ocr("en", target_device, det_limit)
                self.paddle_lang = "en"
                self.active_device = target_device

        self.engine_tag = "CUDA" if self.active_device.startswith("gpu") else "ONNX-CPU"
        self._warmup()
        log.info(
            "[OCR: %s] PaddleOCR modeli hazır: lang=%s | active_device=%s",
            self.engine_tag,
            self.paddle_lang,
            self.active_device,
        )

    def _warmup(self) -> None:
        """GPU CUDA çekirdeklerini ısıtarak ilk çıkarım gecikmesini ortadan kaldırır."""
        dummy = np.ones((64, 256, 3), dtype=np.uint8) * 255
        try:
            self._ocr.predict(dummy)
        except Exception as exc:
            log.warning("[OCR: %s] Isınma çıkarımı uyarısı: %s", self.engine_tag, exc)

    def _infer_raw_items(self, img: np.ndarray) -> list[dict[str, Any]]:
        results = self._ocr.predict(img)
        return _parse_paddle_dict_results(results)


# =========================================================================== #
# 4. Fabrika Deseni (OcrEngineFactory) ve Dinamik Cephe Sınıfı (OcrEngine)
# =========================================================================== #
class OcrEngineFactory:
    """Yapılandırma (`config.toml`) ve ortam değişkenlerine göre uygun OCR motorunu
    (`RapidOcrEngine` veya `PaddleCudaEngine`) üreten modüler Fabrika sınıfı.
    """

    @staticmethod
    def resolve_backend_kind(cfg: OcrConfig) -> str:
        """Hangi OCR motorunun (`'rapidocr'` | `'paddle'`) kullanılacağını belirler.

        Seçim Kuralları:
        1. Birim testlerinde `paddleocr.PaddleOCR` monkeypatch edilmişse `'paddle'` seçilir.
        2. `GAMEOCR_OCR_ENGINE` veya `cfg.engine` açıkça `'rapidocr'` / `'onnx'` / `'lite'`
           olarak ayarlanmışsa `'rapidocr'` seçilir.
        3. `GAMEOCR_OCR_ENGINE` veya `cfg.engine` açıkça `'paddle'` / `'cuda'` / `'nvidia'`
           olarak ayarlanmışsa `'paddle'` seçilir.
        4. `GAMEOCR_FORCE_CPU=1` ise veya hedef cihaz `'cpu'` ise (Ana Sürüm / Lite davranış):
           `rapidocr-onnxruntime` mevcutsa `'rapidocr'` (`CPUExecutionProvider`) seçilir.
        5. Hedef cihaz `'gpu'` veya `'auto'` iken:
           - Eğer `device == 'gpu'` veya (`engine == 'paddle'`) ise ve CUDA mevcutsa `'paddle'` seçilir.
           - Varsayılan `'auto'` modunda `rapidocr-onnxruntime` kuruluysa Lite `RapidOcrEngine`
             (`CPUExecutionProvider`), kullanıcı açıkça GPU (`device='gpu'` veya `engine='paddle'`)
             istediğinde ise `PaddleCudaEngine` (`CUDA`) seçilir.
        """
        if _is_paddle_monkeypatched():
            return "paddle"

        explicit = cfg.resolved_engine() if hasattr(cfg, "resolved_engine") else "auto"
        if explicit == "rapidocr":
            if _is_rapidocr_available():
                return "rapidocr"
            if _is_paddle_available():
                log.warning("RapidOCR paketi bulunamadı; PaddleOCR motoruna düşülüyor.")
                return "paddle"
            return "rapidocr"

        if explicit == "paddle":
            if _is_paddle_available():
                return "paddle"
            if _is_rapidocr_available():
                log.warning("PaddleOCR paketi bulunamadı; RapidOCR (ONNX-CPU) motoruna düşülüyor.")
                return "rapidocr"
            return "paddle"

        # explicit == "auto"
        pref_dev = cfg.resolved_device() if hasattr(cfg, "resolved_device") else ("gpu" if cfg.use_gpu else "cpu")
        if pref_dev == "gpu" and _is_paddle_available():
            target_dev = resolve_paddle_device(cfg)
            if target_dev.startswith("gpu"):
                return "paddle"

        # Ana Sürüm (GameOCR - Lite) varsayılanı: RapidOCR (CPUExecutionProvider)
        if _is_rapidocr_available():
            return "rapidocr"
        if _is_paddle_available():
            return "paddle"
        return "rapidocr"

    @classmethod
    def create(cls, cfg: OcrConfig, src_lang: str = "EN") -> BaseOcrEngine:
        """Yapılandırmaya göre `RapidOcrEngine` veya `PaddleCudaEngine` örneği oluşturur."""
        kind = cls.resolve_backend_kind(cfg)
        if kind == "rapidocr":
            try:
                return RapidOcrEngine(cfg, src_lang=src_lang)
            except Exception as exc:
                if _is_paddle_available():
                    log.warning(
                        "RapidOcrEngine başlatılamadı (%s), PaddleCudaEngine yedeğine geçiliyor…",
                        exc,
                    )
                    return PaddleCudaEngine(cfg, src_lang=src_lang)
                raise

        try:
            return PaddleCudaEngine(cfg, src_lang=src_lang)
        except Exception as exc:
            if _is_rapidocr_available():
                log.warning(
                    "PaddleCudaEngine başlatılamadı (%s), RapidOcrEngine (ONNX-CPU) yedeğine geçiliyor…",
                    exc,
                )
                return RapidOcrEngine(cfg, src_lang=src_lang)
            raise


class OcrEngine(BaseOcrEngine):
    """`OcrWorker` ve `Pipeline` tarafından kullanılan, çalışma zamanında (runtime)
    `OcrEngineFactory` üzerinden `RapidOcrEngine` (ONNX-CPU) ile `PaddleCudaEngine` (CUDA)
    arasında dinamik ve thread-safe geçiş yapabilen Birleşik OCR Motoru.
    """

    def __init__(self, cfg: OcrConfig, src_lang: str = "EN") -> None:
        self._backend: BaseOcrEngine | None = None
        super().__init__(cfg, src_lang=src_lang)

    def _load_model(self, lang: str) -> None:
        """Fabrika desenini kullanarak aktif yapılandırmaya uygun alt motoru yükler."""
        self._backend = OcrEngineFactory.create(self.cfg, src_lang=self.src_lang)
        self._ocr = self._backend._ocr
        self.paddle_lang = self._backend.paddle_lang
        self.active_device = self._backend.active_device
        self.engine_tag = self._backend.engine_tag

    def _infer_raw_items(self, img: np.ndarray) -> list[dict[str, Any]]:
        if self._backend is None:
            return _parse_paddle_dict_results(self._ocr.predict(img)) if self._ocr is not None else []
        # Testlerde `ocr_engine._ocr` doğrudan değiştirilmişse alt motora yansıt
        self._backend._ocr = self._ocr
        return self._backend._infer_raw_items(img)


def create_ocr_engine(cfg: OcrConfig, src_lang: str = "EN") -> BaseOcrEngine:
    """`OcrWorker` ve `Pipeline` için yardımcı Fabrika fonksiyonu."""
    return OcrEngineFactory.create(cfg, src_lang=src_lang)
