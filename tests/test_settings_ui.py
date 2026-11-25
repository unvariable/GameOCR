import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication

from gameocr.ui.settings_dialog import HotkeyButton


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_hotkey_button_formatting(qapp):
    btn = HotkeyButton("ctrl+alt+p")
    assert "Ctrl + Alt + P" in btn.text()
    assert btn.current_shortcut() == "ctrl+alt+p"


def test_hotkey_button_record_key(qapp):
    btn = HotkeyButton("ctrl+alt+p")
    btn._start_recording()
    assert btn._is_recording is True

    # Simulate pressing 'S' with Ctrl+Alt modifiers
    event = QKeyEvent(
        QKeyEvent.Type.KeyPress,
        Qt.Key.Key_S,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier,
    )
    btn.keyPressEvent(event)

    assert btn._is_recording is False
    assert btn.current_shortcut() == "Ctrl+Alt+S"
    assert "Ctrl + Alt + S" in btn.text()


def test_hotkey_button_escape_cancels(qapp):
    btn = HotkeyButton("Ctrl+Alt+P")
    btn._start_recording()

    event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    btn.keyPressEvent(event)

    assert btn._is_recording is False
    assert btn.current_shortcut() == "Ctrl+Alt+P"


def test_settings_dialog_reset_defaults(qapp):
    from unittest.mock import patch
    from PyQt6.QtWidgets import QMessageBox
    from gameocr.config import Config
    from gameocr.ui.settings_dialog import SettingsDialog

    cfg = Config()
    cfg.overlay.opacity = 0.12
    cfg.hotkeys.pause = "Ctrl+Shift+P"
    cfg.deepl.auth_key = "secret_key"

    applied_cfgs = []
    dialog = SettingsDialog(cfg, on_applied=lambda c: applied_cfgs.append(c))
    assert dialog.reset_defaults_btn is not None

    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
        dialog._reset_to_defaults()

    assert dialog.cfg.deepl.auth_key == "secret_key"
    assert dialog.cfg.overlay.opacity == 0.72
    assert dialog.cfg.hotkeys.pause == "ctrl+alt+p"
    assert len(applied_cfgs) == 1


def test_settings_dialog_live_key_update(qapp):
    from unittest.mock import MagicMock
    from gameocr.config import Config
    from gameocr.ui.settings_dialog import SettingsDialog
    from gameocr.translator import Translator

    cfg = Config()
    cfg.deepl.auth_key = ""

    mock_trans = MagicMock(spec=Translator)
    mock_trans.cfg = cfg.deepl
    mock_trans.usage.return_value = (5000, 500000)

    dialog = SettingsDialog(cfg, translator=mock_trans)
    dialog.key_edit.setText("new_live_key:fx")
    dialog._verify_and_refresh_quota()
    dialog._refresh_quota()

    assert mock_trans.update_config.called
    assert dialog.cfg.deepl.auth_key == "new_live_key:fx"
    assert dialog.quota_bar.value() == 1  # 5000 / 500000 = 1%


def test_settings_dialog_auto_save_on_close(qapp):
    from PyQt6.QtGui import QCloseEvent
    from gameocr.config import Config
    from gameocr.ui.settings_dialog import SettingsDialog

    cfg = Config()
    cfg.deepl.auth_key = "initial_key"
    applied_cfgs = []

    dialog = SettingsDialog(cfg, on_applied=lambda c: applied_cfgs.append(c))
    dialog.key_edit.setText("updated_key:fx")

    close_ev = QCloseEvent()
    dialog.closeEvent(close_ev)

    assert len(applied_cfgs) >= 1
    assert applied_cfgs[-1].deepl.auth_key == "updated_key:fx"


def test_settings_dialog_survives_usage_exception(qapp) -> None:
    """translator.usage() beklenmeyen hata fırlatsa bile SettingsDialog çökmeden açılmalıdır."""
    from unittest.mock import MagicMock
    from gameocr.config import Config
    from gameocr.ui.settings_dialog import SettingsDialog
    from gameocr.translator import Translator

    cfg = Config()
    cfg.deepl.auth_key = "dummy-key:fx"
    mock_trans = MagicMock(spec=Translator)
    mock_trans.cfg = cfg.deepl
    mock_trans.usage.side_effect = AttributeError("'Detail' object has no attribute 'valid'")

    dialog = SettingsDialog(cfg, translator=mock_trans)
    assert dialog.quota_bar.value() == 0
    dialog.close()


def test_settings_dialog_async_quota_close_detach_and_win32_labels(qapp, monkeypatch) -> None:
    """Aşama 33: Yavaş DeepL kota sorgusu açılışı bloklamamalı, indirme thread'i varken
    kapanışta 0xc0000409 önlenmeli ve Windows'ta DWM blur etiketi gösterilmelidir.
    """
    import threading
    import time
    from unittest.mock import MagicMock
    from PyQt6.QtCore import QThread
    from PyQt6.QtGui import QCloseEvent
    from gameocr.config import Config
    import gameocr.ui.settings_dialog as sd_mod
    from gameocr.translator import Translator

    gate = threading.Event()
    cfg = Config()
    cfg.deepl.auth_key = "dummy-key:fx"
    mock_trans = MagicMock(spec=Translator)
    mock_trans.cfg = cfg.deepl

    def slow_usage():
        gate.wait(timeout=1.5)
        return (25000, 500000)

    mock_trans.usage.side_effect = slow_usage

    monkeypatch.setattr(sd_mod.sys, "platform", "win32")
    t0 = time.monotonic()
    dialog = sd_mod.SettingsDialog(cfg, translator=mock_trans)
    elapsed = time.monotonic() - t0
    assert elapsed < 0.4
    assert "DWM" in dialog.blur_check.text()
    assert "KWin" not in dialog.blur_check.text()
    assert dialog.blur_strength_slider.isVisible() is False

    gate.set()
    deadline = time.monotonic() + 1.5
    while dialog.quota_bar.value() != 5 and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    assert dialog.quota_bar.value() == 5

    # Çalışan QThread varken dialog kapatılınca parent'tan ayrılıp çökmemeli
    worker_stop = threading.Event()

    class DummyWorker(QThread):
        def run(self) -> None:
            worker_stop.wait(timeout=1.0)

    w = DummyWorker(dialog)
    w.start()
    dialog._ocr_download_worker = w  # type: ignore[assignment]
    dialog.closeEvent(QCloseEvent())

    assert w.parent() is None
    assert dialog._ocr_download_worker is None
    worker_stop.set()
    w.wait(1500)
    qapp.processEvents()



