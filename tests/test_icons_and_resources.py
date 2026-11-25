"""Çoklu çözünürlüklü uygulama logosu, kaynak yolu yardımcısı ve masaüstü/paketleme testleri."""
from __future__ import annotations

import os
import subprocess
import sys
import types
from pathlib import Path

import pytest
from PIL import Image
from PyQt6.QtCore import QSize
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QApplication

import gameocr.resources as res_mod
import gameocr.ui.icons as icons_mod
from gameocr.resources import (
    APP_ICON_SIZES,
    HICOLOR_ICON_SIZES,
    icon_path,
    list_app_icon_paths,
    resource_path,
)
from gameocr.ui.icons import (
    LINUX_DESKTOP_FILE_NAME,
    WINDOWS_APP_USER_MODEL_ID,
    configure_windows_app_user_model_id,
    get_app_icon,
    get_tray_icon,
)
from tools.generate_icons import ICO_LAYER_SIZES, parse_ico_layer_sizes

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_runtime_icon_assets_and_ico_layers() -> None:
    """Tüm PNG boyutları RGBA olarak bulunmalı, gameocr.ico 5 katmanlı olmalı ve logo.kra dışlanmalıdır."""
    icons_dir = PROJECT_ROOT / "gameocr" / "assets" / "icons"
    assert icons_dir.is_dir()

    for size in APP_ICON_SIZES:
        png = icons_dir / f"logo_{size}.png"
        assert png.is_file(), f"Eksik PNG: {png}"
        with Image.open(png) as img:
            assert img.size == (size, size)
            assert img.mode == "RGBA"

    # Krita kaynak dosyası çalışma zamanı varlıklarına kesinlikle kopyalanmamalı
    assets_dir = PROJECT_ROOT / "gameocr" / "assets"
    assert not any(assets_dir.rglob("*.kra"))

    ico = icons_dir / "gameocr.ico"
    assert ico.is_file()
    layers = parse_ico_layer_sizes(ico)
    assert len(layers) == len(ICO_LAYER_SIZES)
    assert set(layers) == {(s, s) for s in ICO_LAYER_SIZES}


def test_resource_path_cwd_independent_and_meipass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """resource_path() ve icon_path() cwd değişse de doğru çözünmeli, _MEIPASS'i öncelemelidir."""
    monkeypatch.chdir(tmp_path)

    cfg_default = resource_path("config.default.toml")
    assert cfg_default.is_file()
    assert cfg_default.name == "config.default.toml"

    ico = icon_path("gameocr.ico")
    assert ico.is_file()
    assert ico.parent.name == "icons"

    pairs = list_app_icon_paths()
    assert [s for s, _ in pairs] == list(APP_ICON_SIZES)

    # PyInstaller _MEIPASS simülasyonu
    fake_meipass = tmp_path / "_MEI_test"
    fake_icons = fake_meipass / "gameocr" / "assets" / "icons"
    fake_icons.mkdir(parents=True)
    fake_ico = fake_icons / "gameocr.ico"
    fake_ico.write_bytes(b"fake-ico")

    monkeypatch.setattr(res_mod.sys, "_MEIPASS", str(fake_meipass), raising=False)
    resolved = icon_path("gameocr.ico")
    assert resolved == fake_ico.resolve()


def test_app_icon_multiresolution_and_desktop_file_name(qapp) -> None:
    """get_app_icon() çoklu boyut sunmalı ve setDesktopFileName('gameocr') çalışmalıdır."""
    icon = get_app_icon()
    assert not icon.isNull()
    available = {(sz.width(), sz.height()) for sz in icon.availableSizes()}
    assert {(24, 24), (32, 32), (64, 64), (128, 128)}.issubset(available)

    QGuiApplication.setDesktopFileName(LINUX_DESKTOP_FILE_NAME)
    assert QGuiApplication.desktopFileName() == "gameocr"


def test_tray_icon_linux_sync_and_windows_ico(
    qapp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Linux'ta eski placeholder PNG güncellenmeli; Windows'ta .ico yüklenip Linux hicolor yazılmamalıdır."""
    xdg_dir = tmp_path / "xdg_data"
    stale_64 = xdg_dir / "icons" / "hicolor" / "64x64" / "apps" / "gameocr.png"
    stale_64.parent.mkdir(parents=True)
    stale_64.write_bytes(b"stale-placeholder")

    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_dir))
    monkeypatch.setattr(icons_mod.sys, "platform", "linux")

    linux_icon = get_tray_icon()
    assert not linux_icon.isNull()

    src_64 = (PROJECT_ROOT / "gameocr" / "assets" / "icons" / "logo_64.png").read_bytes()
    assert stale_64.read_bytes() == src_64
    for size in HICOLOR_ICON_SIZES:
        target = xdg_dir / "icons" / "hicolor" / f"{size}x{size}" / "apps" / "gameocr.png"
        assert target.is_file()

    # Windows simülasyonu: ayrı XDG dizinine yazmadan doğrudan gameocr.ico yüklemeli
    win_xdg = tmp_path / "win_xdg"
    monkeypatch.setenv("XDG_DATA_HOME", str(win_xdg))
    monkeypatch.setattr(icons_mod.sys, "platform", "win32")

    win_icon = get_tray_icon()
    assert not win_icon.isNull()
    assert not win_icon.pixmap(QSize(32, 32)).isNull()
    assert not win_xdg.exists()


def test_configure_windows_app_user_model_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-Windows'ta False, mocked win32 üzerinde SetCurrentProcessExplicitAppUserModelID çağrılmalıdır."""
    monkeypatch.setattr(icons_mod.sys, "platform", "linux")
    assert configure_windows_app_user_model_id() is False

    captured: list[str] = []

    class FakeShell32:
        def SetCurrentProcessExplicitAppUserModelID(self, app_id: str) -> int:
            captured.append(app_id)
            return 0

    fake_ctypes = types.SimpleNamespace(
        windll=types.SimpleNamespace(shell32=FakeShell32())
    )
    monkeypatch.setattr(icons_mod.sys, "platform", "win32")
    monkeypatch.setattr(icons_mod, "ctypes", fake_ctypes)

    assert configure_windows_app_user_model_id() is True
    assert captured == [WINDOWS_APP_USER_MODEL_ID]


def test_spec_and_windows_build_include_ico_and_icons_pure_ascii() -> None:
    """gameocr.spec ve Windows build.sh betikleri gameocr.ico + ikon varlıklarını içermelidir."""
    spec_text = (PROJECT_ROOT / "gameocr.spec").read_text(encoding="utf-8")
    assert "gameocr/assets/icons" in spec_text
    assert "gameocr/assets/icons/gameocr.ico" in spec_text
    assert "icon=_exe_icon" in spec_text
    assert "logo.kra" not in spec_text

    script = PROJECT_ROOT / "build.sh"
    subprocess.run(
        [str(script), "--platform", "windows", "--gpu", "cpu", "--compiler", "pyinstaller", "--dry-run"],
        capture_output=True,
        text=True,
        check=True,
        timeout=10.0,
    )

    win_cpu_dist = PROJECT_ROOT / "dist" / "gameocr-windows-win32-cpu"
    ps1_bytes = (win_cpu_dist / "setup-windows.ps1").read_bytes()
    bat_bytes = (win_cpu_dist / "build-windows.bat").read_bytes()

    assert all(b < 128 for b in ps1_bytes)
    assert all(b < 128 for b in bat_bytes)

    ps1_text = ps1_bytes.decode("ascii")
    bat_text = bat_bytes.decode("ascii")
    assert "Invoke-Expression" not in ps1_text
    assert "gameocr/assets/icons;gameocr/assets/icons" in ps1_text
    assert "gameocr/assets/icons/gameocr.ico" in ps1_text
    assert "--icon" in ps1_text
    assert "gameocr/assets/icons;gameocr/assets/icons" in bat_text
    assert "gameocr/assets/icons/gameocr.ico" in bat_text
    assert "--icon" in bat_text


def test_linux_desktop_install_and_uninstall_scripts(tmp_path: Path) -> None:
    """install-desktop.sh ve uninstall-desktop.sh XDG dizininde .desktop ve tüm hicolor PNG'leri yönetmelidir."""
    install_sh = PROJECT_ROOT / "packaging" / "linux" / "install-desktop.sh"
    uninstall_sh = PROJECT_ROOT / "packaging" / "linux" / "uninstall-desktop.sh"
    desktop_src = PROJECT_ROOT / "packaging" / "linux" / "gameocr.desktop"

    assert install_sh.is_file()
    assert uninstall_sh.is_file()
    assert desktop_src.is_file()

    xdg_dir = tmp_path / "xdg_desktop_test"
    env = os.environ.copy()
    env["XDG_DATA_HOME"] = str(xdg_dir)

    subprocess.run(
        [str(install_sh), "--exec", "/opt/GameOCR/GameOCR.AppImage"],
        env=env,
        capture_output=True,
        text=True,
        check=True,
        timeout=10.0,
    )

    installed_desktop = xdg_dir / "applications" / "gameocr.desktop"
    assert installed_desktop.is_file()
    desktop_text = installed_desktop.read_text(encoding="utf-8")
    assert "Icon=gameocr" in desktop_text
    assert "StartupWMClass=gameocr" in desktop_text
    assert "Exec=/opt/GameOCR/GameOCR.AppImage" in desktop_text

    for size in (24, 32, 64, 128, 256, 512, 1024):
        assert (xdg_dir / "icons" / "hicolor" / f"{size}x{size}" / "apps" / "gameocr.png").is_file()

    subprocess.run(
        [str(uninstall_sh)],
        env=env,
        capture_output=True,
        text=True,
        check=True,
        timeout=10.0,
    )

    assert not installed_desktop.exists()
    for size in (24, 32, 64, 128, 256, 512, 1024):
        assert not (xdg_dir / "icons" / "hicolor" / f"{size}x{size}" / "apps" / "gameocr.png").exists()
