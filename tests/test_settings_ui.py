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



