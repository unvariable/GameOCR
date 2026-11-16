"""Evrensel Kontrol Merkezi (ControlWindow), tepsi tema ikonu ve show_panel kısayolu testleri."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtNetwork import QLocalServer
from PyQt6.QtWidgets import QApplication

from gameocr.__main__ import _try_notify_running_instance
from gameocr.config import Config
from gameocr.i18n import set_language
from gameocr.ui.control_window import ControlWindow
from gameocr.ui.tray import get_tray_icon


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_control_window_actions_status_and_close_hides(qapp, tmp_path, monkeypatch) -> None:
    set_language("tr")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

    called: list[str] = []
    cfg = Config()
    win = ControlWindow(
        cfg=cfg,
        on_toggle_pause=lambda: called.append("pause"),
        on_select_window=lambda: called.append("window"),
        on_select_roi=lambda: called.append("roi"),
        on_toggle_overlay=lambda: called.append("overlay"),
        on_open_settings=lambda: called.append("settings"),
        on_open_history=lambda: called.append("history"),
        on_quit=lambda: called.append("quit"),
        hide_on_close=True,
    )

    win.pause_btn.click()
    win.window_btn.click()
    win.roi_btn.click()
    win.overlay_btn.click()
    win.settings_btn.click()
    win.history_btn.click()
    win.quit_btn.click()

    assert called == ["pause", "window", "roi", "overlay", "settings", "history", "quit"]

    win.update_status(backend="xcomposite", paused=True)
    assert "Duraklatıldı" in win.status_label.text()
    assert "xcomposite" in win.backend_label.text()

    # Kapatma olayı hide_on_close=True iken uygulamayı öldürmez, gizler
    win.show()
    ev = QCloseEvent()
    win.closeEvent(ev)
    assert not ev.isAccepted()
    assert not win.isVisible()

    # hide_on_close=False iken çarpı (X) doğrudan çıkış (on_quit) tetikler
    win.hide_on_close = False
    ev2 = QCloseEvent()
    win.closeEvent(ev2)
    assert ev2.isAccepted()
    assert called[-1] == "quit"


def test_tray_icon_writes_xdg_theme_png(qapp, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    icon = get_tray_icon()
    assert not icon.isNull()
    expected_png = Path(tmp_path) / "icons" / "hicolor" / "64x64" / "apps" / "gameocr.png"
    assert expected_png.exists()
    assert expected_png.stat().st_size > 100


def test_single_instance_ipc_notify(qapp) -> None:
    server_name = f"gameocr-test-ipc-{os.getpid()}"
    QLocalServer.removeServer(server_name)
    server = QLocalServer()
    assert server.listen(server_name)

    received: list[str] = []

    def _on_conn() -> None:
        conn = server.nextPendingConnection()
        if conn and conn.waitForReadyRead(200):
            received.append(bytes(conn.readAll()).decode("utf-8").strip())
            conn.disconnectFromServer()

    server.newConnection.connect(_on_conn)
    assert _try_notify_running_instance(server_name, "SHOW") is True
    qapp.processEvents()
    server.close()
    assert received == ["SHOW"]
