"""Aşama 4, 5 ve 6: Gelişmiş Loglama, build.sh ve Windows Portu birim testleri."""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

import numpy as np
import pytest

from gameocr.capture.win32_backend import Win32Backend
from gameocr.config import CaptureConfig, Config, OcrConfig
from gameocr.logging_utils import StageError, log_timing, setup_logging, timed_stage
from gameocr.ocr_engine import OcrEngine, resolve_paddle_device
from gameocr.ui.blur import enable_win32_blur
from gameocr.ui.hotkeys import _parse_win32_shortcut
from gameocr.ui.overlay import set_win32_topmost_clickthrough


def test_log_timing_and_rotating_file_handler(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """DEBUG modunda @log_timing ve timed_stage milisaniye (ms) cinsinden log üretmelidir."""
    log_dir = tmp_path / "logs"
    setup_logging("DEBUG", log_dir=log_dir)

    logger = logging.getLogger("gameocr.test_telemetry")

    @log_timing("custom_fast_op")
    def sample_func(x: int) -> int:
        return x * 2

    with caplog.at_level(logging.DEBUG):
        assert sample_func(21) == 42
        with timed_stage(logger, "pipeline_step", frame_id=7):
            pass

    joined = "\n".join(caplog.messages)
    assert "[TIMING] custom_fast_op:" in joined
    assert "ms" in joined
    assert "[TIMING] pipeline_step:" in joined
    assert (log_dir / "gameocr.log").exists()


def test_win32_shortcut_parser() -> None:
    """Windows RegisterHotKey kısayol ayrıştırıcısı değiştirici ve sanal tuş kodlarını doğru hesaplamalıdır."""
    parsed = _parse_win32_shortcut("ctrl+alt+p")
    assert parsed is not None
    mods, vk = parsed
    assert mods == (0x0002 | 0x0001)  # MOD_CONTROL | MOD_ALT
    assert vk == ord("P")

    parsed_f = _parse_win32_shortcut("ctrl+shift+f10")
    assert parsed_f is not None
    mods_f, vk_f = parsed_f
    assert mods_f == (0x0002 | 0x0004)
    assert vk_f == 0x70 + 9


def test_win32_backend_mocked_capture(monkeypatch: pytest.MonkeyPatch) -> None:
    """Win32Backend sahte (mock) MSS ile tam ekran ve ROI karelerini yakalayabilmelidir."""
    cfg = CaptureConfig(backend="win32", roi=[0.1, 0.2, 0.5, 0.4])
    backend = Win32Backend(cfg)

    class FakeSct:
        monitors = [
            {"left": 0, "top": 0, "width": 1920, "height": 1080},
            {"left": 0, "top": 0, "width": 1000, "height": 500},
        ]

        def grab(self, region: dict[str, int]) -> np.ndarray:
            h, w = region["height"], region["width"]
            return np.full((h, w, 4), 128, dtype=np.uint8)

        def close(self) -> None:
            pass

    monkeypatch.setattr(backend, "_sct", lambda: FakeSct())
    backend.open()
    assert backend.source_geometry() == (0, 0, 1000, 500)

    full = backend.grab_full()
    assert full is not None and full.shape == (500, 1000, 3)

    roi_img = backend.grab_roi(cfg.roi)
    assert roi_img is not None and roi_img.shape == (200, 500, 3)
    backend.close()


def test_win32_blur_and_topmost_safe_on_non_windows() -> None:
    """Windows DWM blur ve topmost fonksiyonları Linux üzerinde çökmeden False döndürmelidir."""
    assert enable_win32_blur(0) is False
    assert set_win32_topmost_clickthrough(0) is False


def test_interactive_build_sh_wizard() -> None:
    """build.sh interaktif modda masaüstü ortamı, görüntü sunucusu, GPU ve derleyici seçimlerini kabul etmelidir."""
    script = Path(__file__).resolve().parent.parent / "build.sh"
    assert script.exists()

    # Sırasıyla: 2 (GNOME), 1 (Wayland), 2 (AMD), 2 (Nuitka)
    proc = subprocess.run(
        [str(script), "--dry-run"],
        input="2\n1\n2\n2\n",
        capture_output=True,
        text=True,
        check=True,
        timeout=10.0,
    )
    out = proc.stdout
    assert "gnome" in out
    assert "wayland" in out
    assert "amd" in out
    assert "nuitka" in out
    assert "[DRY-RUN]" in out

    # Windows (Beta) interaktif seçim testi: 5 (Windows Beta), 1 (NVIDIA), 1 (PyInstaller)
    proc_win = subprocess.run(
        [str(script), "--dry-run"],
        input="5\n1\n1\n",
        capture_output=True,
        text=True,
        check=True,
        timeout=10.0,
    )
    out_win = proc_win.stdout
    assert "windows" in out_win
    assert "win32" in out_win
    assert "pyinstaller" in out_win
    assert "[DRY-RUN]" in out_win


def test_ocr_device_cpu_gpu_selection_and_low_end_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Aşama 9: GPU/CPU/Otomatik cihaz seçimi ve Düşük Sistem (Low-End) modu doğru çalışmalıdır."""
    monkeypatch.delenv("GAMEOCR_FORCE_CPU", raising=False)

    cfg_cpu = OcrConfig(device="cpu", low_end_mode=True, det_limit_side_len=960)
    assert cfg_cpu.resolved_device() == "cpu"
    assert resolve_paddle_device(cfg_cpu) == "cpu"

    cfg_gpu = OcrConfig(device="gpu", low_end_mode=False, det_limit_side_len=960)
    assert cfg_gpu.resolved_device() == "gpu"

    # GAMEOCR_FORCE_CPU=1 ortam değişkeni (Universal-Lite AppImage) her zaman CPU'ya zorlamalıdır
    monkeypatch.setenv("GAMEOCR_FORCE_CPU", "1")
    assert cfg_gpu.resolved_device() == "cpu"
    assert resolve_paddle_device(cfg_gpu) == "cpu"
    monkeypatch.delenv("GAMEOCR_FORCE_CPU", raising=False)

    # OcrEngine.update_config canlı cihaz/mod değişimini algılamalı ve low_end_mode'da det_limit_side_len'i 640 ile sınırlamalıdır
    reload_calls: list[str] = []
    monkeypatch.setattr(OcrEngine, "_load_model", lambda self, lang: reload_calls.append(f"{lang}:{self.cfg.device}:{self._effective_det_limit()}"))

    engine = OcrEngine(OcrConfig(device="auto", low_end_mode=False, det_limit_side_len=960), "EN")
    assert reload_calls == ["en:auto:960"]

    engine.update_config(OcrConfig(device="cpu", low_end_mode=True, det_limit_side_len=960), "EN")
    assert engine._effective_det_limit() == 640
    assert reload_calls[-1] == "en:cpu:640"


def test_build_sh_windows_beta_auto_python312_and_dual_appimage() -> None:
    """Aşama 10 & 11: build.sh çift sürüm (dual) AppImage profilini ve otomatik Python 3.12 kuruculu Windows paketini üretmelidir."""
    root = Path(__file__).resolve().parent.parent
    script = root / "build.sh"

    # Dual AppImage dry-run testi
    proc_dual = subprocess.run(
        [str(script), "--de", "kde", "--display", "wayland", "--gpu", "dual", "--compiler", "pyinstaller", "--dry-run"],
        capture_output=True,
        text=True,
        check=True,
        timeout=10.0,
    )
    assert "dual" in proc_dual.stdout
    assert "[DRY-RUN]" in proc_dual.stdout

    # Windows (Beta) paketinde otomatik Python 3.12 kurulum betiklerinin üretildiğini doğrula
    proc_win = subprocess.run(
        [str(script), "--platform", "windows", "--gpu", "nvidia", "--compiler", "pyinstaller", "--dry-run"],
        capture_output=True,
        text=True,
        check=True,
        timeout=10.0,
    )
    assert "setup-windows-beta.ps1" in proc_win.stdout
    assert "build-windows-beta.bat" in proc_win.stdout

    win_dist = root / "dist" / "gameocr-windows-win32-nvidia"
    bat_text = (win_dist / "build-windows-beta.bat").read_text(encoding="utf-8")
    ps1_text = (win_dist / "setup-windows-beta.ps1").read_text(encoding="utf-8")

    assert "Python.Python.3.12" in bat_text
    assert "python-3.12.8-amd64.exe" in bat_text
    assert "Find-Python312" in ps1_text
    assert "Python.Python.3.12" in ps1_text


def test_build_sh_universal_and_nvidia_appimage_targets() -> None:
    """Aşama 15: build.sh varsayılan olarak GameOCR-Universal-x86_64.AppImage (ONNX-CPU) ve
    --gpu nvidia ile GameOCR_nvidia-x86_64.AppImage paket hedeflerini barındırmalıdır.
    """
    root = Path(__file__).resolve().parent.parent
    script = root / "build.sh"
    script_text = script.read_text(encoding="utf-8")

    assert "GameOCR-Universal-x86_64.AppImage" in script_text
    assert "GameOCR_nvidia-x86_64.AppImage" in script_text
    assert "rapidocr_onnxruntime" in script_text

    # Varsayılan CPU/Lite dry-run: paddle dışlanmalı ve rapidocr_onnxruntime toplanmalıdır
    proc_lite = subprocess.run(
        [str(script), "--de", "kde", "--display", "wayland", "--gpu", "cpu", "--compiler", "pyinstaller", "--dry-run"],
        capture_output=True,
        text=True,
        check=True,
        timeout=10.0,
    )
    assert "rapidocr_onnxruntime" in proc_lite.stdout
    assert "--exclude-module paddle" in proc_lite.stdout

    # NVIDIA dry-run: paddle binary'leri toplanmalıdır
    proc_nv = subprocess.run(
        [str(script), "--de", "kde", "--display", "wayland", "--gpu", "nvidia", "--compiler", "pyinstaller", "--dry-run"],
        capture_output=True,
        text=True,
        check=True,
        timeout=10.0,
    )
    assert "--collect-binaries paddle" in proc_nv.stdout


def test_windows_single_exe_ascii_scripts_and_meipass_models(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Aşama 16: Windows derleme betikleri saf ASCII olmalı (PowerShell 5.1 AmpersandNotAllowed koruması),
    CPU modunda --onefile GameOCR-Universal-x64.exe üretmeli ve _MEIPASS/models dizinini bulabilmelidir.
    """
    root = Path(__file__).resolve().parent.parent
    script = root / "build.sh"

    proc_win_cpu = subprocess.run(
        [str(script), "--platform", "windows", "--gpu", "cpu", "--compiler", "pyinstaller", "--dry-run"],
        capture_output=True,
        text=True,
        check=True,
        timeout=10.0,
    )
    assert "setup-windows-beta.ps1" in proc_win_cpu.stdout

    win_cpu_dist = root / "dist" / "gameocr-windows-win32-cpu"
    ps1_bytes = (win_cpu_dist / "setup-windows-beta.ps1").read_bytes()
    bat_bytes = (win_cpu_dist / "build-windows-beta.bat").read_bytes()

    # PowerShell 5.1 BOM'suz UTF-8 tırnak bozulmasını önlemek için saf ASCII zorunluluğu
    assert all(b < 128 for b in ps1_bytes), "setup-windows-beta.ps1 ASCII olmayan bayt içeriyor!"
    assert all(b < 128 for b in bat_bytes), "build-windows-beta.bat ASCII olmayan bayt içeriyor!"

    ps1_text = ps1_bytes.decode("ascii")
    bat_text = bat_bytes.decode("ascii")
    assert "--onefile" in ps1_text
    assert "GameOCR-Universal-x64" in ps1_text
    assert "rapidocr-onnxruntime" in ps1_text
    assert "--onefile" in bat_text
    assert "GameOCR-Universal-x64.exe" in bat_text

    # PyInstaller --onefile _MEIPASS model dizini tespiti
    import sys
    import gameocr.local_models as lm

    fake_meipass = tmp_path / "_MEI12345"
    bundle_dir = fake_meipass / "models" / "en-tr" / "translate-en_tr-1_5"
    model_sub = bundle_dir / "model"
    model_sub.mkdir(parents=True)
    (model_sub / "model.bin").write_bytes(b"ct2")
    (bundle_dir / "sentencepiece.model").write_bytes(b"spm")

    monkeypatch.setattr(sys, "_MEIPASS", str(fake_meipass), raising=False)
    monkeypatch.setattr(lm, "MODELS_DIR", tmp_path / "no_system_models")
    monkeypatch.setattr(lm, "PROJECT_ROOT", tmp_path / "no_project_models")
    monkeypatch.delenv("GAMEOCR_BUNDLED_MODELS_DIR", raising=False)

    mgr = lm.LocalModelManager(models_dir=tmp_path / "empty_user_models")
    found = mgr._find_ct2_bundle("EN-TR")
    assert found is not None
    assert found[0] == model_sub


def test_win32_overlay_mask_and_large_roi_upscale_skip(monkeypatch: pytest.MonkeyPatch) -> None:
    """Aşama 22: Windows'ta OverlayWindow WA_TranslucentBackground yerine setMask kullanmalı
    (SetWindowDisplayAffinity uyumu) ve upscale() büyük ROI'leri 2x büyüterek OCR'ı yavaşlatmamalıdır.
    """
    import os
    import numpy as np
    from PyQt6.QtCore import QRectF, Qt
    from PyQt6.QtWidgets import QApplication
    from gameocr.config import OverlayConfig
    from gameocr.preprocess import upscale
    import gameocr.ui.overlay as overlay_mod

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    _app = QApplication.instance() or QApplication([])

    # 1) Büyük ROI (385x719) büyütülmemeli, küçük altyazı bandı (100x400) büyütülmeli
    large_roi = np.zeros((385, 719), dtype=np.uint8)
    assert upscale(large_roi, 2.0).shape == (385, 719)

    small_roi = np.zeros((100, 400), dtype=np.uint8)
    assert upscale(small_roi, 2.0).shape == (200, 800)

    # 2) Windows simülasyonu: WA_TranslucentBackground kapalı + setMask aktif
    monkeypatch.setattr(overlay_mod.sys, "platform", "win32")
    monkeypatch.setattr(overlay_mod, "set_win32_topmost_clickthrough", lambda hwnd: True)
    monkeypatch.setattr(overlay_mod, "ensure_kwin_rule", lambda: None)
    ov = overlay_mod.OverlayWindow(OverlayConfig())
    assert not ov.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    ov._sync_win32_mask(QRectF(10.0, 20.0, 200.0, 80.0))
    assert ov._last_win32_mask_rect == (10, 20, 200, 80)
    assert not ov.mask().isEmpty()
    ov.close()







