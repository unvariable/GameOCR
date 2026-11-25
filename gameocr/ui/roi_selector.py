"""Kullanıcının ekran üzerinde canlı ve anında ROI seçmesini sağlayan arayüz.

Harici komutlar (spectacle vb.) çalıştırmadan, şeffaf tam ekran pencere
ile arkadaki masaüstünü/oyunu canlı gösterir. Kullanıcı fareyle altyazı
alanını seçtiğinde oransal (0..1) koordinatlar üretilir. Belirli bir
pencere seçiliyse koordinatlar doğrudan o pencerenin geometrisine oranlanır.
"""
from __future__ import annotations

import logging
import sys
from typing import Callable

from PyQt6.QtCore import QPoint, QRect, Qt
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QKeyEvent,
    QMouseEvent,
    QPaintEvent,
    QPainter,
    QPainterPath,
    QPen,
)
from PyQt6.QtWidgets import QApplication, QWidget

from .overlay import pick_screen_for_physical_rect, win32_physical_rect_to_qt_logical

log = logging.getLogger(__name__)


def _pick_screen_for_rect(source_rect: tuple[int, int, int, int] | None):
    """Verilen fiziksel/mantıksal dikdörtgeni en çok kapsayan ekranı seçer."""
    scr, _phys = pick_screen_for_physical_rect(source_rect)
    return scr or QApplication.primaryScreen()


class RoiSelectorWindow(QWidget):
    def __init__(
        self,
        snapshot: object = None,  # Geriye dönük uyumluluk için korundu
        on_selected: Callable[[list[float]], None] | None = None,
        parent: QWidget | None = None,
        source_rect: tuple[int, int, int, int] | None = None,
        source_label: str = "",
        monitor_rect: tuple[int, int, int, int] | None = None,
    ) -> None:
        super().__init__(parent)
        self.on_selected = on_selected
        self._source_label = (source_label or "").strip()

        self._start_pos: QPoint | None = None
        self._current_pos: QPoint | None = None
        self._is_selecting = False

        # Şeffaf tam ekran pencere ayarları (Görev çubuğunda sekme açmaması için Tool bayrağı)
        if sys.platform == "win32":
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

        # Kaynak pencere veya aktif monitör varsa onu kapsayan ekranı seç
        screen = _pick_screen_for_rect(source_rect if source_rect is not None else monitor_rect)
        screen_geo = screen.geometry() if screen else QRect(0, 0, 1920, 1080)
        self.setGeometry(screen_geo)
        self.setFixedSize(screen_geo.width(), screen_geo.height())
        self.setCursor(Qt.CursorShape.CrossCursor)

        self._target_rect: QRect | None = None
        if source_rect is not None and source_rect[2] >= 16 and source_rect[3] >= 16:
            if sys.platform == "win32":
                lx, ly, lw, lh = win32_physical_rect_to_qt_logical(source_rect)
                self._target_rect = QRect(lx - screen_geo.x(), ly - screen_geo.y(), max(16, lw), max(16, lh))
            else:
                self._target_rect = QRect(
                    int(source_rect[0]) - screen_geo.x(),
                    int(source_rect[1]) - screen_geo.y(),
                    max(16, int(source_rect[2])),
                    max(16, int(source_rect[3])),
                )

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if sys.platform == "win32":
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

        if self._target_rect is not None:
            inter = rect.intersected(self._target_rect)
            if inter.isEmpty() or inter.width() < 10 or inter.height() < 10:
                log.warning("Seçilen ROI hedef pencere dışında veya çok küçük (en az 10x10 px olmalı)")
                return
            tw = max(1, self._target_rect.width())
            th = max(1, self._target_rect.height())
            roi = [
                float((inter.x() - self._target_rect.x()) / tw),
                float((inter.y() - self._target_rect.y()) / th),
                float(inter.width() / tw),
                float(inter.height() / th),
            ]
            log.info("Pencere-göreli ROI onaylandı: %s (px: %dx%d)", roi, inter.width(), inter.height())
        else:
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

        if sys.platform == "win32":
            # Windows'ta WA_TranslucentBackground kapalı olduğu için sistem gri (#F0F0F0)
            # arka planını temiz koyu tuvalle bastır.
            painter.fillRect(0, 0, w, h, QColor(12, 16, 24))

        # 1. Arka plan karartması (hedef pencere seçiliyse pencere dışı daha koyu vurgulanır)
        if self._target_rect is not None:
            visible_target = self._target_rect.intersected(QRect(0, 0, w, h))
            outer_path = QPainterPath()
            outer_path.addRect(0.0, 0.0, float(w), float(h))
            inner_path = QPainterPath()
            inner_path.addRect(
                float(visible_target.x()),
                float(visible_target.y()),
                float(visible_target.width()),
                float(visible_target.height()),
            )
            outside_path = outer_path.subtracted(inner_path)
            outside_fill = QColor(6, 8, 14) if sys.platform == "win32" else QColor(0, 0, 0, 165)
            inside_fill = QColor(24, 30, 42) if sys.platform == "win32" else QColor(0, 0, 0, 80)
            painter.fillPath(outside_path, outside_fill)
            painter.fillRect(visible_target, inside_fill)

            target_pen = QPen(QColor("#38BDF8"), 2.0, Qt.PenStyle.DashLine)
            painter.setPen(target_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(visible_target.adjusted(1, 1, -1, -1))
        elif sys.platform != "win32":
            painter.fillRect(0, 0, w, h, QColor(0, 0, 0, 95))

        # 2. Seçim kutusu
        rect = self._get_selection_rect()
        if rect is not None and rect.width() > 0 and rect.height() > 0:
            if sys.platform == "win32":
                # Windows'ta WA_TranslucentBackground yokken CompositionMode_Clear siyah kutu üretir;
                # seçili bölgeyi parlak vurgulu dolgu ile netleştir.
                painter.fillRect(rect, QColor(72, 120, 110))
            else:
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
        from ..i18n import t

        if self._target_rect is not None:
            title = self._source_label or "Target Window"
            if len(title) > 36:
                title = title[:33] + "…"
            guide_text = t("roi.hint_window", title=title)
        else:
            guide_text = t("roi.hint")

        banner_font = QFont("sans-serif", 11, QFont.Weight.Bold)
        fm = QFontMetrics(banner_font)
        banner_w = max(560, min(max(320, w - 40), fm.horizontalAdvance(guide_text) + 48))
        banner_h = 44
        banner_x = (w - banner_w) // 2
        banner_y = 30
        banner_rect = QRect(banner_x, banner_y, banner_w, banner_h)

        painter.setBrush(QColor(15, 15, 22, 220))
        painter.setPen(QPen(QColor(255, 255, 255, 40), 1.0))
        painter.drawRoundedRect(banner_rect, 10, 10)

        painter.setFont(banner_font)
        painter.setPen(QColor(245, 245, 247))
        painter.drawText(banner_rect, Qt.AlignmentFlag.AlignCenter, guide_text)
