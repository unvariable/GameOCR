import os
import threading
import time

from PyQt6.QtWidgets import QApplication

from gameocr.config import HotkeysConfig
from gameocr.ui.hotkeys import GlobalHotkeyListener, HotkeyBridge, _parse_win32_shortcut


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


def test_win32_extended_vk_and_stop_joins_before_restart(monkeypatch):
    """Aşama 33: Genişletilmiş Win32 tuşları ayrıştırılmalı ve stop() yarış durumunu önlemek için thread'i beklemelidir."""
    assert _parse_win32_shortcut("ctrl+alt+space") == (0x0002 | 0x0001, 0x20)
    assert _parse_win32_shortcut("ctrl+shift+pgup") == (0x0002 | 0x0004, 0x21)
    assert _parse_win32_shortcut("alt+enter") == (0x0001, 0x0D)
    assert _parse_win32_shortcut("ctrl+alt+-") == (0x0002 | 0x0001, 0xBD)

    listener = GlobalHotkeyListener(HotkeysConfig(enabled=True), {})
    events: list[str] = []
    started = threading.Event()

    def fake_run() -> None:
        started.set()
        while not listener._stop_event.is_set():
            time.sleep(0.01)
        time.sleep(0.05)
        events.append("old_exited")

    def fake_start() -> None:
        events.append("new_started")

    monkeypatch.setattr(listener, "_run_win32", fake_run)
    monkeypatch.setattr(listener, "start", fake_start)

    t = threading.Thread(target=fake_run, daemon=True)
    listener._xlib_thread = t
    t.start()
    assert started.wait(timeout=1.0)

    listener.update_config(HotkeysConfig(enabled=True, show_panel="ctrl+alt+g"))
    assert events == ["old_exited", "new_started"]
    assert listener._xlib_thread is None
