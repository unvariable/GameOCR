"""Çalışma zamanı pencere, görev çubuğu, dock ve sistem tepsisi ikon yardımcıları.

Windows'ta ``SetCurrentProcessExplicitAppUserModelID`` ve çok katmanlı
``gameocr.ico`` ile görev çubuğu/tepsi netliğini; Linux Wayland/X11'de
``setDesktopFileName("gameocr")``, çoklu çözünürlüklü PNG seti ve
XDG ``hicolor`` tema senkronizasyonunu sağlar.
"""
from __future__ import annotations

import ctypes
import logging
import os
import shutil
import sys
from pathlib import Path

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap

from ..resources import (
    HICOLOR_ICON_SIZES,
    TRAY_ICON_SIZES,
    icon_path,
    list_app_icon_paths,
)

log = logging.getLogger(__name__)

WINDOWS_APP_USER_MODEL_ID = "GameOCR.App"
LINUX_DESKTOP_FILE_NAME = "gameocr"


def create_fallback_icon() -> QIcon:
    """Varlık dosyaları bulunamazsa acil durum 64x64 vektörel rozet ikonu üretir."""
    pix = QPixmap(64, 64)
    pix.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(40, 44, 70))
    painter.setPen(QColor(0, 220, 150))
    painter.drawRoundedRect(4, 4, 56, 56, 16, 16)
    painter.setFont(QFont("sans-serif", 26, QFont.Weight.Bold))
    painter.setPen(QColor(255, 255, 255))
    painter.drawText(0, 0, 64, 64, Qt.AlignmentFlag.AlignCenter, "G")
    painter.end()

    return QIcon(pix)


def configure_windows_app_user_model_id(
    app_id: str = WINDOWS_APP_USER_MODEL_ID,
) -> bool:
    """Windows görev çubuğunun Python yerine GameOCR ikonunu göstermesi için AppUserModelID atar."""
    if sys.platform != "win32":
        return False
    try:
        shell32 = ctypes.windll.shell32
        fn = shell32.SetCurrentProcessExplicitAppUserModelID
        if hasattr(fn, "argtypes"):
            from ctypes import wintypes

            fn.argtypes = [wintypes.LPCWSTR]
            fn.restype = ctypes.c_long
        hr = fn(app_id)
        if hr != 0:
            log.debug("SetCurrentProcessExplicitAppUserModelID dönüş kodu: %s", hr)
        return True
    except Exception as exc:
        log.debug("AppUserModelID ayarlanamadı: %s", exc)
        return False


def _build_multi_size_png_icon(sizes: tuple[int, ...] | None = None) -> QIcon:
    """Çoklu çözünürlüklü PNG dosyalarından DPI uyumlu ``QIcon`` oluşturur."""
    icon = QIcon()
    entries = list_app_icon_paths() if sizes is None else list_app_icon_paths(sizes)
    for size, path in entries:
        icon.addFile(str(path), QSize(size, size))
    return icon


def get_app_icon() -> QIcon:
    """Uygulama ve pencereler için çoklu çözünürlüklü ``QIcon`` döndürür."""
    icon = _build_multi_size_png_icon()
    if not icon.isNull():
        return icon
    return create_fallback_icon()


def sync_linux_hicolor_icons(data_home: Path | None = None) -> Path | None:
    """Paket içindeki PNG ikonları XDG ``hicolor`` tema dizinine kopyalar ve günceller.

    Eski sürümlerden kalan vektörel/yer tutucu ``gameocr.png`` dosyaları
    bayt karşılaştırmasıyla otomatik olarak güncel şeffaf logoyla değiştirilir.
    """
    base_data = data_home or Path(
        os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")
    )
    hicolor_root = base_data / "icons" / "hicolor"
    primary_64: Path | None = None
    first_synced: Path | None = None

    for size in HICOLOR_ICON_SIZES:
        src = icon_path(f"logo_{size}.png")
        if not src.is_file():
            continue
        dst = hicolor_root / f"{size}x{size}" / "apps" / "gameocr.png"
        dst.parent.mkdir(parents=True, exist_ok=True)
        needs_copy = not dst.is_file()
        if not needs_copy:
            try:
                needs_copy = dst.read_bytes() != src.read_bytes()
            except OSError:
                needs_copy = True
        if needs_copy:
            shutil.copy2(src, dst)
        if size == 64:
            primary_64 = dst
        if first_synced is None:
            first_synced = dst

    if primary_64 is None and first_synced is None:
        fallback_dst = hicolor_root / "64x64" / "apps" / "gameocr.png"
        if not fallback_dst.is_file():
            fallback_dst.parent.mkdir(parents=True, exist_ok=True)
            create_fallback_icon().pixmap(64, 64).save(str(fallback_dst), "PNG")
        return fallback_dst

    return primary_64 or first_synced


def get_tray_icon() -> QIcon:
    """Sistem tepsisi için platforma uygun (Windows ``.ico`` / Linux tema + PNG) ikon döndürür."""
    if sys.platform == "win32":
        ico_file = icon_path("gameocr.ico")
        if ico_file.is_file():
            ico_icon = QIcon(str(ico_file))
            if not ico_icon.isNull():
                return ico_icon
        tray_png = _build_multi_size_png_icon(TRAY_ICON_SIZES)
        if not tray_png.isNull():
            return tray_png
        return create_fallback_icon()

    try:
        synced = sync_linux_hicolor_icons()
        themed = QIcon.fromTheme("gameocr")
        if not themed.isNull():
            return themed
        tray_png = _build_multi_size_png_icon(TRAY_ICON_SIZES)
        if not tray_png.isNull():
            return tray_png
        if synced is not None and synced.is_file():
            return QIcon(str(synced))
    except Exception as exc:
        log.debug("Tema ikonu hazırlanamadı, bellek içi ikon kullanılacak: %s", exc)
    return create_fallback_icon()
