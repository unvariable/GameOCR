"""Logo varlıklarını düzenleyen ve çok katmanlı ``gameocr.ico`` üreten yardımcı betik.

``logo/`` dizinindeki şeffaf PNG dosyalarını ``gameocr/assets/icons/`` altına
kopyalar, ``logo_1024.png`` dosyasından Lanczos örneklemesiyle ``256x256`` ve
``512x512`` sürümleri üretir ve Windows için ``24, 32, 64, 128, 256`` katmanlı
``gameocr.ico`` dosyasını oluşturur. ``logo.kra`` kaynak dosyası kesinlikle
kopyalanmaz.
"""
from __future__ import annotations

import shutil
import struct
from pathlib import Path

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE_DIR = PROJECT_ROOT / "logo"
DEFAULT_TARGET_DIR = PROJECT_ROOT / "gameocr" / "assets" / "icons"

SOURCE_PNG_SIZES: tuple[int, ...] = (24, 32, 64, 128, 1024)
DERIVED_PNG_SIZES: tuple[int, ...] = (256, 512)
ICO_LAYER_SIZES: tuple[int, ...] = (24, 32, 64, 128, 256)


def parse_ico_layer_sizes(ico_path: Path) -> list[tuple[int, int]]:
    """İkili ``.ico`` başlığındaki (ICONDIR / ICONDIRENTRY) katman boyutlarını okur."""
    data = ico_path.read_bytes()
    if len(data) < 6:
        raise ValueError(f"Geçersiz ICO dosyası: {ico_path}")
    _reserved, image_type, count = struct.unpack_from("<HHH", data, 0)
    if image_type != 1:
        raise ValueError(f"Beklenmeyen ICO türü ({image_type}): {ico_path}")
    layers: list[tuple[int, int]] = []
    offset = 6
    for _ in range(count):
        width_byte, height_byte = struct.unpack_from("<BB", data, offset)
        width = 256 if width_byte == 0 else width_byte
        height = 256 if height_byte == 0 else height_byte
        layers.append((width, height))
        offset += 16
    return layers


def generate_icon_assets(
    source_dir: Path = DEFAULT_SOURCE_DIR,
    target_dir: Path = DEFAULT_TARGET_DIR,
) -> Path:
    """PNG ikon setini ``target_dir`` içine yerleştirir ve çok katmanlı ``gameocr.ico`` üretir."""
    target_dir.mkdir(parents=True, exist_ok=True)

    # 1. Mevcut kaynak PNG dosyalarını kopyala (logo.kra hariç tutulur)
    for size in SOURCE_PNG_SIZES:
        src = source_dir / f"logo_{size}.png"
        if not src.is_file():
            raise FileNotFoundError(f"Kaynak logo PNG bulunamadı: {src}")
        dst = target_dir / f"logo_{size}.png"
        shutil.copy2(src, dst)

    # 2. logo_1024.png kaynağından Lanczos ile 256x256 ve 512x512 üret
    master_path = source_dir / "logo_1024.png"
    with Image.open(master_path) as raw_master:
        master = raw_master.convert("RGBA")
        for size in DERIVED_PNG_SIZES:
            resized = master.resize((size, size), Image.Resampling.LANCZOS)
            resized.save(target_dir / f"logo_{size}.png", format="PNG")

    # 3. 24, 32, 64, 128, 256 katmanlı RGBA gameocr.ico üret
    ico_path = target_dir / "gameocr.ico"
    ico_images: list[Image.Image] = []
    for size in sorted(ICO_LAYER_SIZES, reverse=True):
        png_file = target_dir / f"logo_{size}.png"
        with Image.open(png_file) as img:
            ico_images.append(img.convert("RGBA"))

    # Pillow ICO yazıcısı sizes + append_images verildiğinde tam olarak istenen katmanları yazar.
    base_img = ico_images[0]
    base_img.save(
        ico_path,
        format="ICO",
        sizes=[(s, s) for s in sorted(ICO_LAYER_SIZES, reverse=True)],
        append_images=ico_images[1:],
    )

    layers = parse_ico_layer_sizes(ico_path)
    expected = {(s, s) for s in ICO_LAYER_SIZES}
    if set(layers) != expected or len(layers) != len(ICO_LAYER_SIZES):
        raise RuntimeError(
            f"gameocr.ico beklenen katmanları içermiyor: bulunan={layers}, beklenen={sorted(expected)}"
        )

    return ico_path


def main() -> int:
    ico_path = generate_icon_assets()
    layers = parse_ico_layer_sizes(ico_path)
    print(f"İkon varlıkları üretildi: {ico_path.parent}")
    print(f"gameocr.ico katmanları ({len(layers)}): {layers}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
