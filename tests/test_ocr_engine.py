import logging
import cv2
import numpy as np
import pytest

from gameocr.config import OcrConfig
from gameocr.ocr_engine import (
    BaseOcrEngine,
    OcrEngine,
    OcrEngineFactory,
    PaddleCudaEngine,
    RapidOcrEngine,
)


@pytest.fixture(scope="module")
def ocr_engine():
    cfg = OcrConfig(use_gpu=True, min_confidence=0.5, det_limit_side_len=960)
    return OcrEngine(cfg, src_lang="EN")


def test_ocr_recognize_synthetic_text(ocr_engine):
    # Beyaz zemin üzerine siyah metin çiz
    img = np.ones((80, 450, 3), dtype=np.uint8) * 255
    cv2.putText(img, "Game Over", (30, 55), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 0, 0), 3)

    text, score = ocr_engine.recognize(img)
    assert "Game Over" in text
    assert score >= 0.7


def test_ocr_recognize_blank_image(ocr_engine):
    blank = np.zeros((60, 200, 3), dtype=np.uint8)
    text, score = ocr_engine.recognize(blank)
    assert text == ""
    assert score == 0.0


def test_ocr_empty_input(ocr_engine):
    text, score = ocr_engine.recognize(None)
    assert text == ""
    assert score == 0.0

    tiny = np.zeros((4, 4, 3), dtype=np.uint8)
    text, score = ocr_engine.recognize(tiny)
    assert text == ""
    assert score == 0.0


def test_ocr_line_clustering_word_ordering(ocr_engine):
    # Test that words with slightly different ymin (e.g. ascender differences)
    # on the same line are properly clustered and sorted left-to-right (xmin)
    mock_res = [{
        "rec_texts": ["into the gym.", "Anyway! Let's get", "our asses"],
        "rec_scores": [0.99, 0.99, 0.99],
        "rec_boxes": [
            [575.0, 70.0, 780.0, 94.0],  # xmin=575, ymin=70
            [36.0, 70.0, 380.0, 94.0],    # xmin=36, ymin=70
            [395.0, 78.0, 560.0, 94.0],   # xmin=395, ymin=78 (lowercase, higher ymin)
        ],
    }]

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(ocr_engine._ocr, "predict", lambda img: mock_res)
        dummy = np.ones((100, 800, 3), dtype=np.uint8)
        text, score = ocr_engine.recognize(dummy)
        assert text == "Anyway! Let's get our asses into the gym."


def test_ocr_limit_type_max_prevents_memory_explosion(monkeypatch: pytest.MonkeyPatch) -> None:
    """Aşama 14: det_limit_type='max' geniş altyazı alanlarında 10x-15x piksel büyümesini ve bellek patlamasını engellemelidir."""
    recorded_kwargs: dict[str, object] = {}

    def mock_paddle_init(**kwargs):
        recorded_kwargs.update(kwargs)
        class DummyPaddle:
            def predict(self, img):
                return []
        return DummyPaddle()

    import paddleocr
    monkeypatch.setattr(paddleocr, "PaddleOCR", mock_paddle_init)

    cfg = OcrConfig(device="cpu", det_limit_side_len=640, det_limit_type="max")
    assert cfg.det_limit_type == "max"

    engine = OcrEngine(cfg, "EN")
    assert recorded_kwargs.get("text_det_limit_type") == "max"
    assert recorded_kwargs.get("text_det_limit_side_len") == 640


def test_dual_engine_factory_selection_and_rapidocr_polygon_parsing(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Aşama 15: OcrEngineFactory, ONNX-CPU (RapidOcrEngine) ve CUDA (PaddleCudaEngine) geçişini
    ve RapidOCR 4-noktalı poligon çıktısının TextStyleMeta'ya dönüşümünü doğrulamalıdır.
    """
    monkeypatch.delenv("GAMEOCR_FORCE_CPU", raising=False)
    monkeypatch.delenv("GAMEOCR_OCR_ENGINE", raising=False)

    # 1. Varsayılan Lite/CPU yapılandırması RapidOcrEngine (ONNX-CPU) seçmelidir
    cfg_lite = OcrConfig(engine="rapidocr", device="cpu", cpu_threads=4)
    assert cfg_lite.resolved_engine() == "rapidocr"
    assert OcrEngineFactory.resolve_backend_kind(cfg_lite) == "rapidocr"

    rapid_engine = OcrEngineFactory.create(cfg_lite, src_lang="EN")
    assert isinstance(rapid_engine, BaseOcrEngine)
    assert isinstance(rapid_engine, RapidOcrEngine)
    assert rapid_engine.engine_tag == "ONNX-CPU"
    assert rapid_engine.active_device == "cpu"

    # 2. RapidOCR 4-köşeli poligon çıktısının ([x1,y1]..[x4,y4]) satır sıralama ve TextStyleMeta testi
    mock_rapid_out = [
        [
            [[320.0, 40.0], [580.0, 40.0], [580.0, 76.0], [320.0, 76.0]],
            "world!",
            0.96,
        ],
        [
            [[40.0, 42.0], [300.0, 42.0], [300.0, 76.0], [40.0, 76.0]],
            "Hello brave",
            0.98,
        ],
    ]
    monkeypatch.setattr(rapid_engine, "_ocr", lambda img, **kw: (mock_rapid_out, [0.01, 0.0, 0.01]))

    canvas = np.zeros((120, 640, 3), dtype=np.uint8)
    cv2.putText(canvas, "Hello brave world!", (40, 70), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2)

    with caplog.at_level(logging.DEBUG):
        text, conf, meta = rapid_engine.recognize_with_meta(canvas, raw_img=canvas)

    assert text == "Hello brave world!"
    assert conf == pytest.approx(0.97, rel=1e-2)
    assert meta is not None
    assert meta.bbox_rel is not None
    assert meta.line_height_px >= 20
    assert "[OCR: ONNX-CPU]" in "\n".join(caplog.messages)

    # 3. Ortam değişkeni veya config ile NVIDIA/Paddle seçimi
    monkeypatch.setenv("GAMEOCR_OCR_ENGINE", "paddle")
    cfg_nv = OcrConfig(engine="auto", device="gpu", enable_tensorrt=False)
    assert cfg_nv.resolved_engine() == "paddle"
    assert OcrEngineFactory.resolve_backend_kind(cfg_nv) == "paddle"



