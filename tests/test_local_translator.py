"""Aşama 2: Çevrimdışı (Lokal) Çeviri Motoru ve Dil Paketi Yöneticisi birim testleri."""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication

from gameocr.config import Config, DeepLConfig
from gameocr.local_models import (
    LocalModelManager,
    LocalModelNotInstalledError,
    ModelDownloadWorker,
)
from gameocr.translator import Translator, TranslatorError
from gameocr.ui.settings_dialog import SettingsDialog


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_default_only_en_tr_installed(tmp_path: Path) -> None:
    """Varsayılan olarak yalnızca EN-TR dil paketi kurulu gelmelidir."""
    mgr = LocalModelManager(models_dir=tmp_path / "models")
    assert mgr.installed_packs() == ["EN-TR"]
    assert mgr.is_installed("EN", "TR") is True
    assert mgr.is_installed("JA", "TR") is False
    assert mgr.is_installed("EN", "DE") is False


def test_local_translate_en_tr_and_memory_lifecycle(tmp_path: Path) -> None:
    """EN-TR çevrimdışı çeviri çalışmalı ve aktif model bellekte yönetilmelidir."""
    mgr = LocalModelManager(models_dir=tmp_path / "models")
    assert mgr.active_loaded_pair() is None

    out1 = mgr.translate("Wake up, Samurai!", "EN", "TR")
    assert "samuray" in out1.lower()
    assert mgr.active_loaded_pair() == "EN-TR"

    out2 = mgr.translate("Hello world", "EN", "TR")
    assert out2.lower() == "merhaba dünya"

    mgr.unload_model()
    assert mgr.active_loaded_pair() is None


def test_uninstalled_language_pack_raises_until_downloaded(tmp_path: Path) -> None:
    """Kurulu olmayan bir dil çifti (örn. EN-DE veya JA-TR) indirilmeden çeviri yapmamalıdır."""
    mgr = LocalModelManager(models_dir=tmp_path / "models")
    with pytest.raises(LocalModelNotInstalledError):
        mgr.translate("Hello world", "EN", "DE")

    progress_steps: list[int] = []
    ok = mgr.download_pack("EN-DE", progress_cb=lambda p: progress_steps.append(p))
    assert ok is True
    assert 100 in progress_steps
    assert mgr.is_installed("EN", "DE") is True

    # İndirildikten sonra çeviri çalışmalı ve bellekteki aktif model EN-DE olmalı
    de_text = mgr.translate("Hello world", "EN", "DE")
    assert de_text.lower() == "hallo welt"
    assert mgr.active_loaded_pair() == "EN-DE"

    # Paketi kaldırma testi
    assert mgr.remove_pack("EN-DE") is True
    assert mgr.is_installed("EN", "DE") is False


def test_model_download_worker_async_signals(qapp, tmp_path: Path) -> None:
    """ModelDownloadWorker ana thread'i dondurmadan ilerleme ve tamamlanma sinyalleri üretmelidir."""
    mgr = LocalModelManager(models_dir=tmp_path / "models")
    worker = ModelDownloadWorker(mgr, "JA-TR")

    progress_events: list[tuple[str, int]] = []
    finished_events: list[tuple[str, bool, str]] = []

    worker.progressChanged.connect(lambda code, pct: progress_events.append((code, pct)))
    worker.downloadFinished.connect(lambda code, ok, msg: finished_events.append((code, ok, msg)))

    worker.run()  # Senkron test doğrulaması (QThread sinyal emisyonu)
    assert len(progress_events) >= 2
    assert progress_events[-1] == ("JA-TR", 100)
    assert len(finished_events) == 1
    assert finished_events[0][0] == "JA-TR"
    assert finished_events[0][1] is True
    assert mgr.is_installed("JA", "TR") is True


def test_translator_facade_local_and_auto_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Translator sınıfı 'local' ve 'auto_fallback' modlarında çevrimdışı motoru kullanmalıdır."""
    monkeypatch.delenv("DEEPL_AUTH_KEY", raising=False)
    mgr = LocalModelManager(models_dir=tmp_path / "models")

    # 1. Doğrudan Lokal Mod
    tr_local = Translator(DeepLConfig(auth_key=""), engine="local", local_manager=mgr)
    res = tr_local.translate("Game over", "EN", "TR")
    assert res.lower() == "oyun bitti"
    assert tr_local.last_latency_ms >= 0.0
    assert tr_local.usage() is None

    # 2. Auto-Fallback Modu (DeepL anahtarı yokken otomatik olarak lokal modele düşmeli)
    tr_auto = Translator(DeepLConfig(auth_key=""), engine="auto_fallback", local_manager=mgr)
    res_fallback = tr_auto.translate("Mission complete", "EN", "TR")
    assert res_fallback.lower() == "görev tamamlandı"

    # 3. DeepL moduna geçildiğinde lokal model bellekten boşaltılmalı
    tr_local.update_config(DeepLConfig(auth_key=""), engine="deepl")
    assert mgr.active_loaded_pair() is None
    with pytest.raises(TranslatorError):
        tr_local.translate("Hello", "EN", "TR")


def test_settings_dialog_local_packs_ui(qapp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SettingsDialog içerisindeki Lokal Dil Paketleri tablosu ve motor seçici doğru çalışmalıdır."""
    import gameocr.config as cfg_mod

    monkeypatch.setattr(cfg_mod, "CONFIG_FILE", tmp_path / "config.toml")
    mgr = LocalModelManager(models_dir=tmp_path / "models")
    cfg = Config()
    dlg = SettingsDialog(cfg, local_manager=mgr)

    # Tabloda tüm katalog listelenmeli ve ilk satır EN-TR kurulu olmalı
    assert dlg.packs_table.rowCount() >= 5
    first_row_text = dlg.packs_table.item(0, 0).text()
    assert "EN-TR" in first_row_text

    # Motoru 'local' seçip kaydetme
    idx = dlg.engine_combo.findData("local")
    dlg.engine_combo.setCurrentIndex(idx)
    dlg._save_changes()
    assert dlg.cfg.general.translation_engine == "local"


def test_local_translate_tr_en_real_ctranslate2(tmp_path: Path) -> None:
    """TR -> EN lokal çevirisi kurulduğunda '[TR-EN]' önekli sahte çıktı yerine gerçek İngilizce çeviri üretmelidir."""
    mgr = LocalModelManager(models_dir=tmp_path / "models")
    mgr.download_pack("TR-EN")
    out = mgr.translate("Yenilikten korkmaya ne gerek var?", "TR", "EN-US")
    assert "[TR-EN]" not in out
    assert any(w in out.lower() for w in ("afraid", "fear", "innovation", "why", "need"))


