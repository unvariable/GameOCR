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

    # Windows paketinde otomatik Python 3.12 kurulum betiklerinin üretildiğini doğrula
    proc_win = subprocess.run(
        [str(script), "--platform", "windows", "--gpu", "nvidia", "--compiler", "pyinstaller", "--dry-run"],
        capture_output=True,
        text=True,
        check=True,
        timeout=10.0,
    )
    assert "setup-windows.ps1" in proc_win.stdout
    assert "build-windows.bat" in proc_win.stdout

    win_dist = root / "dist" / "gameocr-windows-win32-nvidia"
    bat_text = (win_dist / "build-windows.bat").read_text(encoding="utf-8")
    ps1_text = (win_dist / "setup-windows.ps1").read_text(encoding="utf-8")

    assert "Python.Python.3.12" in bat_text
    assert "python-3.12.8-amd64.exe" in bat_text
    assert "Find-Python312" in ps1_text
    assert "Python.Python.3.12" in ps1_text
    assert "Invoke-Expression" not in ps1_text


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
    assert "setup-windows.ps1" in proc_win_cpu.stdout

    win_cpu_dist = root / "dist" / "gameocr-windows-win32-cpu"
    ps1_bytes = (win_cpu_dist / "setup-windows.ps1").read_bytes()
    bat_bytes = (win_cpu_dist / "build-windows.bat").read_bytes()

    # PowerShell 5.1 BOM'suz UTF-8 tırnak bozulmasını önlemek için saf ASCII zorunluluğu
    assert all(b < 128 for b in ps1_bytes), "setup-windows.ps1 ASCII olmayan bayt içeriyor!"
    assert all(b < 128 for b in bat_bytes), "build-windows.bat ASCII olmayan bayt içeriyor!"

    ps1_text = ps1_bytes.decode("ascii")
    bat_text = bat_bytes.decode("ascii")
    assert "Invoke-Expression" not in ps1_text
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


def test_win32_overlay_mask_updates_before_paint_no_gray_clipping(monkeypatch: pytest.MonkeyPatch) -> None:
    """Aşama 28: Kısa altyazı görünürken araya CLEAR girmeden daha geniş/uzun yeni altyazı
    geldiğinde maske paintEvent() ÖNCESİNDE büyümeli, paintEvent() içinde setMask/setWindowOpacity
    çağrılmamalı ve genişleyen alanda açık gri (#F0F0F0) sızıntı kalmamalıdır.
    """
    import os
    from PyQt6.QtWidgets import QApplication
    from gameocr.config import OverlayConfig
    from gameocr.messages import TextStyleMeta, UiKind, UiMessage
    import gameocr.ui.overlay as overlay_mod

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    _app = QApplication.instance() or QApplication([])

    monkeypatch.setattr(overlay_mod.sys, "platform", "win32")
    monkeypatch.setattr(overlay_mod, "set_win32_topmost_clickthrough", lambda hwnd: True)
    monkeypatch.setattr(overlay_mod, "ensure_kwin_rule", lambda: None)

    ov = overlay_mod.OverlayWindow(OverlayConfig(opacity=0.0, exact_alignment=True))
    ov.setGeometry(0, 0, 900, 160)
    ov.show()

    # 1) Kısa 1 satırlık altyazı
    meta_short = TextStyleMeta(
        bbox_rel=(0.02, 0.10, 0.25, 0.22),
        line_height_px=24,
        text_color_hex="#60D0FF",
        bg_color_hex="#282830",
    )
    ov._handle_ui_message(UiMessage(UiKind.SHOW, text="Kısa cümle.", data=meta_short))
    ov._anim.stop()
    ov._opacity = 1.0
    m1 = ov._last_win32_mask_rect
    assert m1 is not None

    # 2) Doğrudan (CLEAR olmadan) daha geniş ve 2 satırlık altyazı
    meta_long = TextStyleMeta(
        bbox_rel=(0.02, 0.10, 0.80, 0.65),
        line_height_px=24,
        text_color_hex="#60D0FF",
        bg_color_hex="#282830",
    )
    ov._handle_ui_message(
        UiMessage(
            UiKind.SHOW,
            text="Ama eğer olsaydı... Neden? Kimsenin posterleri değiştirmek için ne sebebi olabilir ki?",
            data=meta_long,
        )
    )
    m2 = ov._last_win32_mask_rect
    assert m2 is not None
    assert m2[2] > m1[2] and m2[3] > m1[3]

    # 3) paintEvent() sırasında setMask / setWindowOpacity çağrılmamalı (spy)
    calls: list[str] = []
    orig_set_mask = ov.setMask
    orig_set_opacity = ov.setWindowOpacity

    def _spy_set_mask(*args, **kwargs):
        calls.append("setMask")
        return orig_set_mask(*args, **kwargs)

    def _spy_set_opacity(*args, **kwargs):
        calls.append("setWindowOpacity")
        return orig_set_opacity(*args, **kwargs)

    monkeypatch.setattr(ov, "setMask", _spy_set_mask)
    monkeypatch.setattr(ov, "setWindowOpacity", _spy_set_opacity)

    img = ov.grab().toImage()
    assert calls == []

    # 4) Eski m1 dışında kalan, yeni m2 içindeki sağ-alt piksel koyu arka planla (#282830) boyanmış olmalı
    px = m2[0] + m2[2] - 4
    py = m2[1] + m2[3] - 4
    c = img.pixelColor(px, py)
    assert max(c.red(), c.green(), c.blue()) < 100
    ov.close()


def test_win32_backend_window_isolation_printwindow_and_no_monitor_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Aşama 32: Win32Backend pencere seçiliyse PrintWindow ile izole okur,
    pencere örtülü/gizli/simge durumunda asla monitöre geri düşmez.
    """
    import gameocr.capture.win32_backend as wb

    cfg = CaptureConfig(backend="win32", win32_hwnd=0x1234, roi=[0.0, 0.5, 1.0, 0.5])
    backend = wb.Win32Backend(cfg)

    mss_calls: list[dict[str, int]] = []

    class FakeSct:
        monitors = [
            {"left": 0, "top": 0, "width": 1920, "height": 1080},
            {"left": 0, "top": 0, "width": 1000, "height": 500},
        ]

        def grab(self, region: dict[str, int]) -> np.ndarray:
            mss_calls.append(dict(region))
            return np.full((region["height"], region["width"], 4), 200, dtype=np.uint8)

        def close(self) -> None:
            pass

    monkeypatch.setattr(backend, "_sct", lambda: FakeSct())
    monkeypatch.setattr(wb, "is_win32_window_alive", lambda hwnd: hwnd == 0x1234)
    monkeypatch.setattr(wb, "get_win32_window_title", lambda hwnd: "Test Game Window")
    monkeypatch.setattr(wb.sys, "platform", "win32")

    win_rect: wb.Rect | None = (100, 80, 640, 360)
    monkeypatch.setattr(wb, "get_win32_window_rect", lambda hwnd: win_rect if hwnd == 0x1234 else None)

    occ_ratio = 0.0
    monkeypatch.setattr(wb, "get_win32_rect_occlusion_ratio", lambda hwnd, rect: occ_ratio)

    pw_frame: np.ndarray | None = np.full((360, 640, 3), 77, dtype=np.uint8)
    monkeypatch.setattr(wb, "capture_win32_window_printwindow", lambda hwnd, rect: pw_frame)

    backend.open()
    assert "Test Game Window" in backend.name
    assert backend.source_geometry() == (100, 80, 640, 360)

    # 1) PrintWindow aktifken mss.grab hiç çağrılmamalı
    roi_img = backend.grab_roi(cfg.roi)
    assert roi_img is not None and roi_img.shape == (180, 640, 3)
    assert int(roi_img[0, 0, 0]) == 77
    assert mss_calls == []

    # 2) Z-order örtülme oranı doğrulaması (0%, kısmi ve çoklu örtücü ile >= %75)
    assert wb.compute_rect_occlusion_ratio((100, 100, 200, 100), []) == 0.0
    partial = wb.compute_rect_occlusion_ratio((100, 100, 200, 100), [(100, 100, 100, 100)])
    assert 0.35 <= partial <= 0.65
    multi = wb.compute_rect_occlusion_ratio(
        (100, 100, 200, 100),
        [(100, 100, 100, 100), (200, 100, 80, 100)],
    )
    assert multi >= 0.75

    # 3) Hedef ROI >= %75 örtülüyse PrintWindow bile okuma döndürmez
    occ_ratio = 0.80
    assert backend.grab_roi(cfg.roi) is None
    assert mss_calls == []

    # 4) PrintWindow siyah/başarısız ise: yalnızca örtülme <= %5 iken MSS yedeğine düşer
    pw_frame = None
    occ_ratio = 0.40
    assert backend.grab_roi(cfg.roi) is None
    assert mss_calls == []

    occ_ratio = 0.0
    fallback_img = backend.grab_roi(cfg.roi)
    assert fallback_img is not None and fallback_img.shape == (180, 640, 3)
    assert len(mss_calls) == 1

    # 5) Pencere simge durumunda veya kapalı (win_rect=None) iken ASLA monitöre düşmemeli
    win_rect = None
    assert backend.source_geometry() is None
    assert backend.grab_roi(cfg.roi) is None

    # 6) forget_source() sonrası monitör moduna temiz geçiş
    backend.forget_source()
    assert backend.window_id == 0
    assert backend.source_geometry() == (0, 0, 1000, 500)
    backend.close()


def test_capture_worker_clears_overlay_and_resets_when_window_hidden_or_reselected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Aşama 32: CaptureWorker hedef pencere gizlendiğinde/örtüldüğünde CLEAR + RESET_STATE
    yayınlamalı, pencere geri gelince GEOMETRY yenilemeli ve RESELECT_WINDOW(0) ile tam ekrana dönmelidir.
    """
    import queue
    import threading
    import time
    from gameocr.capture.base import CaptureBackend
    from gameocr.messages import Control, ControlKind, UiKind, UiMessage
    from gameocr.workers import CaptureWorker
    import gameocr.workers as workers_mod

    class FakeWindowBackend(CaptureBackend):
        name = "Win32 Pencere: FakeGame"

        def __init__(self) -> None:
            self.window_id = 0x5555
            self.visible = True
            self.closed = False

        def open(self) -> None:
            pass

        def close(self) -> None:
            pass

        def forget_source(self) -> None:
            self.window_id = 0
            self.name = "Win32 Tam Ekran (Monitör)"

        def persist_state(self, cfg: CaptureConfig) -> None:
            cfg.win32_hwnd = self.window_id

        def is_window_closed(self) -> bool:
            return self.closed

        def source_geometry(self):
            if self.window_id == 0:
                return (0, 0, 1920, 1080)
            return (100, 100, 800, 600) if self.visible else None

        def grab_full(self):
            return np.full((600, 800, 3), 50, dtype=np.uint8) if self.visible else None

        def grab_roi(self, roi):
            if self.window_id == 0:
                return np.full((100, 200, 3), 90, dtype=np.uint8)
            return np.full((100, 200, 3), 50, dtype=np.uint8) if self.visible else None

    monkeypatch.setattr(workers_mod.sys, "platform", "win32")
    monkeypatch.setattr(workers_mod, "save_config", lambda cfg: None)

    cfg = Config()
    cfg.capture.win32_hwnd = 0x5555
    cfg.capture.roi = [0.1, 0.5, 0.8, 0.2]
    cfg.capture.fps = 30.0

    backend = FakeWindowBackend()
    frame_q: queue.Queue = queue.Queue(maxsize=1)
    ui_q: queue.Queue[UiMessage] = queue.Queue()
    ctrl_q: queue.Queue[Control] = queue.Queue()
    ocr_ctrl_q: queue.Queue[Control] = queue.Queue()
    filter_ctrl_q: queue.Queue[Control] = queue.Queue()
    stop_event = threading.Event()

    cw = CaptureWorker(
        backend=backend,
        cfg=cfg,
        frame_q=frame_q,
        ui_q=ui_q,
        control_q=ctrl_q,
        stop_event=stop_event,
        ocr_ctrl_q=ocr_ctrl_q,
        filter_ctrl_q=filter_ctrl_q,
    )
    cw.start()
    try:
        time.sleep(0.12)
        assert not frame_q.empty()

        # Pencere gizlendiğinde CLEAR + RESET_STATE yayınlanmalı
        backend.visible = False
        time.sleep(0.12)
        ui_msgs: list[UiMessage] = []
        while not ui_q.empty():
            ui_msgs.append(ui_q.get_nowait())
        assert any(m.kind == UiKind.CLEAR for m in ui_msgs)
        assert not ocr_ctrl_q.empty() and ocr_ctrl_q.get_nowait().kind == ControlKind.RESET_STATE
        assert not filter_ctrl_q.empty() and filter_ctrl_q.get_nowait().kind == ControlKind.RESET_STATE

        # Pencere geri geldiğinde GEOMETRY yeniden iletilmeli
        backend.visible = True
        time.sleep(0.12)
        ui_msgs.clear()
        while not ui_q.empty():
            ui_msgs.append(ui_q.get_nowait())
        assert any(m.kind == UiKind.GEOMETRY for m in ui_msgs)

        # RESELECT_WINDOW(0) ile monitör moduna geçiş
        ctrl_q.put(Control(ControlKind.RESELECT_WINDOW, 0))
        time.sleep(0.12)
        assert backend.window_id == 0
        assert cfg.capture.win32_hwnd == 0
    finally:
        stop_event.set()
        cw.join(timeout=2.0)


def test_roi_selector_maps_coordinates_relative_to_selected_window() -> None:
    """Aşama 32: RoiSelectorWindow belirli bir source_rect verildiğinde seçimi
    ekran yerine o pencerenin koordinatlarına oranlamalıdır.
    """
    import os
    from PyQt6.QtCore import QPoint
    from PyQt6.QtWidgets import QApplication
    from gameocr.ui.roi_selector import RoiSelectorWindow

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    _app = QApplication.instance() or QApplication([])

    captured: list[list[float]] = []
    sel = RoiSelectorWindow(
        on_selected=lambda roi: captured.append(roi),
        source_rect=(200, 100, 800, 600),
        source_label="Target Game",
    )
    sel._start_pos = QPoint(300, 400)
    sel._current_pos = QPoint(699, 549)
    sel._confirm_selection()

    assert len(captured) == 1
    assert captured[0] == pytest.approx([0.125, 0.5, 0.5, 0.25], abs=0.005)
    sel.close()


def test_windows_single_instance_ipc_name_deterministic(monkeypatch: pytest.MonkeyPatch) -> None:
    """Aşama 33: os.getuid olmayan Windows'ta IPC adı PID yerine kullanıcı adına göre kararlı olmalıdır."""
    import os
    import gameocr.__main__ as main_mod

    monkeypatch.delattr(os, "getuid", raising=False)
    monkeypatch.setenv("USERDOMAIN", "DESKTOP-TEST")
    monkeypatch.setenv("USERNAME", "Taner Şahin")

    monkeypatch.setattr(os, "getpid", lambda: 1111)
    name1 = main_mod._ipc_server_name()
    monkeypatch.setattr(os, "getpid", lambda: 9999)
    name2 = main_mod._ipc_server_name()

    assert name1 == name2
    assert name1.startswith("gameocr-control-v1-")
    assert name1.isascii()


def test_win32_mixed_dpi_multimonitor_and_high_dpi_font(monkeypatch: pytest.MonkeyPatch) -> None:
    """Aşama 33: Karışık DPI çoklu monitörde fiziksel->mantıksal dönüşüm ve High-DPI font ölçekleme."""
    import os
    from PyQt6.QtCore import QRect
    from PyQt6.QtWidgets import QApplication
    from gameocr.config import OverlayConfig
    from gameocr.messages import TextStyleMeta
    import gameocr.capture.win32_backend as wb
    import gameocr.ui.overlay as overlay_mod

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    _app = QApplication.instance() or QApplication([])

    class FakeScreen:
        def __init__(self, name: str, geo: QRect, dpr: float) -> None:
            self._name = name
            self._geo = geo
            self._dpr = dpr

        def name(self) -> str:
            return self._name

        def geometry(self) -> QRect:
            return self._geo

        def devicePixelRatio(self) -> float:
            return self._dpr

    scr1 = FakeScreen("\\\\.\\DISPLAY1", QRect(0, 0, 1280, 720), 1.5)
    scr2 = FakeScreen("\\\\.\\DISPLAY2", QRect(1280, 0, 1920, 1080), 1.0)
    scr_neg = FakeScreen("\\\\.\\DISPLAY3", QRect(-1920, 0, 1920, 1080), 1.0)

    monkeypatch.setattr(overlay_mod.sys, "platform", "win32")
    monkeypatch.setattr(overlay_mod.QApplication, "screens", staticmethod(lambda: [scr1, scr2, scr_neg]))
    monkeypatch.setattr(overlay_mod.QApplication, "primaryScreen", staticmethod(lambda: scr1))
    monkeypatch.setattr(
        wb,
        "get_win32_monitors",
        lambda: [
            ("\\\\.\\DISPLAY1", (0, 0, 1920, 1080)),
            ("\\\\.\\DISPLAY2", (1920, 0, 1920, 1080)),
            ("\\\\.\\DISPLAY3", (-1920, 0, 1920, 1080)),
        ],
    )

    # Sağdaki 2. monitörde (100% DPI, fiziksel x=2120) ve soldaki negatif monitörde (x=-1720) doğrulama
    assert overlay_mod.win32_physical_rect_to_qt_logical((2120, 200, 600, 120)) == (1480, 200, 600, 120)
    assert overlay_mod.win32_physical_rect_to_qt_logical((-1720, 100, 500, 100)) == (-1720, 100, 500, 100)
    # 1. monitörde (150% DPI): fiziksel 300x150 -> mantıksal 200x100
    assert overlay_mod.win32_physical_rect_to_qt_logical((300, 150, 600, 150)) == (200, 100, 400, 100)

    monkeypatch.setattr(overlay_mod, "set_win32_topmost_clickthrough", lambda hwnd: True)
    monkeypatch.setattr(overlay_mod, "ensure_kwin_rule", lambda: None)
    ov = overlay_mod.OverlayWindow(OverlayConfig(exact_alignment=True, match_font_size=True))
    ov.setGeometry(0, 0, 800, 200)
    ov._style_meta = TextStyleMeta(bbox_rel=(0.05, 0.1, 0.5, 0.3), line_height_px=30)
    monkeypatch.setattr(ov, "devicePixelRatioF", lambda: 1.5)
    _p, _tr, font, _tc, _al, mode = ov.compute_render_layout(800.0, 200.0, "Merhaba")
    assert mode == "exact"
    assert font.pixelSize() == 20
    ov.close()


def test_win32_colorkey_transparent_mode_and_roi_selector_no_black_box(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Aşama 33: Standart mod opacity=0.0 LWA_COLORKEY kullanmalı ve Windows ROI seçici
    CompositionMode_Clear yüzünden siyah kutu çizmemelidir.
    """
    import os
    from PyQt6.QtCore import QPoint
    from PyQt6.QtWidgets import QApplication
    from gameocr.config import OverlayConfig
    from gameocr.messages import UiKind, UiMessage
    import gameocr.ui.overlay as overlay_mod
    import gameocr.ui.roi_selector as roi_mod

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    _app = QApplication.instance() or QApplication([])

    monkeypatch.setattr(overlay_mod.sys, "platform", "win32")
    monkeypatch.setattr(overlay_mod, "set_win32_topmost_clickthrough", lambda hwnd: True)
    monkeypatch.setattr(overlay_mod, "ensure_kwin_rule", lambda: None)
    colorkey_calls: list[tuple[int, int]] = []
    monkeypatch.setattr(
        overlay_mod,
        "set_win32_layered_colorkey",
        lambda hwnd, key, alpha: colorkey_calls.append((key, alpha)) or True,
    )

    ov = overlay_mod.OverlayWindow(OverlayConfig(opacity=0.0, exact_alignment=False))
    ov.setGeometry(0, 0, 400, 100)
    ov.show()
    ov._handle_ui_message(UiMessage(UiKind.SHOW, text="Şeffaf altyazı"))
    ov._anim.stop()
    ov._opacity = 1.0
    ov._prepare_win32_surface()

    assert ov._win32_colorkey_active is True
    assert any(k == 0x00010101 for k, _a in colorkey_calls)
    ov_img = ov.grab().toImage()
    corner = ov_img.pixelColor(4, 4)
    assert (corner.red(), corner.green(), corner.blue()) == (1, 1, 1)
    ov.close()

    # RoiSelectorWindow Windows çizimi siyah (0,0,0) kutu üretmemeli
    monkeypatch.setattr(roi_mod.sys, "platform", "win32")
    sel = roi_mod.RoiSelectorWindow(monitor_rect=(0, 0, 800, 600))
    sel._start_pos = QPoint(100, 100)
    sel._current_pos = QPoint(300, 220)
    sel.show()
    sel_img = sel.grab().toImage()
    inside_sel = sel_img.pixelColor(200, 160)
    assert (inside_sel.red(), inside_sel.green(), inside_sel.blue()) != (0, 0, 0)
    assert inside_sel.green() >= 90
    sel.close()


def test_win32_printwindow_second_attempt_crop_and_dxcam_secondary_monitor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Aşama 33: PrintWindow 2. denemesi GetWindowRect ofsetini kullanmalı ve DXcam
    ikincil monitörde (left != 0) atlanıp MSS'e düşmelidir.
    """
    import types
    import gameocr.capture.win32_backend as wb

    monkeypatch.setattr(wb.sys, "platform", "win32")

    class FakeApi:
        class _User32:
            @staticmethod
            def IsWindow(_hwnd: int) -> bool:
                return True

        user32 = _User32()

    monkeypatch.setattr(wb._Win32Api, "get", classmethod(lambda cls: FakeApi()))
    monkeypatch.setattr(wb, "get_win32_raw_window_rect", lambda hwnd: (93, 77, 654, 370))
    monkeypatch.setattr(wb, "get_win32_outer_rect", lambda hwnd: (100, 80, 640, 360))

    def fake_pw(_api, _hwnd: int, w: int, h: int, flags: int):
        if flags & wb.PW_CLIENTONLY:
            return None
        img = np.zeros((h, w, 3), dtype=np.uint8)
        # İstemci alanı (cx=100, cy=80 -> GetWindowRect (93,77)'ye göre ox=7, oy=3)
        img[3 : 3 + 360, 7 : 7 + 640] = (11, 22, 33)
        return img

    monkeypatch.setattr(wb, "_print_window_to_bgr", fake_pw)
    cropped = wb.capture_win32_window_printwindow(0x1234, (100, 80, 640, 360))
    assert cropped is not None
    assert cropped.shape == (360, 640, 3)
    assert tuple(cropped[0, 0]) == (11, 22, 33)

    # İkincil monitörde (left=1920) DXcam kesinlikle çağrılmamalı, MSS kullanılmalı
    dxcam_calls: list[tuple[int, int, int, int]] = []
    mss_calls: list[dict[str, int]] = []

    class FakeSct:
        monitors = [
            {"left": 0, "top": 0, "width": 3840, "height": 1080},
            {"left": 0, "top": 0, "width": 1920, "height": 1080},
            {"left": 1920, "top": 0, "width": 1920, "height": 1080},
        ]

        def grab(self, region: dict[str, int]) -> np.ndarray:
            mss_calls.append(dict(region))
            return np.full((region["height"], region["width"], 4), 55, dtype=np.uint8)

        def close(self) -> None:
            pass

    cfg = CaptureConfig(backend="win32", mss_monitor=2, roi=[0.0, 0.5, 0.5, 0.5])
    backend = wb.Win32Backend(cfg)
    monkeypatch.setattr(backend, "_sct", lambda: FakeSct())
    backend.open()
    backend._dxcam_camera = types.SimpleNamespace(
        grab=lambda region: dxcam_calls.append(region) or np.full((10, 10, 3), 99, dtype=np.uint8)
    )
    frame = backend.grab_roi(cfg.roi)
    assert frame is not None
    assert dxcam_calls == []
    assert len(mss_calls) == 1
    assert mss_calls[0]["left"] == 1920
    backend.close()


def test_atomic_replace_retries_permission_error_and_tray_preserves_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Aşama 33: atomic_replace geçici PermissionError'ı yeniden denemeli ve TrayManager.update_config
    duraklatma/overlay durumunu korumalıdır.
    """
    import os
    from PyQt6.QtWidgets import QApplication
    from gameocr.security import atomic_replace
    from gameocr.ui.tray import TrayManager

    src = tmp_path / "a.tmp"
    dst = tmp_path / "a.toml"
    src.write_text("ok", encoding="utf-8")

    attempts = {"n": 0}
    orig_replace = Path.replace

    def flaky_replace(self: Path, target: Path):
        if self == src and attempts["n"] < 2:
            attempts["n"] += 1
            raise PermissionError("locked by antivirus")
        return orig_replace(self, target)

    monkeypatch.setattr(Path, "replace", flaky_replace)
    atomic_replace(src, dst, retries=5, delay_s=0.005)
    assert attempts["n"] == 2
    assert dst.read_text(encoding="utf-8") == "ok"

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    _app = QApplication.instance() or QApplication([])
    tray = TrayManager(Config())
    tray.is_paused = True
    tray.set_overlay_hidden(True)
    tray.update_config(Config())
    assert tray.overlay_action.isChecked() is True
    assert "Devam" in tray.pause_action.text() or "Resume" in tray.pause_action.text()
    tray.tray.hide()









