"""Kullanıcının ekran üzerinde canlı ve anında ROI seçmesini sağlayan arayüz.

Harici komutlar (spectacle vb.) çalıştırmadan, şeffaf tam ekran pencere
ile arkadaki masaüstünü/oyunu canlı gösterir. Kullanıcı fareyle altyazı
alanını seçtiğinde oransal (0..1) koordinatlar üretilir.
"""
from __future__ import annotations

import logging
from typing import Callable

from PyQt6.QtCore import QPoint, QRect, Qt
from PyQt6.QtGui import (
    QColor,
    QFont,
    QKeyEvent,
    QMouseEvent,
    QPaintEvent,
    QPainter,
    QPen,
)
from PyQt6.QtWidgets import QApplication, QWidget

log = logging.getLogger(__name__)


class RoiSelectorWindow(QWidget):
    def __init__(
        self,
        snapshot: object = None,  # Geriye dönük uyumluluk için korundu
        on_selected: Callable[[list[float]], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.on_selected = on_selected

        self._start_pos: QPoint | None = None
        self._current_pos: QPoint | None = None
        self._is_selecting = False

        import sys as _sys

        # Şeffaf tam ekran pencere ayarları (Görev çubuğunda sekme açmaması için Tool bayrağı)
        if _sys.platform == "win32":
            # Windows'ta WA_TranslucentBackground, SetWindowDisplayAffinity'yi engeller;
            # setWindowOpacity ile şeffaflık sağlanarak self-capture önlenir.
            self.setWindowOpacity(0.42)
        else:
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )

        # Birincil ekranın boyutunu al
        screen = QApplication.primaryScreen()
        screen_geo = screen.geometry() if screen else QRect(0, 0, 1920, 1080)
        self.setGeometry(screen_geo)
        self.setFixedSize(screen_geo.width(), screen_geo.height())
        self.setCursor(Qt.CursorShape.CrossCursor)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        import sys as _sys

        if _sys.platform == "win32":
            from ..capture.win32_backend import set_win32_exclude_from_capture

            set_win32_exclude_from_capture(int(self.winId()), exclude=True)
        else:
            from .overlay import set_x11_always_on_top

            set_x11_always_on_top(int(self.winId()))
            self.showFullScreen()
        self.raise_()
        self.activateWindow()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._start_pos = event.pos()
            self._current_pos = event.pos()
            self._is_selecting = True
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._is_selecting:
            self._current_pos = event.pos()
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._is_selecting:
            self._is_selecting = False
            self._current_pos = event.pos()
            self.update()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._confirm_selection()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Escape, Qt.Key.Key_Q):
            log.info("ROI seçimi iptal edildi")
            self.close()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._confirm_selection()

    def _get_selection_rect(self) -> QRect | None:
        if self._start_pos is None or self._current_pos is None:
            return None
        return QRect(self._start_pos, self._current_pos).normalized()

    def _confirm_selection(self) -> None:
        rect = self._get_selection_rect()
        if rect is None or rect.width() < 10 or rect.height() < 10:
            log.warning("Seçilen ROI çok küçük (en az 10x10 px olmalı)")
            return

        w_total = max(1, self.width())
        h_total = max(1, self.height())

        roi = [
            float(rect.x() / w_total),
            float(rect.y() / h_total),
            float(rect.width() / w_total),
            float(rect.height() / h_total),
        ]
        log.info("ROI onaylandı: %s (px: %dx%d)", roi, rect.width(), rect.height())
        if self.on_selected:
            self.on_selected(roi)
        self.close()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()

        # 1. Tüm ekranı hafif loş yarı saydam karart (arkadaki oyun net görünür)
        painter.fillRect(0, 0, w, h, QColor(0, 0, 0, 95))

        # 2. Seçim kutusu
        rect = self._get_selection_rect()
        if rect is not None and rect.width() > 0 and rect.height() > 0:
            # Seçili alanın karartmasını sil (tamamen netleşir)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(rect, Qt.GlobalColor.transparent)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

            # Canlı yeşil seçim çerçevesi
            pen = QPen(QColor(0, 240, 150), 2.0, Qt.PenStyle.SolidLine)
            painter.setPen(pen)
            painter.drawRect(rect)

            # Piksel ölçü etiketi
            info_text = f"{rect.width()} x {rect.height()} px"
            painter.setFont(QFont("sans-serif", 10, QFont.Weight.Bold))
            painter.setPen(QColor(0, 0, 0, 220))
            label_y = rect.y() - 8 if rect.y() > 26 else rect.y() + 22
            painter.drawText(rect.x() + 7, label_y + 1, info_text)
            painter.setPen(QColor(0, 240, 150))
            painter.drawText(rect.x() + 6, label_y, info_text)

        # 3. Üst Bilgi Kartı
        banner_w, banner_h = 560, 44
        banner_x = (w - banner_w) // 2
        banner_y = 30
        banner_rect = QRect(banner_x, banner_y, banner_w, banner_h)

        painter.setBrush(QColor(15, 15, 22, 220))
        painter.setPen(QPen(QColor(255, 255, 255, 40), 1.0))
        painter.drawRoundedRect(banner_rect, 10, 10)

        from ..i18n import t
        guide_text = t("roi.hint")
        painter.setFont(QFont("sans-serif", 11, QFont.Weight.Bold))
        painter.setPen(QColor(245, 245, 247))
        painter.drawText(banner_rect, Qt.AlignmentFlag.AlignCenter, guide_text)
