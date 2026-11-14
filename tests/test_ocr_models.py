"""Aşama 18: Çok Dilli OCR Dil Paketi İndirme Yöneticisi (`OcrModelManager`) birim testleri."""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication

from gameocr.config import Config
from gameocr.ocr_engine import RapidOcrEngine
from gameocr.ocr_models import (
    OcrModelDownloadWorker,
    OcrModelError,
    OcrModelManager,
    resolve_ocr_pack_for_lang,
)
from gameocr.ui.settings_dialog import SettingsDialog


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_default_ocr_packs_installed(tmp_path: Path) -> None:
    """Varsayılan olarak EN ve LATIN OCR paketleri kurulu gelmeli, diğerleri kurulu olmamalıdır."""
    mgr = OcrModelManager(models_dir=tmp_path / "models")
    assert mgr.installed_packs() == ["EN", "LATIN"]
    assert mgr.is_installed("EN") is True
    assert mgr.is_installed("TR") is True
    assert mgr.is_installed("DE") is True
    assert mgr.is_installed("JA") is False
    assert mgr.is_installed("KO") is False
    assert mgr.is_installed("RU") is False
    assert mgr.is_installed("AR") is False


def test_ocr_pack_download_resolve_and_remove(tmp_path: Path) -> None:
    """Farklı dillerdeki OCR paketleri (JA, KO, RU, AR) indirilebilmeli, çözümlenebilmeli ve kaldırılabilmelidir."""
    models_root = tmp_path / "models"
    mgr = OcrModelManager(models_dir=models_root)

    # İndirme öncesi Japonca paketi bulunmamalı
    assert mgr.find_onnx_model_for_lang("japan") is None
    assert RapidOcrEngine._find_bundled_onnx_rec_model("japan", models_dir=models_root) is None

    # Japonca (JA) paketini indir
    progress_steps: list[int] = []
    ok = mgr.download_pack("JA", progress_cb=lambda p: progress_steps.append(p))
    assert ok is True
    assert 100 in progress_steps
    assert mgr.is_installed("JA") is True
    assert mgr.is_installed("japan") is True

    found_ja = RapidOcrEngine._find_bundled_onnx_rec_model("japan", models_dir=models_root)
    assert found_ja is not None
    assert found_ja[0].name == "japan_rec.onnx"
    assert found_ja[1].name == "japan_dict.txt"

    # Rusça/Kiril (RU) paketini indir
    mgr.download_pack("RU")
    found_ru = RapidOcrEngine._find_bundled_onnx_rec_model("ru", models_dir=models_root)
    assert found_ru is not None
    assert found_ru[0].name == "cyrillic_rec.onnx"

    # Varsayılan paketler (EN, LATIN) silinememeli
    assert mgr.remove_pack("EN") is False
    assert mgr.remove_pack("LATIN") is False

    # İndirilen JA paketi kaldırılabilmeli
    assert mgr.remove_pack("JA") is True
    assert mgr.is_installed("JA") is False
    assert mgr.find_onnx_model_for_lang("japan") is None

    # Geçersiz paket kodu hata fırlatmalı
    with pytest.raises(OcrModelError):
        mgr.download_pack("UNKNOWN_LANG")


def test_ocr_model_download_worker_signals(qapp, tmp_path: Path) -> None:
    """OcrModelDownloadWorker arka planda ilerleme ve tamamlanma sinyalleri üretmelidir."""
    mgr = OcrModelManager(models_dir=tmp_path / "models")
    worker = OcrModelDownloadWorker(mgr, "KO")

    progress_events: list[tuple[str, int]] = []
    finished_events: list[tuple[str, bool, str]] = []

    worker.progressChanged.connect(lambda code, pct: progress_events.append((code, pct)))
    worker.downloadFinished.connect(lambda code, ok, msg: finished_events.append((code, ok, msg)))

    worker.run()
    assert len(progress_events) >= 2
    assert progress_events[-1] == ("KO", 100)
    assert len(finished_events) == 1
    assert finished_events[0] == ("KO", True, "KO")
    assert mgr.is_installed("KO") is True
    assert resolve_ocr_pack_for_lang("korean") is not None


def test_settings_dialog_ocr_packs_table_and_actions(qapp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SettingsDialog içerisindeki OCR Dil Paketleri tablosu ve indirme/kaldırma akışı doğru çalışmalıdır."""
    import gameocr.config as cfg_mod
    import gameocr.ui.settings_dialog as sd_mod

    cfg_path = tmp_path / "config.toml"
    monkeypatch.setattr(cfg_mod, "CONFIG_FILE", cfg_path)
    monkeypatch.setattr(sd_mod, "save_config", lambda c, path=cfg_path: cfg_mod.save_config(c, path))

    ocr_mgr = OcrModelManager(models_dir=tmp_path / "models")
    applied_configs: list[Config] = []
    cfg = Config()

    dlg = SettingsDialog(
        cfg,
        ocr_manager=ocr_mgr,
        on_applied=lambda updated: applied_configs.append(updated.copy()),
    )

    # Tabloda tüm 8 OCR paketi listelenmeli
    assert dlg.ocr_packs_table.rowCount() >= 8
    first_row_text = dlg.ocr_packs_table.item(0, 0).text()
    assert "[EN]" in first_row_text

    # İndirme tamamlandığında cfg.ocr.installed_ocr_packs güncellenmeli ve on_applied tetiklenmeli
    ocr_mgr.download_pack("AR")
    dlg._on_ocr_pack_download_finished("AR", True, "AR")
    assert "AR" in dlg.cfg.ocr.installed_ocr_packs
    assert len(applied_configs) == 1
    assert "AR" in applied_configs[-1].ocr.installed_ocr_packs

    # Kaldırma işlemi
    dlg._remove_ocr_pack("AR")
    assert "AR" not in dlg.cfg.ocr.installed_ocr_packs
    assert len(applied_configs) == 2


def test_publish_github_check_only_and_build_bootstrap_present() -> None:
    """publish_github.sh gizlilik denetiminden geçmeli ve build.sh otomatik kütüphane indirici içermelidir."""
    import subprocess

    root = Path(__file__).resolve().parent.parent
    pub_script = root / "publish_github.sh"
    build_script = root / "build.sh"
    assert pub_script.is_file()
    assert (root / "LICENSE").is_file()
    assert (root / "THIRD_PARTY_NOTICES.md").is_file()
    assert (root / ".gitignore").is_file()
    assert "ensure_build_prerequisites" in build_script.read_text(encoding="utf-8")

    res = subprocess.run(
        ["bash", str(pub_script), "--check-only"],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"publish_github.sh --check-only failed:\n{res.stdout}\n{res.stderr}"


