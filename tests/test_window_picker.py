"""Aşama 3: Dinamik Pencere Seçimi Arayüzü (Wayland Portal / X11 Pencere Listesi) birim testleri."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication, QDialog

from gameocr.config import Config
from gameocr.ui.tray import TrayManager
from gameocr.ui.window_picker import (
    WindowEntry,
    WindowPickerDialog,
    parse_xwininfo_output,
    trigger_window_selection,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


SAMPLE_XWININFO_TREE = """
xwininfo: Window id: 0x1e0 (the root window) (has no name)

  Root window id: 0x1e0 (the root window) (has no name)
  Parent window id: 0x0 (none)
     12 children:
     0x1400007 "Desktop — Plasma": ("plasmashell" "plasmashell")  1920x1080+0+0  +0+0
     0x3800001 "Cyberpunk 2077": ("steam_app_1091500" "Cyberpunk2077.exe")  1920x1080+0+0  +0+0
     0x4200010 "The Witcher 3": ("witcher3.exe" "Wine")  2560x1440+0+0  +0+0
     0x5000001 "GameOCR Overlay": ("gameocr" "GameOCR")  800x150+560+850  +560+850
     0x6000002 "Tiny Helper": ("helper" "Helper")  16x16+0+0  +0+0
"""


def test_parse_xwininfo_output_filters_and_extracts() -> None:
    """xwininfo çıktısından yalnızca gerçek oyun/uygulama pencereleri ayıklanmalıdır."""
    entries = parse_xwininfo_output(SAMPLE_XWININFO_TREE)
    assert len(entries) == 2
    assert entries[0].win_id == 0x3800001
    assert entries[0].title == "Cyberpunk 2077"
    assert entries[0].wm_class == "Cyberpunk2077.exe"
    assert entries[0].width == 1920 and entries[0].height == 1080

    assert entries[1].win_id == 0x4200010
    assert entries[1].title == "The Witcher 3"


def test_window_picker_dialog_search_and_select(qapp) -> None:
    """WindowPickerDialog arama filtresi ve pencere seçimi doğru çalışmalıdır."""
    entries = [
        WindowEntry(win_id=0x1001, title="Baldur's Gate 3", wm_class="bg3.exe", width=1920, height=1080),
        WindowEntry(win_id=0x2002, title="Elden Ring", wm_class="eldenring.exe", width=1920, height=1080),
    ]
    dlg = WindowPickerDialog(entries=entries, allow_click_pick=False)
    assert dlg.table.rowCount() == 2

    # Arama filtresi
    dlg.search_edit.setText("elden")
    assert dlg.table.rowCount() == 1
    assert dlg.table.item(0, 1).text() == "Elden Ring"

    # Seçimi onayla
    dlg._accept_selected()
    assert dlg.selected_window_id == 0x2002


def test_trigger_window_selection_wayland_vs_x11(qapp, monkeypatch: pytest.MonkeyPatch) -> None:
    """Oturum tipine göre Wayland'da portal, X11'de pencere listesi diyaloğu tetiklenmelidir."""
    portal_called = False
    selected_wids: list[int] = []

    def on_portal() -> None:
        nonlocal portal_called
        portal_called = True

    def on_wid(wid: int) -> None:
        selected_wids.append(wid)

    # 1. Wayland oturumu testi
    mode_wl = trigger_window_selection(on_portal, on_wid, force_session_type="wayland")
    assert mode_wl == "wayland"
    assert portal_called is True

    # 2. X11 oturumu testi (Dialog kabul edildiğinde wid döner)
    def fake_exec(self) -> int:
        self.selected_window_id = 0xABCDEF
        return int(QDialog.DialogCode.Accepted)

    monkeypatch.setattr(WindowPickerDialog, "exec", fake_exec)
    monkeypatch.setattr(
        "gameocr.ui.window_picker.list_x11_windows",
        lambda: [WindowEntry(win_id=0xABCDEF, title="Hades II", wm_class="hades2", width=1920, height=1080)],
    )

    mode_x11 = trigger_window_selection(on_portal, on_wid, force_session_type="x11")
    assert mode_x11 == "x11"
    assert selected_wids == [0xABCDEF]


def test_tray_select_window_action_wired(qapp) -> None:
    """Sistem tepsisi menüsünde 'Program İzle / Pencere Seç' eylemi bulunmalı ve tetiklenmelidir."""
    triggered = False

    def _on_win() -> None:
        nonlocal triggered
        triggered = True

    tray = TrayManager(Config(), on_select_window=_on_win)
    assert hasattr(tray, "window_action")
    tray.window_action.trigger()
    assert triggered is True


def test_create_backend_selects_portal_on_wayland(monkeypatch: pytest.MonkeyPatch) -> None:
    """Wayland oturumunda auto backend olarak XComposite değil PortalBackend seçilmelidir."""
    from gameocr.capture.base import OverlayHandle, create_backend
    from gameocr.capture.portal_backend import PortalBackend
    from gameocr.config import CaptureConfig

    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    cfg = CaptureConfig(backend="auto")
    backend = create_backend(cfg, OverlayHandle())
    assert isinstance(backend, PortalBackend)


def test_window_picker_fullscreen_option_and_pipeline_update_config_preserves_window(
    qapp,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """Aşama 32: WindowPickerDialog 'Tüm Ekran' seçeneğini desteklemeli ve
    Pipeline.update_config canlı win32_hwnd / roi alanlarını ezmemelidir.
    """
    from gameocr.cache_store import CacheStore
    from gameocr.pipeline import Pipeline

    # 1) WindowPickerDialog Tüm Ekran butonu testi
    entries = [WindowEntry(win_id=0x4444, title="Game Window", wm_class="game.exe", width=1280, height=720)]
    dlg = WindowPickerDialog(entries=entries, allow_click_pick=False)
    dlg._accept_full_screen()
    assert dlg.selected_full_screen is True
    assert dlg.selected_window_id == 0

    full_screen_called = False

    def fake_exec(self) -> int:
        self.selected_full_screen = True
        self.selected_window_id = 0
        return int(QDialog.DialogCode.Accepted)

    monkeypatch.setattr(WindowPickerDialog, "exec", fake_exec)
    monkeypatch.setattr("gameocr.ui.window_picker.list_x11_windows", lambda: entries)

    def nonlocal_set() -> None:
        nonlocal full_screen_called
        full_screen_called = True

    trigger_window_selection(
        on_wayland_portal=lambda: None,
        on_window_id_selected=lambda _wid: None,
        force_session_type="x11",
        on_full_screen=nonlocal_set,
    )
    assert full_screen_called is True

    # 2) Pipeline.update_config canlı win32_hwnd ve roi alanlarını korumalı
    import gameocr.pipeline as pipeline_mod
    from gameocr.capture.win32_backend import Win32Backend

    monkeypatch.setattr(pipeline_mod, "save_config", lambda cfg: None)
    monkeypatch.setattr(pipeline_mod, "OcrEngine", lambda *a, **kw: type("FakeOcr", (), {"src_lang": "EN"})())

    cfg = Config()
    cfg.capture.backend = "win32"
    cfg.capture.win32_hwnd = 0x7777
    cfg.capture.roi = [0.1, 0.2, 0.3, 0.4]

    cache = CacheStore(tmp_path / "cache.sqlite")
    try:
        import queue
        pipe = Pipeline(cfg, cache_store=cache, ui_q=queue.Queue())
        assert isinstance(pipe.backend, Win32Backend)

        stale_copy = cfg.copy()
        stale_copy.capture.win32_hwnd = 0
        stale_copy.capture.roi = [0.0, 0.0, 0.0, 0.0]
        stale_copy.general.log_level = "DEBUG"

        pipe.update_config(stale_copy)
        assert pipe.cfg.capture.win32_hwnd == 0x7777
        assert pipe.cfg.capture.roi == [0.1, 0.2, 0.3, 0.4]
        assert pipe.cfg.general.log_level == "DEBUG"
    finally:
        cache.close()



