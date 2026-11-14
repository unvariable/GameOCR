"""Aşama 1: Dinamik Görsel Metin Hizalama (Boyut, Renk, Tam Koordinat) birim testleri."""
from __future__ import annotations

import os
import queue

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import cv2
import numpy as np
import pytest
from PyQt6.QtWidgets import QApplication

from gameocr.config import Config, OcrConfig, OverlayConfig
from gameocr.logging_utils import StageError, format_stage_traceback, timed_stage
from gameocr.messages import TextStyleMeta, UiKind, UiMessage
from gameocr.ocr_engine import OcrEngine, compute_style_meta, extract_text_color
from gameocr.ui.overlay import OverlayWindow
from gameocr.ui.settings_dialog import SettingsDialog


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _make_synthetic_subtitle_image(
    bg_bgr: tuple[int, int, int],
    fg_bgr: tuple[int, int, int],
    w: int = 400,
    h: int = 100,
) -> np.ndarray:
    """Belirtilen arka plan rengi üzerine kalın metin çizen sentetik BGR görüntü üretir."""
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:, :] = bg_bgr
    # Metin gövdesini temsil eden kalın harf blokları ve OpenCV yazısı
    cv2.putText(img, "HELLO WORLD", (40, 65), cv2.FONT_HERSHEY_SIMPLEX, 1.3, fg_bgr, 4)
    cv2.rectangle(img, (50, 35), (120, 65), fg_bgr, -1)
    return img


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def test_extract_text_color_yellow_on_dark() -> None:
    """Koyu arka plan üzerindeki sarı altyazı rengini doğru örneklemelidir."""
    # BGR: Koyu lacivert arka plan (20, 15, 10), Parlak sarı metin (0, 220, 255 -> RGB: 255, 220, 0)
    img = _make_synthetic_subtitle_image(bg_bgr=(20, 15, 10), fg_bgr=(0, 220, 255))
    sampled = extract_text_color(img, bbox_rel=(0.08, 0.25, 0.80, 0.55))
    r, g, b = _hex_to_rgb(sampled)
    assert r > 220
    assert g > 190
    assert b < 40


def test_extract_text_color_cyan_on_dark() -> None:
    """Koyu arka plan üzerindeki camgöbeği (cyan) konuşmacı/altyazı rengini doğru örneklemelidir."""
    # BGR: Siyah arka plan (10, 10, 10), Cyan metin (240, 230, 30 -> RGB: 30, 230, 240)
    img = _make_synthetic_subtitle_image(bg_bgr=(10, 10, 10), fg_bgr=(240, 230, 30))
    sampled = extract_text_color(img, bbox_rel=(0.08, 0.25, 0.80, 0.55))
    r, g, b = _hex_to_rgb(sampled)
    assert r < 60
    assert g > 200
    assert b > 200


def test_extract_text_color_dark_on_light_bg() -> None:
    """Açık (beyaz) arka plan üzerindeki koyu kırmızı metin rengini doğru örneklemelidir."""
    # BGR: Beyaz arka plan (245, 245, 245), Koyu kırmızı metin (20, 20, 200 -> RGB: 200, 20, 20)
    img = _make_synthetic_subtitle_image(bg_bgr=(245, 245, 245), fg_bgr=(20, 20, 200))
    sampled = extract_text_color(img, bbox_rel=(0.08, 0.25, 0.80, 0.55))
    r, g, b = _hex_to_rgb(sampled)
    assert r > 170
    assert g < 50
    assert b < 50


def test_extract_text_color_uniform_fallback() -> None:
    """Tek renk (kontrastsız) veya boş görüntüde varsayılan (fallback) rengi döndürmelidir."""
    blank = np.full((60, 200, 3), 50, dtype=np.uint8)
    assert extract_text_color(blank, fallback="#ABCDEF") == "#ABCDEF"
    assert extract_text_color(None, fallback="#123456") == "#123456"


def test_compute_style_meta_and_upscale_compensation() -> None:
    """Ön işlemede 2x büyütülmüş görüntüden orijinal satır yüksekliği ve normalize BBox doğru hesaplanmalıdır."""
    # Orijinal görüntü 100x400, 2x upscale edilmiş hali 200x800
    raw_img = _make_synthetic_subtitle_image(bg_bgr=(10, 10, 10), fg_bgr=(50, 250, 50), w=400, h=100)
    proc_shape = (200, 800, 3)

    # İşlenmiş görüntüde kutu yüksekliği 48px -> orijinalde 24px olmalı
    valid_items = [
        {"text": "Hello", "score": 0.95, "xmin": 80.0, "ymin": 50.0, "xmax": 240.0, "ymax": 98.0, "height": 48.0, "cy": 74.0},
        {"text": "world!", "score": 0.92, "xmin": 260.0, "ymin": 50.0, "xmax": 480.0, "ymax": 98.0, "height": 48.0, "cy": 74.0},
    ]

    meta = compute_style_meta(valid_items, proc_shape=proc_shape, raw_img=raw_img)
    assert meta.line_height_px == 24
    # xmin=80 / 800 = 0.1, ymin=50 / 200 = 0.25, w=(480-80)/800 = 0.5, h=(98-50)/200 = 0.24
    assert meta.bbox_rel == pytest.approx((0.1, 0.25, 0.5, 0.24), rel=1e-2)
    r, g, b = _hex_to_rgb(meta.text_color_hex)
    assert g > 200 and r < 80 and b < 80


def test_ocr_engine_recognize_with_meta_mocked(monkeypatch: pytest.MonkeyPatch) -> None:
    """OcrEngine.recognize_with_meta hem metni hem de TextStyleMeta'yı döndürmelidir."""
    monkeypatch.setattr(OcrEngine, "_load_model", lambda self, lang: None)
    engine = OcrEngine(OcrConfig(min_confidence=0.6), src_lang="EN")

    class DummyPredictor:
        def predict(self, img):
            return [{
                "rec_texts": ["Wake", "up,", "Samurai!"],
                "rec_scores": [0.98, 0.95, 0.99],
                "rec_boxes": [
                    [40, 20, 120, 52],
                    [130, 20, 180, 52],
                    [190, 20, 320, 52],
                ],
            }]

    engine._ocr = DummyPredictor()
    raw = _make_synthetic_subtitle_image(bg_bgr=(10, 10, 10), fg_bgr=(0, 240, 255), w=400, h=100)

    text, score, meta = engine.recognize_with_meta(raw, raw_img=raw)
    assert text == "Wake up, Samurai!"
    assert score == pytest.approx((0.98 + 0.95 + 0.99) / 3)
    assert meta is not None
    assert meta.line_height_px == 32
    assert meta.bbox_rel == pytest.approx((40 / 400, 20 / 100, 280 / 400, 32 / 100), rel=1e-2)


def test_overlay_exact_alignment_vs_standard_fallback(qapp) -> None:
    """exact_alignment=True iken tam koordinat/boyut/renk kullanılmalı, False iken standart panele dönmelidir."""
    ui_q: queue.Queue[UiMessage] = queue.Queue()
    cfg = OverlayConfig(
        exact_alignment=True,
        match_font_size=True,
        match_text_color=True,
        text_color="#F5F5F7",
        font_min=10,
        font_max=40,
    )
    overlay = OverlayWindow(cfg, ui_q=ui_q)
    overlay.set_roi_geometry(100, 800, 1000, 200)

    style_meta = TextStyleMeta(
        bbox_rel=(0.15, 0.30, 0.50, 0.20),
        line_height_px=28,
        text_color_hex="#FFD700",
    )
    overlay._handle_ui_message(UiMessage(UiKind.SHOW, text="Uyan, Samuray!", data=style_meta))

    # 1. Tam Hizalama (Exact Alignment = True) kontrolü
    panel_rect, text_rect, font, color, _, mode = overlay.compute_render_layout(1000.0, 200.0, "Uyan, Samuray!")
    assert mode == "exact"
    assert text_rect.x() == 150  # 0.15 * 1000
    assert text_rect.y() == 60   # 0.30 * 200
    assert font.pixelSize() == 28
    assert color.name().upper() == "#FFD700"
    assert panel_rect.width() < 1000.0  # Tam ekran yerine metni saran sıkı panel

    # 2. Ayarlar'dan Tam Hizalama kapatıldığında (exact_alignment = False) standart davranışa dönüş
    cfg.exact_alignment = False
    overlay.update_config(cfg)
    panel_rect_std, text_rect_std, _, color_std, _, mode_std = overlay.compute_render_layout(
        1000.0, 200.0, "Uyan, Samuray!"
    )
    assert mode_std == "standard"
    assert panel_rect_std.width() == 1000.0
    assert panel_rect_std.height() == 200.0
    assert text_rect_std.x() == 40  # %4 standart padding
    assert color_std.name().upper() == "#F5F5F7"


def test_settings_dialog_exact_alignment_toggle(qapp, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SettingsDialog içerisindeki Tam Hizalama onay kutuları Config nesnesini doğru güncellemelidir."""
    import gameocr.config as cfg_mod

    monkeypatch.setattr(cfg_mod, "CONFIG_FILE", tmp_path / "config.toml")
    cfg = Config()
    assert cfg.overlay.exact_alignment is True

    applied_configs: list[Config] = []
    dlg = SettingsDialog(cfg, on_applied=lambda c: applied_configs.append(c))

    assert dlg.exact_alignment_check.isChecked() is True
    assert dlg.match_font_size_check.isChecked() is True
    assert dlg.match_text_color_check.isChecked() is True

    # Kullanıcı Tam Hizalama'yı kapattığında alt seçenekler devre dışı kalmalı ve ayar kaydedilmeli
    dlg.exact_alignment_check.setChecked(False)
    assert dlg.match_font_size_check.isEnabled() is False
    assert dlg.match_text_color_check.isEnabled() is False

    dlg._save_changes()
    assert len(applied_configs) == 1
    assert applied_configs[0].overlay.exact_alignment is False


def test_stage_error_traceback_formatting() -> None:
    """StageError ve timed_stage hata durumunda aşama adını ve bağlamı içeren traceback üretmelidir."""
    import logging

    logger = logging.getLogger("test_stage")
    with pytest.raises(StageError) as exc_info:
        with timed_stage(logger, "bbox_alignment", reraise=True, roi_w=400, roi_h=100):
            raise ValueError("Sınır kutusu negatif olamaz")

    err = exc_info.value
    assert err.stage == "bbox_alignment"
    assert "roi_w=400" in str(err)
    tb_str = format_stage_traceback(err.stage, err, **err.context)
    assert "Aşama: bbox_alignment" in tb_str
    assert "Sınır kutusu negatif olamaz" in tb_str


def test_multicolor_word_extraction_and_mapping() -> None:
    """Açık renk arka plandaki siyah metin ve turuncu-kırmızı vurgu kelimesi doğru ayrıştırılmalı
    ve çevrilen Türkçe cümledeki karşılığına ('painkiller' -> 'ağrı kesici') eşlenmelidir.
    """
    from gameocr.workers import map_word_colors_to_translation

    # Açık gri arka plan (220, 220, 220), siyah ana metin (10, 10, 10) ve turuncu-kırmızı "painkiller" (20, 70, 230 BGR)
    img = np.full((80, 600, 3), 220, dtype=np.uint8)
    sentence = "Have a painkiller, it could help some."
    words = sentence.split()
    total_chars = sum(len(w) for w in words) + len(words) - 1
    x0, x1, y0, y1 = 20, 580, 15, 65
    box_w = x1 - x0
    cur = 0
    for w_str in words:
        wx0 = x0 + int(round((cur / total_chars) * box_w))
        wx1 = x0 + int(round(((cur + len(w_str)) / total_chars) * box_w))
        cur += len(w_str) + 1
        color = (20, 70, 230) if "painkiller" in w_str else (10, 10, 10)
        cv2.rectangle(img, (wx0 + 2, y0 + 8), (wx1 - 2, y1 - 8), color, -1)

    valid_items = [
        {
            "text": sentence,
            "score": 0.99,
            "xmin": float(x0),
            "ymin": float(y0),
            "xmax": float(x1),
            "ymax": float(y1),
            "height": float(y1 - y0),
            "cy": float((y0 + y1) / 2.0),
        }
    ]
    meta = compute_style_meta(valid_items, proc_shape=img.shape, raw_img=img)
    # Arka plan açık gri (#DCDCDC civarı), ana metin siyah (#0A0A0A civarı) olmalı
    bg_r, bg_g, bg_b = _hex_to_rgb(meta.bg_color_hex)
    assert bg_r > 200 and bg_g > 200 and bg_b > 200
    fg_r, fg_g, fg_b = _hex_to_rgb(meta.text_color_hex)
    assert fg_r < 30 and fg_g < 30 and fg_b < 30

    # Vurgu kelimesi olarak "painkiller" turuncu-kırmızı (#E64614) yakalanmış olmalı
    assert len(meta.word_colors) == 1
    span_word, span_hex = meta.word_colors[0]
    assert span_word == "painkiller"
    sr, sg, sb = _hex_to_rgb(span_hex)
    assert sr > 200 and sg < 100 and sb < 50

    # Çevrilen cümleye eşleştirme
    mapped = map_word_colors_to_translation(
        source_text=sentence,
        translated_text="Bir ağrı kesici al, biraz yardımcı olabilir.",
        word_colors=meta.word_colors,
        src_lang="EN",
        tgt_lang="TR",
        translator=None,
    )
    assert len(mapped) == 1
    html_out = OverlayWindow._build_highlighted_html(
        "Bir ağrı kesici al, biraz yardımcı olabilir.",
        meta.text_color_hex,
        [("ağrı kesici", span_hex)],
    )
    assert f'<span style="color: {span_hex};">ağrı kesici</span>' in html_out


def test_long_translation_auto_fits_without_clipping(qapp) -> None:
    """Dar bir kutuya uzun (3 satırlık) çeviri geldiğinde font boyutu otomatik küçülmeli ve taşmamalıdır."""
    from PyQt6.QtGui import QFontMetrics

    cfg = OverlayConfig(
        exact_alignment=True,
        match_font_size=True,
        match_text_color=True,
        font_min=10,
        font_max=36,
    )
    overlay = OverlayWindow(cfg)
    overlay.set_roi_geometry(100, 800, 600, 54)

    style_meta = TextStyleMeta(
        bbox_rel=(0.05, 0.10, 0.85, 0.75),
        line_height_px=34,
        text_color_hex="#050505",
        bg_color_hex="#DCDCDC",
    )
    long_text = (
        "İçerideki şeyler oldukça yüksek kaliteli görünüyor. "
        "Ama kim bunu burada göstermeye çalışıyor?"
    )
    overlay._handle_ui_message(UiMessage(UiKind.SHOW, text=long_text, data=style_meta))
    _, text_rect, font, _, alignment, mode = overlay.compute_render_layout(600.0, 54.0, long_text)
    assert mode == "exact"
    assert font.pixelSize() < 34  # Orijinal 34px sığmadığı için otomatik küçülmüş olmalı
    fm = QFontMetrics(font)
    bound = fm.boundingRect(text_rect, int(alignment), long_text)
    assert bound.height() <= text_rect.height()


