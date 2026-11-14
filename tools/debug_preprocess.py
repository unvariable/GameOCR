#!/usr/bin/env python3
"""Ön işleme boru hattı görsel hata ayıklama aracı.

Belirtilen bir resim dosyasını alır, preprocess adımlarını uygular ve
sonucu bir çıktı dosyasına kaydeder.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

from gameocr.config import PreprocessConfig
from gameocr.preprocess import preprocess, to_gray, upscale, binarize, normalize_polarity


def main() -> int:
    parser = argparse.ArgumentParser(description="GameOCR Ön İşleme İnceleme Aracı")
    parser.add_argument("input_image", type=Path, help="Giriş görüntü dosyası yolu")
    parser.add_argument("--mode", default="otsu", choices=["otsu", "adaptive", "none"], help="Binarization modu")
    parser.add_argument("--scale", type=float, default=2.0, help="Büyütme katsayısı")
    parser.add_argument("--denoise", action="store_true", default=True, help="Medyan gürültü filtresi")
    parser.add_argument("--output", "-o", type=Path, default=Path("debug_output.png"), help="Çıktı dosyası")
    args = parser.parse_args()

    if not args.input_image.exists():
        print(f"[HATA] Dosya bulunamadı: {args.input_image}")
        return 1

    img = cv2.imread(str(args.input_image))
    if img is None:
        print(f"[HATA] Görüntü okunamadı: {args.input_image}")
        return 1

    cfg = PreprocessConfig(mode=args.mode, scale=args.scale, denoise=args.denoise)
    processed = preprocess(img, cfg)

    cv2.imwrite(str(args.output), processed)
    print(f"[BAŞARILI] İşlenmiş görüntü kaydedildi: {args.output} (Boyut: {processed.shape[1]}x{processed.shape[0]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
