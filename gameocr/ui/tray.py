"""Sistem tepsisi (System Tray Icon) entegrasyonu.

Arka planda çalışan uygulamayı kontrol etmek için hızlı menü,
durum ipucu ve bildirim desteği sunar.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QMenu, QMessageBox, QSystemTrayIcon, QWidget

from ..cache_store import CacheStore
from ..config import Config
from ..i18n import t

log = logging.getLogger(__name__)


def create_default_tray_icon() -> QIcon:
    """Tepsi için 64x64 boyutunda şık bir GameOCR vektörel rozet ikonu üretir."""
    pix = QPixmap(64, 64)
    pix.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Koyu mor / mavi degrade arka plan dairesi
    painter.setBrush(QColor(40, 44, 70))
    painter.setPen(QColor(0, 220, 150))
    painter.drawRoundedRect(4, 4, 56, 56, 16, 16)

    # "G" harfi
    painter.setFont(QFont("sans-serif", 26, QFont.Weight.Bold))
    painter.setPen(QColor(255, 255, 255))
    painter.drawText(0, 0, 64, 64, Qt.AlignmentFlag.AlignCenter, "G")
    painter.end()

    return QIcon(pix)


def get_tray_icon() -> QIcon:
    """Tema ikonu (`gameocr`) yükler; yoksa kullanıcı ikon dizinine PNG yazıp fallback döner.

    Cinnamon (`xapp-sn-watcher`) ve GNOME AppIndicator gibi StatusNotifierHost
    bileşenleri `IconName` boş olduğunda ikonu göstermeyebildiği için tema ikonu
    sağlamak tüm masaüstü ortamlarında görünürlüğü artırır.
    """
    fallback = create_default_tray_icon()
    try:
        data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        icon_file = data_home / "icons" / "hicolor" / "64x64" / "apps" / "gameocr.png"
        if not icon_file.exists():
            icon_file.parent.mkdir(parents=True, exist_ok=True)
            pix = fallback.pixmap(64, 64)
            pix.save(str(icon_file), "PNG")
        themed = QIcon.fromTheme("gameocr")
        if not themed.isNull():
            return themed
        if icon_file.exists():
            return QIcon(str(icon_file))
    except Exception as exc:
        log.debug("Tema ikonu hazırlanamadı, bellek içi ikon kullanılacak: %s", exc)
    return fallback


class TrayManager:
    def __init__(
        self,
        cfg: Config,
        cache_store: CacheStore | None = None,
        on_toggle_pause: Callable[[], None] | None = None,
        on_select_window: Callable[[], None] | None = None,
        on_select_roi: Callable[[], None] | None = None,
        on_open_settings: Callable[[], None] | None = None,
        on_open_history: Callable[[], None] | None = None,
        on_toggle_overlay: Callable[[bool], None] | None = None,
        on_show_control: Callable[[], None] | None = None,
        on_quit: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        self.cfg = cfg
        self.cache_store = cache_store
        self.on_toggle_pause = on_toggle_pause
        self.on_select_window = on_select_window
        self.on_select_roi = on_select_roi
        self.on_open_settings = on_open_settings
        self.on_open_history = on_open_history
        self.on_toggle_overlay = on_toggle_overlay
        self.on_show_control = on_show_control
        self.on_quit = on_quit

        self.tray = QSystemTrayIcon(parent)
        self.tray.setIcon(get_tray_icon())

        self.backend_name = "auto"
        self.is_paused = False
        self.quota_info = ""

        self._build_menu()
        self._update_tooltip()
        self.tray.activated.connect(self._handle_activated)
        self.tray.show()

    def _build_menu(self) -> None:
        menu = QMenu()

        # Bilgi başlığı
        self.header_action = QAction(f"{t('app.name')} [{self.cfg.general.source_lang} → {self.cfg.general.target_lang}]", menu)
        self.header_action.setEnabled(False)
        menu.addAction(self.header_action)

        # Kontrol Merkezi
        show_panel_action = QAction(t("tray.show_panel"), menu)
        if self.on_show_control:
            show_panel_action.triggered.connect(self.on_show_control)
        menu.addAction(show_panel_action)
        menu.addSeparator()

        # Başlat / Duraklat
        self.pause_action = QAction(t("tray.pause"), menu)
        self.pause_action.triggered.connect(self._handle_toggle_pause)
        menu.addAction(self.pause_action)

        # Program İzle / Pencere Seç
        self.window_action = QAction(t("tray.select_window"), menu)
        if self.on_select_window:
            self.window_action.triggered.connect(self.on_select_window)
        menu.addAction(self.window_action)

        # ROI Seç
        roi_action = QAction(t("tray.select_roi"), menu)
        if self.on_select_roi:
            roi_action.triggered.connect(self.on_select_roi)
        menu.addAction(roi_action)

        # Overlay Görünürlüğü
        self.overlay_action = QAction(t("tray.toggle_overlay"), menu)
        self.overlay_action.setCheckable(True)
        self.overlay_action.toggled.connect(self._handle_toggle_overlay)
        menu.addAction(self.overlay_action)

        menu.addSeparator()

        # Çeviri Geçmişi
        history_action = QAction(t("tray.history"), menu)
        if self.on_open_history:
            history_action.triggered.connect(self.on_open_history)
        menu.addAction(history_action)

        # Ayarlar
        settings_action = QAction(t("tray.settings"), menu)
        if self.on_open_settings:
            settings_action.triggered.connect(self.on_open_settings)
        menu.addAction(settings_action)

        menu.addSeparator()

        # Çıkış
        quit_action = QAction(t("tray.quit"), menu)
        if self.on_quit:
            quit_action.triggered.connect(self.on_quit)
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)

    def _handle_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            if self.on_show_control:
                self.on_show_control()

    def _handle_toggle_pause(self) -> None:
        self.is_paused = not self.is_paused
        self.pause_action.setText(t("tray.resume") if self.is_paused else t("tray.pause"))
        if self.on_toggle_pause:
            self.on_toggle_pause()
        self._update_tooltip()

    def _handle_toggle_overlay(self, checked: bool) -> None:
        if self.on_toggle_overlay:
            # checked=True ise overlay gizlenecek (visible=False)
            self.on_toggle_overlay(not checked)

    def update_config(self, cfg: Config) -> None:
        self.cfg = cfg
        self._build_menu()
        self._update_tooltip()

    def update_status(self, backend: str | None = None, quota: str | None = None) -> None:
        if backend:
            self.backend_name = backend
        if quota:
            self.quota_info = quota
        self._update_tooltip()

    def _update_tooltip(self) -> None:
        src = self.cfg.general.source_lang
        tgt = self.cfg.general.target_lang
        state_str = t("tray.paused_badge") if self.is_paused else "Aktif"
        tt = f"GameOCR ({state_str})\nDil: {src} → {tgt}\nYakalama: {self.backend_name}"
        if self.quota_info:
            tt += f"\nDeepL: {self.quota_info}"
        self.tray.setToolTip(tt)
        self.header_action.setText(f"GameOCR [{src} → {tgt}] ({state_str})")

    def show_notification(self, title: str, message: str) -> None:
        self.tray.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 3000)
