#!/usr/bin/env python3
"""Sistem ve GPU doğrulama aracı.

PaddlePaddle GPU derlemesi, CUDA kullanılabilirliği ve aktif grafik aygıtını
kontrol eder.
"""
from __future__ import annotations

import sys


def main() -> int:
    print("=" * 60)
    print(" GameOCR - GPU ve Sistem Kontrolü")
    print("=" * 60)
    print(f"Python sürümü   : {sys.version.split()[0]}")

    try:
        import paddle
    except ImportError as exc:
        print(f"[HATA] PaddlePaddle içe aktarılamadı: {exc}")
        return 1

    print(f"Paddle sürümü   : {paddle.__version__}")
    cuda_compiled = paddle.device.is_compiled_with_cuda()
    print(f"CUDA derlemesi  : {'EVET' if cuda_compiled else 'HAYIR'}")

    if not cuda_compiled:
        print("[UYARI] PaddlePaddle CUDA desteği olmadan derlenmiş!")
        return 1

    dev_count = paddle.device.cuda.device_count()
    print(f"Kullanılabilir GPU: {dev_count}")

    if dev_count == 0:
        print("[HATA] CUDA derlemesi mevcut fakat sistemde GPU bulunamadı!")
        return 1

    for idx in range(dev_count):
        prop = paddle.device.cuda.get_device_properties(idx)
        total_mem_gb = prop.total_memory / (1024**3)
        print(f"  GPU #{idx}: {prop.name} ({total_mem_gb:.2f} GB VRAM)")

    # Küçük bir tensör testi
    try:
        t = paddle.to_tensor([1.0, 2.0, 3.0], place=paddle.CUDAPlace(0))
        res = (t * 2.0).numpy()
        print(f"GPU İşlem Testi : BAŞARILI (sonuç: {res})")
    except Exception as exc:
        print(f"[HATA] GPU işlem testi başarısız: {exc}")
        return 1

    print("=" * 60)
    print("Tüm GPU kontrolleri başarıyla tamamlandı.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
