"""Çalışma zamanı varlıkları için çapraz platform kaynak yolu çözümleyici.

Kaynak koddan çalıştırmayı (``uv run``, ``python -m gameocr``), tekerlek
kurulumlarını, Linux AppImage paketini ve PyInstaller (``sys._MEIPASS``) /
Nuitka dondurulmuş derlemelerini çalışma dizininden (``cwd``) bağımsız
olarak destekler.
"""
from __future__ import annotations

import sys
from pathlib import Path

APP_ICON_SIZES: tuple[int, ...] = (24, 32, 64, 128, 256, 512, 1024)
HICOLOR_ICON_SIZES: tuple[int, ...] = (24, 32, 64, 128, 256, 512)
TRAY_ICON_SIZES: tuple[int, ...] = (24, 32, 64)


def get_resource_base_dirs() -> list[Path]:
    """Öncelik sırasına göre tekilleştirilmiş kaynak kök dizinlerini döndürür."""
    candidates: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass))
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent)

    pkg_dir = Path(__file__).resolve().parent
    candidates.append(pkg_dir.parent)
    candidates.append(pkg_dir)

    seen: set[Path] = set()
    unique: list[Path] = []
    for base in candidates:
        resolved = base.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(resolved)
    return unique


def resource_path(relative_path: str | Path) -> Path:
    """Verilen göreli kaynak yolunu çalışma dizininden bağımsız olarak çözümler."""
    rel = Path(relative_path)
    if rel.is_absolute():
        return rel

    base_dirs = get_resource_base_dirs()
    for base in base_dirs:
        candidate = base / rel
        if candidate.exists():
            return candidate
        if rel.parts and rel.parts[0] == "gameocr" and base.name == "gameocr":
            nested = base / Path(*rel.parts[1:])
            if nested.exists():
                return nested

    return base_dirs[0] / rel


def icon_path(filename: str) -> Path:
    """``gameocr/assets/icons/<filename>`` yolunu çözümler."""
    return resource_path(Path("gameocr") / "assets" / "icons" / filename)


def list_app_icon_paths(
    sizes: tuple[int, ...] = APP_ICON_SIZES,
) -> list[tuple[int, Path]]:
    """Mevcut tüm çoklu çözünürlüklü PNG uygulama ikonlarını ``(boyut, yol)`` olarak listeler."""
    found: list[tuple[int, Path]] = []
    for size in sizes:
        candidate = icon_path(f"logo_{size}.png")
        if candidate.is_file():
            found.append((size, candidate))
    return found
