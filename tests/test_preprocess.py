import numpy as np

from gameocr.config import PreprocessConfig
from gameocr.preprocess import (
    ChangeGate,
    binarize,
    normalize_polarity,
    preprocess,
    to_gray,
    upscale,
)


def test_to_gray():
    bgr = np.zeros((20, 20, 3), dtype=np.uint8)
    bgr[:, :] = [50, 100, 150]
    gray = to_gray(bgr)
    assert gray.shape == (20, 20)
    assert gray.ndim == 2

    # Halihazırda griyse dokunulmaz
    gray2 = to_gray(gray)
    assert np.array_equal(gray, gray2)


def test_upscale():
    img = np.zeros((10, 10), dtype=np.uint8)
    up = upscale(img, 2.0)
    assert up.shape == (20, 20)

    no_scale = upscale(img, 1.0)
    assert no_scale.shape == (10, 10)


def test_binarize_and_polarity():
    # Koyu zemin üzerinde açık yazıyı simüle et
    img = np.zeros((50, 50), dtype=np.uint8)
    img[20:30, 20:30] = 255  # ortada beyaz kutu

    bin_img = binarize(img, "otsu")
    assert set(np.unique(bin_img)).issubset({0, 255})

    # Çoğunluk siyah olduğu için normalize_polarity ters çevirmeli (beyaz zemin siyah yazı)
    norm = normalize_polarity(bin_img)
    # Beyaz piksellerin sayısı daha fazla olmalı
    assert np.count_nonzero(norm == 255) > norm.size / 2


def test_preprocess_pipeline():
    cfg = PreprocessConfig(mode="otsu", scale=2.0, denoise=True)
    img = np.zeros((30, 80, 3), dtype=np.uint8)
    img[10:20, 10:70] = 200

    out = preprocess(img, cfg)
    # 3 kanallı BGR ve 2x ölçeklenmiş olmalı
    assert out.shape == (60, 160, 3)
    assert out.dtype == np.uint8


def test_change_gate():
    gate = ChangeGate(threshold_percent=1.5)
    f1 = np.zeros((100, 100, 3), dtype=np.uint8)

    # İlk kare daima True döner
    assert gate.changed(f1) is True

    # Birebir aynı kare değişmedi
    assert gate.changed(f1) is False

    # Küçük bir gürültü eşiğin altındaysa False döner
    noisy = f1.copy()
    noisy[0:2, 0:2] = 5
    assert gate.changed(noisy) is False

    # Anlamlı bir değişiklik (yeni altyazı)
    f2 = f1.copy()
    f2[40:60, 20:80] = 255
    assert gate.changed(f2) is True
