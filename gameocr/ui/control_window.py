"""Evrensel Kontrol Merkezi Penceresi (ControlWindow).

Sistem tepsisinin görünmediği veya desteklenmediği masaüstü ortamlarında
(Linux Mint Cinnamon, GNOME, tiling WM'ler vb.) GameOCR'ın tüm kontrollerine
doğrudan görev çubuğu/pencere üzerinden erişimi garanti eder.
"""
from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..config import Config
from ..i18n import t
from .tray import get_tray_icon


class ControlWindow(QWidget):
    """Tüm dağıtımlarda ve masaüstlerinde garanti erişim sunan kompakt kontrol penceresi."""

    def __init__(
        self,
        cfg: Config,
        on_toggle_pause: Callable[[], None] | None = None,
        on_select_window: Callable[[], None] | None = None,
        on_select_roi: Callable[[], None] | None = None,
        on_toggle_overlay: Callable[[], None] | None = None,
        on_open_settings: Callable[[], None] | None = None,
        on_open_history: Callable[[], None] | None = None,
        on_quit: Callable[[], None] | None = None,
        hide_on_close: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.cfg = cfg
        self.on_toggle_pause = on_toggle_pause
        self.on_select_window = on_select_window
        self.on_select_roi = on_select_roi
        self.on_toggle_overlay = on_toggle_overlay
        self.on_open_settings = on_open_settings
        self.on_open_history = on_open_history
        self.on_quit = on_quit
        self.hide_on_close = hide_on_close

        self.is_paused = False
        self.overlay_visible = True
        self.backend_name = "auto"

        self.setWindowTitle(t("control.title"))
        self.setWindowIcon(get_tray_icon())
        self.setMinimumWidth(360)

        self._build_ui()
        self.refresh_labels()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        # Üst durum kartı
        status_card = QFrame()
        status_card.setFrameShape(QFrame.Shape.StyledPanel)
        status_layout = QVBoxLayout(status_card)
        status_layout.setContentsMargins(10, 8, 10, 8)
        status_layout.setSpacing(4)

        top_row = QHBoxLayout()
        self.status_label = QLabel()
        self.status_label.setStyleSheet("font-weight: bold;")
        self.lang_label = QLabel()
        self.lang_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        top_row.addWidget(self.status_label)
        top_row.addWidget(self.lang_label)

        self.backend_label = QLabel()
        status_layout.addLayout(top_row)
        status_layout.addWidget(self.backend_label)
        root.addWidget(status_card)

        # Ana işlem butonları (2 sütunlu ızgara)
        grid = QGridLayout()
        grid.setSpacing(8)

        self.pause_btn = QPushButton()
        self.pause_btn.clicked.connect(lambda: self.on_toggle_pause and self.on_toggle_pause())

        self.window_btn = QPushButton()
        self.window_btn.clicked.connect(lambda: self.on_select_window and self.on_select_window())

        self.roi_btn = QPushButton()
        self.roi_btn.clicked.connect(lambda: self.on_select_roi and self.on_select_roi())

        self.overlay_btn = QPushButton()
        self.overlay_btn.clicked.connect(lambda: self.on_toggle_overlay and self.on_toggle_overlay())

        self.settings_btn = QPushButton()
        self.settings_btn.clicked.connect(lambda: self.on_open_settings and self.on_open_settings())

        self.history_btn = QPushButton()
        self.history_btn.clicked.connect(lambda: self.on_open_history and self.on_open_history())

        for btn in (
            self.pause_btn,
            self.window_btn,
            self.roi_btn,
            self.overlay_btn,
            self.settings_btn,
            self.history_btn,
        ):
            btn.setMinimumHeight(34)

        grid.addWidget(self.pause_btn, 0, 0)
        grid.addWidget(self.window_btn, 0, 1)
        grid.addWidget(self.roi_btn, 1, 0)
        grid.addWidget(self.overlay_btn, 1, 1)
        grid.addWidget(self.settings_btn, 2, 0)
        grid.addWidget(self.history_btn, 2, 1)
        root.addLayout(grid)

        # İpucu metni
        self.tip_label = QLabel()
        self.tip_label.setWordWrap(True)
        self.tip_label.setStyleSheet("color: gray; font-size: 11px;")
        root.addWidget(self.tip_label)

        # Alt çubuk: Simge Durumuna Küçült / Çıkış
        bottom_row = QHBoxLayout()
        self.hide_btn = QPushButton()
        self.hide_btn.clicked.connect(self.showMinimized)

        self.quit_btn = QPushButton()
        self.quit_btn.clicked.connect(lambda: self.on_quit and self.on_quit())

        bottom_row.addWidget(self.hide_btn)
        bottom_row.addWidget(self.quit_btn)
        root.addLayout(bottom_row)

    def refresh_labels(self) -> None:
        self.setWindowTitle(t("control.title"))
        self.status_label.setText(
            t("control.status_paused") if self.is_paused else t("control.status_active")
        )
        self.lang_label.setText(
            t(
                "control.lang_pair",
                src=self.cfg.general.source_lang,
                tgt=self.cfg.general.target_lang,
            )
        )
        self.backend_label.setText(t("control.backend", backend=self.backend_name))

        self.pause_btn.setText(t("tray.resume") if self.is_paused else t("tray.pause"))
        self.window_btn.setText(t("tray.select_window"))
        self.roi_btn.setText(t("tray.select_roi"))
        self.overlay_btn.setText(t("tray.toggle_overlay"))
        self.settings_btn.setText(t("tray.settings"))
        self.history_btn.setText(t("tray.history"))
        self.hide_btn.setText(t("control.hide_to_tray"))
        self.quit_btn.setText(t("tray.quit"))
        shortcut = self.cfg.hotkeys.show_panel or "Ctrl+Alt+G"
        self.tip_label.setText(t("control.tip", shortcut=shortcut.upper()))

    def update_config(self, cfg: Config) -> None:
        self.cfg = cfg
        self.refresh_labels()

    def update_status(self, backend: str | None = None, paused: bool | None = None) -> None:
        if backend is not None:
            self.backend_name = backend
        if paused is not None:
            self.is_paused = paused
        self.refresh_labels()

    def bring_to_front(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        import sys as _sys

        if _sys.platform == "win32":
            from ..capture.win32_backend import set_win32_exclude_from_capture

            set_win32_exclude_from_capture(int(self.winId()), exclude=True)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if self.hide_on_close:
            event.ignore()
            self.hide()
            return
        event.accept()
        if self.on_quit:
            self.on_quit()
