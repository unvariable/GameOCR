import os
import threading
import time

from PyQt6.QtWidgets import QApplication

from gameocr.config import HotkeysConfig
from gameocr.ui.hotkeys import GlobalHotkeyListener, HotkeyBridge


def test_hotkey_bridge_cross_thread():
    app = QApplication.instance() or QApplication([])

    received_actions = []

    def on_pause():
        received_actions.append("pause")

    def on_overlay():
        received_actions.append("toggle_overlay")

    callbacks = {
        "pause": on_pause,
        "toggle_overlay": on_overlay,
    }

    cfg = HotkeysConfig(enabled=False)  # Don't grab real X11/KDE keys in unit tests
    listener = GlobalHotkeyListener(cfg, callbacks)

    # Arka plan thread'inden action tetikle
    def bg():
        listener._dispatch_action("pause")
        listener._dispatch_action("toggle_overlay")

    t = threading.Thread(target=bg)
    t.start()
    t.join()

    # Qt event döngüsünü işle
    app.processEvents()

    assert "pause" in received_actions
    assert "toggle_overlay" in received_actions
