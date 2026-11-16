"""GameOCR Şeffaf ve Tıklama Geçirgen Altyazı Katmanı (PyQt6 Overlay).

Linux KDE Plasma / Wayland ve X11 ortamlarında tam ekran oyunların üzerinde
şeffaf, buzlu cam (blur-behind) efektli altyazı paneli çizer.
"""
from __future__ import annotations

import html
import logging
import queue
import re
import shutil
import subprocess
import sys

from PyQt6.QtCore import (
    QEasingCurve,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRect,
    QRectF,
    QTimer,
    Qt,
    pyqtProperty,
)
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QPaintEvent,
    QPainter,
    QPainterPath,
    QPen,
    QRegion,
    QTextDocument,
)
from PyQt6.QtWidgets import QApplication, QWidget

from ..config import OverlayConfig
from ..logging_utils import StageError, log_stage_exception, timed_stage
from ..messages import TextStyleMeta, UiKind, UiMessage
from .blur import disable_blur, enable_blur

log = logging.getLogger(__name__)


def set_win32_topmost_clickthrough(hwnd: int) -> bool:
    """Windows üzerinde overlay penceresine HWND_TOPMOST ve WS_EX_TRANSPARENT bayraklarını uygular."""
    if not hwnd:
        return False
    try:
        import ctypes

        user32 = getattr(ctypes, "windll", None)
        if user32 is None or not hasattr(user32, "user32"):
            return False
        GWL_EXSTYLE = -20
        WS_EX_LAYERED = 0x00080000
        WS_EX_TRANSPARENT = 0x00000020
        WS_EX_TOOLWINDOW = 0x00000080
        WS_EX_NOACTIVATE = 0x08000000
        HWND_TOPMOST = -1
        SWP_NOMOVE = 0x0002
        SWP_NOSIZE = 0x0001
        SWP_NOACTIVATE = 0x0010

        cur_style = user32.user32.GetWindowLongW(int(hwnd), GWL_EXSTYLE)
        new_style = cur_style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
        user32.user32.SetWindowLongW(int(hwnd), GWL_EXSTYLE, new_style)
        user32.user32.SetWindowPos(
            int(hwnd), HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
        )
        # SetWindowLongW çağrısı sonrası DWM yakalama gizleme bayrağını (WDA_EXCLUDEFROMCAPTURE = 0x11)
        # doğrudan pencerenin sahibi olan Qt ana iş parçacığında yenile (self-capture önleme):
        WDA_EXCLUDEFROMCAPTURE = 0x00000011
        ok = bool(user32.user32.SetWindowDisplayAffinity(int(hwnd), WDA_EXCLUDEFROMCAPTURE))
        if not ok:
            log.warning("Win32 SetWindowDisplayAffinity başarısız (hwnd=0x%x)", hwnd)
        return True
    except Exception as exc:
        log.debug("Win32 topmost/clickthrough uygulanamadı: %s", exc)
        return False


def set_x11_always_on_top(win_id: int) -> None:
    """XWayland/X11 veya Windows pencerelerinin her zaman en üstte kalmasını ve görev çubuğunda gizlenmesini sağlar."""
    if sys.platform == "win32":
        set_win32_topmost_clickthrough(win_id)
        return
    try:
        from Xlib import X, Xatom, display
        from Xlib.protocol import event

        d = display.Display()
        window = d.create_resource_object("window", int(win_id))
        root = d.screen().root
        wm_state = d.intern_atom("_NET_WM_STATE")
        state_above = d.intern_atom("_NET_WM_STATE_ABOVE")
        state_stays = d.intern_atom("_NET_WM_STATE_STAYS_ON_TOP")
        state_skip_taskbar = d.intern_atom("_NET_WM_STATE_SKIP_TASKBAR")
        state_skip_pager = d.intern_atom("_NET_WM_STATE_SKIP_PAGER")

        window.change_property(
            wm_state,
            Xatom.ATOM,
            32,
            [state_above, state_stays, state_skip_taskbar, state_skip_pager],
            X.PropModeReplace,
        )

        # EWMH standardına göre pencere yöneticisine (KWin/Mutter) durum değişikliğini bildir
        for atom1, atom2 in ((state_above, state_stays), (state_skip_taskbar, state_skip_pager)):
            cm = event.ClientMessage(
                window=window,
                client_type=wm_state,
                data=(32, [1, atom1, atom2, 1, 0]),  # 1 = _NET_WM_STATE_ADD
            )
            root.send_event(
                cm,
                event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask,
            )

        d.sync()
        d.close()
    except Exception as exc:
        log.debug("X11 Always-on-top atomu ayarlanamadı: %s", exc)


def ensure_kwin_rule() -> None:
    """KWin pencere kurallarına GameOCR için 'Keep Above (Force)' kuralı ekler."""
    if not shutil.which("kwriteconfig6"):
        return
    try:
        subprocess.run(["kwriteconfig6", "--file", "kwinrulesrc", "--group", "1", "--key", "Description", "GameOCR Always on Top"], check=False)
        subprocess.run(["kwriteconfig6", "--file", "kwinrulesrc", "--group", "1", "--key", "wmclass", "gameocr"], check=False)
        subprocess.run(["kwriteconfig6", "--file", "kwinrulesrc", "--group", "1", "--key", "wmclassmatch", "1"], check=False)
        subprocess.run(["kwriteconfig6", "--file", "kwinrulesrc", "--group", "1", "--key", "above", "true", "--type", "bool"], check=False)
        subprocess.run(["kwriteconfig6", "--file", "kwinrulesrc", "--group", "1", "--key", "aboverule", "2"], check=False)
        subprocess.run(["kwriteconfig6", "--file", "kwinrulesrc", "--group", "1", "--key", "skiptaskbar", "true", "--type", "bool"], check=False)
        subprocess.run(["kwriteconfig6", "--file", "kwinrulesrc", "--group", "1", "--key", "skiptaskbarrule", "2"], check=False)
        subprocess.run(["kwriteconfig6", "--file", "kwinrulesrc", "--group", "1", "--key", "skippager", "true", "--type", "bool"], check=False)
        subprocess.run(["kwriteconfig6", "--file", "kwinrulesrc", "--group", "1", "--key", "skippagerrule", "2"], check=False)
        if shutil.which("busctl"):
            subprocess.run(["busctl", "--user", "call", "org.kde.KWin", "/KWin", "org.kde.KWin", "reconfigure"], check=False)
    except Exception as exc:
        log.debug("KWin kuralı eklenemedi: %s", exc)


class OverlayWindow(QWidget):
    def __init__(
        self,
        cfg: OverlayConfig,
        ui_q: queue.Queue[UiMessage] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.cfg = cfg
        self.ui_q = ui_q

        self.setObjectName("gameocr")
        self.setWindowTitle("GameOCR Overlay")

        self._text = ""
        self._status_text = ""
        self._style_meta: TextStyleMeta | None = None
        self._last_render_info: dict[str, object] = {}
        self._opacity = 0.0
        self._user_visible = True
        self._active_geometry: tuple[int, int, int, int] = (0, 0, 0, 0)
        self._blur_active: bool = False
        self._last_blur_geo: tuple[int, int] = (0, 0)
        self._last_win32_mask_rect: tuple[int, int, int, int] | None = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.ToolTip
            | Qt.WindowType.WindowTransparentForInput
        )
        # Windows'ta WA_TranslucentBackground (UpdateLayeredWindow) kullanıldığında DWM
        # SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE) çağrısını reddeder (ok=0, err=8).
        # Bu nedenle Windows üzerinde setMask(QRegion) + setWindowOpacity() ile saydamlık sağlanır.
        if sys.platform != "win32":
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        ensure_kwin_rule()

        # Fade animasyonu
        self._anim = QPropertyAnimation(self, b"panelOpacity", self)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._anim.finished.connect(self._on_anim_finished)

        # UI Kuyruğunu tüketmek için zamanlayıcı (30 ms)
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(30)
        self._poll_timer.timeout.connect(self._poll_queue)
        self._poll_timer.start()

    # ------------------------------------------------------------------ #
    # Kullanıcı Görünürlüğü (Kısayol Kontrollü)
    # ------------------------------------------------------------------ #
    def is_user_visible(self) -> bool:
        return self._user_visible

    def set_user_visible(self, visible: bool) -> None:
        self._user_visible = visible
        if not visible:
            self._anim.stop()
            self._opacity = 0.0
            self.hide()
            disable_blur(int(self.winId()))
        else:
            display_text = (self._status_text or self._text or "").strip()
            if display_text:
                self.fade_in(150)

    # ------------------------------------------------------------------ #
    # Qt Animasyon Özelliği
    # ------------------------------------------------------------------ #
    @pyqtProperty(float)
    def panelOpacity(self) -> float:
        return self._opacity

    @panelOpacity.setter
    def panelOpacity(self, value: float) -> None:
        self._opacity = max(0.0, min(1.0, float(value)))
        if sys.platform == "win32":
            self._apply_win32_window_opacity()
        self.update()

    def _apply_win32_window_opacity(self, exact_mode: bool = False) -> None:
        base_alpha = max(0.0, min(1.0, float(self.cfg.opacity)))
        if exact_mode:
            target = max(base_alpha, 0.96) * self._opacity
        else:
            target = max(0.12, base_alpha) * self._opacity if base_alpha > 0.01 else self._opacity
        self.setWindowOpacity(max(0.0, min(1.0, target)))

    def _sync_win32_mask(self, panel_rect: QRectF) -> None:
        """Windows'ta yalnızca çizilen panel dikdörtgenini görünür kılar (dışı tamamen şeffaftır)."""
        if sys.platform != "win32":
            return
        import math

        rx = max(0, int(math.floor(panel_rect.x())))
        ry = max(0, int(math.floor(panel_rect.y())))
        rw = max(1, int(math.ceil(panel_rect.width())))
        rh = max(1, int(math.ceil(panel_rect.height())))
        key = (rx, ry, rw, rh)
        if self._last_win32_mask_rect != key:
            self._last_win32_mask_rect = key
            self.setMask(QRegion(QRect(rx, ry, rw, rh)))

    def _on_anim_finished(self) -> None:
        if self._opacity <= 0.01:
            self._text = ""
            self._status_text = ""
            self._style_meta = None
            self.hide()
            if self._blur_active:
                disable_blur(int(self.winId()))
                self._blur_active = False

    def showEvent(self, event) -> None:
        super().showEvent(event)
        xid = int(self.winId())
        set_x11_always_on_top(xid)
        self._apply_blur()

    def show_status(self, text: str) -> None:
        """Kısa süreli durum mesajı (örneğin [DURAKLATILDI]) gösterir."""
        self._status_text = text
        self.fade_in(100)

    def fade_in(self, duration_ms: int = 150) -> None:
        if not self._user_visible:
            return
        self.show()
        self.raise_()
        set_x11_always_on_top(int(self.winId()))
        self._apply_blur()
        self.update()

        if self.isVisible() and self._opacity >= 0.98:
            return

        self._anim.stop()
        self._anim.setDuration(duration_ms)
        self._anim.setStartValue(self._opacity)
        self._anim.setEndValue(1.0)
        self._anim.start()

    def fade_out(self, duration_ms: int = 250) -> None:
        self._anim.stop()
        self._anim.setDuration(duration_ms)
        self._anim.setStartValue(self._opacity)
        self._anim.setEndValue(0.0)
        self._anim.start()

    # ------------------------------------------------------------------ #
    # Geometri ve Blur
    # ------------------------------------------------------------------ #
    def set_roi_geometry(self, x: int, y: int, w: int, h: int) -> None:
        if w <= 0 or h <= 0:
            return
        if sys.platform == "win32":
            screen = QApplication.primaryScreen()
            dpr = float(screen.devicePixelRatio()) if screen is not None else 1.0
            if dpr > 1.01:
                x = int(round(x / dpr))
                y = int(round(y / dpr))
                w = max(1, int(round(w / dpr)))
                h = max(1, int(round(h / dpr)))
        if self._active_geometry == (x, y, w, h):
            return
        self._active_geometry = (x, y, w, h)
        self._last_win32_mask_rect = None
        self.setGeometry(x, y, w, h)
        self._apply_blur()
        set_x11_always_on_top(int(self.winId()))

    def _apply_blur(self) -> None:
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return
        xid = int(self.winId())
        display_text = (self._status_text or self._text or "").strip()
        should_blur = bool(
            self._user_visible and display_text and self.cfg.blur and self.cfg.opacity > 0.02
        )
        if should_blur:
            if not self._blur_active or self._last_blur_geo != (w, h):
                enable_blur(xid, w, h)
                self._blur_active = True
                self._last_blur_geo = (w, h)
        else:
            if self._blur_active:
                disable_blur(xid)
                self._blur_active = False

    def update_config(self, cfg: OverlayConfig) -> None:
        self.cfg = cfg
        self._apply_blur()
        set_x11_always_on_top(int(self.winId()))
        self.update()

    # ------------------------------------------------------------------ #
    # Kuyruk Dinleme (ui_q)
    # ------------------------------------------------------------------ #
    def _poll_queue(self) -> None:
        if self.ui_q is None:
            return

        while True:
            try:
                msg = self.ui_q.get_nowait()
            except queue.Empty:
                break

            self._handle_ui_message(msg)

    def _handle_ui_message(self, msg: UiMessage) -> None:
        if msg.kind == UiKind.SHOW:
            new_meta = msg.data if isinstance(msg.data, TextStyleMeta) else None
            # Kullanıcı altyazıyı kısayolla gizlediyse ekrana çizme
            if not self._user_visible:
                self._text = msg.text
                self._style_meta = new_meta
                return

            self._status_text = ""
            # Anti-flicker: Eğer aynı metin zaten tam görünür durumdaysa animasyonu baştan başlatma!
            if (
                self._text == msg.text
                and self._style_meta == new_meta
                and self.isVisible()
                and self._opacity >= 0.95
            ):
                return

            self._text = msg.text
            self._style_meta = new_meta
            self.update()
            self.fade_in(150)

        elif msg.kind == UiKind.CLEAR:
            self._status_text = ""
            self._style_meta = None
            if not self._text:
                self.hide()
                return
            self.fade_out(200)

        elif msg.kind == UiKind.STATUS:
            self._status_text = msg.text
            if self._user_visible:
                self.fade_in(100)

        elif msg.kind == UiKind.GEOMETRY:
            if isinstance(msg.data, (tuple, list)) and len(msg.data) == 4:
                x, y, w, h = msg.data
                self.set_roi_geometry(int(x), int(y), int(w), int(h))

    # ------------------------------------------------------------------ #
    # Çizim (Paint) ve Dinamik Görsel Metin Hizalama
    # ------------------------------------------------------------------ #
    @staticmethod
    def _color_luma(c: QColor) -> float:
        return 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()

    @staticmethod
    def _build_highlighted_html(
        text: str,
        base_color_hex: str,
        word_colors: list[tuple[str, str]],
    ) -> str:
        """Metin içindeki vurgu ifadelerini `<span style="color: #HEX;">...</span>` ile sarmalar."""
        escaped = html.escape(text)
        if not word_colors:
            return f'<div style="color: {base_color_hex};">{escaped}</div>'

        # Uzun ifadeleri önce eşleştir ki kısa alt-kelimeler uzun ifadeyi bölmesin
        sorted_spans = sorted(
            [(p.strip(), col) for p, col in word_colors if p and p.strip()],
            key=lambda x: len(x[0]),
            reverse=True,
        )
        placeholders: list[tuple[str, str]] = []
        working = escaped
        for idx, (phrase, hex_col) in enumerate(sorted_spans):
            esc_phrase = html.escape(phrase)
            if not esc_phrase:
                continue
            pattern = re.compile(re.escape(esc_phrase), flags=re.IGNORECASE)
            match = pattern.search(working)
            if match:
                token = f"__GOCR_SPAN_{idx}__"
                matched_text = match.group(0)
                replacement_html = f'<span style="color: {hex_col};">{matched_text}</span>'
                working = working[: match.start()] + token + working[match.end() :]
                placeholders.append((token, replacement_html))

        for token, replacement_html in placeholders:
            working = working.replace(token, replacement_html)

        return f'<div style="color: {base_color_hex};">{working}</div>'

    def compute_render_layout(
        self,
        w: float,
        h: float,
        display_text: str,
    ) -> tuple[QRectF, QRect, QFont, QColor, Qt.AlignmentFlag, str]:
        """Aktif konfigürasyona (`exact_alignment`) ve OCR metaverisine (`_style_meta`)
        göre arka plan panelini, metin koordinat dikdörtgenini, yazı tipini ve rengini hesaplar.
        """
        use_exact = bool(
            getattr(self.cfg, "exact_alignment", True)
            and self._style_meta is not None
            and not self._status_text
        )

        if use_exact and self._style_meta is not None:
            try:
                with timed_stage(
                    log,
                    "paint_exact_overlay",
                    reraise=True,
                    bbox_rel=self._style_meta.bbox_rel,
                    line_height_px=self._style_meta.line_height_px,
                    color=self._style_meta.text_color_hex,
                ):
                    rx, ry, rw, rh = self._style_meta.bbox_rel
                    if not (0.0 <= rx <= 1.0 and 0.0 <= ry <= 1.0 and rw > 0.0 and rh > 0.0):
                        raise ValueError(f"Geçersiz bbox_rel koordinatı: {self._style_meta.bbox_rel}")

                    # 1. Tam Hizalama (Exact X, Y Koordinatları)
                    x_px = max(2, min(int(w - 16), int(round(rx * w))))
                    y_px = max(2, min(int(h - 12), int(round(ry * h))))
                    orig_x_px, orig_y_px = x_px, y_px
                    orig_w_px = max(16, int(round(rw * w)))
                    orig_h_px = max(12, int(round(rh * h)))

                    # Çevrilen metin orijinalden biraz daha uzun olabileceği için sağa/aşağı taşma payı
                    avail_w = max(16, int(w) - x_px - 4)
                    avail_h = max(12, int(h) - y_px - 4)
                    target_w = min(avail_w, max(orig_w_px, int(orig_w_px * 1.30) + 48))
                    target_h = avail_h

                    text_rect = QRect(x_px, y_px, target_w, target_h)
                    alignment = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap

                    # 2. Orijinal Yazı Tipi Boyutu + Uzun Metin Otomatik Sığdırma (Zero-Clip Auto-Fit)
                    font = QFont(self.cfg.font_family)
                    font.setWeight(QFont.Weight.Bold)
                    if getattr(self.cfg, "match_font_size", True) and self._style_meta.line_height_px > 0:
                        min_px = max(8, int(self.cfg.font_min))
                        max_px = max(min_px, int(self.cfg.font_max) * 2)
                        exact_px = max(min_px, min(max_px, int(self._style_meta.line_height_px)))
                        font.setPixelSize(exact_px)

                        # Eğer çevrilen metin sarıldığında (word-wrap) mevcut yüksekliğe sığmıyorsa:
                        # Önce varsa genişliği avail_w'ye kadar aç, hala sığmıyorsa font_px'i kademeli küçült!
                        fm = QFontMetrics(font)
                        bound = fm.boundingRect(text_rect, int(alignment), display_text)
                        if bound.height() > text_rect.height() and target_w < avail_w:
                            target_w = avail_w
                            text_rect = QRect(x_px, y_px, target_w, target_h)
                            bound = fm.boundingRect(text_rect, int(alignment), display_text)

                        if bound.height() > text_rect.height() and y_px > 4:
                            # Üstteki boşluğu da kullanarak dikey alanı genişlet
                            reclaimed_y = max(2, y_px - min(y_px - 2, bound.height() - text_rect.height()))
                            y_px = reclaimed_y
                            target_h = max(12, int(h) - y_px - 2)
                            text_rect = QRect(x_px, y_px, target_w, target_h)
                            bound = fm.boundingRect(text_rect, int(alignment), display_text)

                        cur_px = exact_px
                        floor_px = max(8, min_px - 2)
                        while (bound.height() > text_rect.height() or bound.width() > text_rect.width()) and cur_px > floor_px:
                            cur_px -= 1
                            font.setPixelSize(cur_px)
                            fm = QFontMetrics(font)
                            bound = fm.boundingRect(text_rect, int(alignment), display_text)
                    else:
                        font = self._compute_fitted_font(display_text, text_rect)

                    # 3. Orijinal Arka Plan ve Metin Rengi + Kontrast Garantisi
                    bg_hex = getattr(self._style_meta, "bg_color_hex", "") or self.cfg.panel_color
                    bg_color = QColor(bg_hex)
                    if not bg_color.isValid():
                        bg_color = QColor(self.cfg.panel_color)

                    raw_hex = (
                        self._style_meta.text_color_hex
                        if getattr(self.cfg, "match_text_color", True)
                        else self.cfg.text_color
                    )
                    text_color = QColor(raw_hex)
                    if not text_color.isValid():
                        text_color = QColor(self.cfg.text_color)

                    # Eğer örneklenen metin rengi ile arka plan rengi arasında yeterli kontrast yoksa düzelt
                    bg_luma = self._color_luma(bg_color)
                    fg_luma = self._color_luma(text_color)
                    if abs(fg_luma - bg_luma) < 42.0:
                        text_color = QColor("#101014") if bg_luma > 140.0 else QColor("#F5F5F7")

                    # Arka plan panelini hem orijinal İngilizce metnin tamamını (orig_w_px, orig_h_px)
                    # hem de yeni çeviri kutusunu eksiksiz kapatacak şekilde sar
                    fm = QFontMetrics(font)
                    drawn_bound = fm.boundingRect(text_rect, int(alignment), display_text)
                    pad_x, pad_y = 10.0, 5.0
                    p_left = max(0.0, float(min(orig_x_px, x_px, drawn_bound.left())) - pad_x)
                    p_top = max(0.0, float(min(orig_y_px, y_px, drawn_bound.top())) - pad_y)
                    p_right = min(w, float(max(orig_x_px + orig_w_px, drawn_bound.right())) + pad_x)
                    p_bottom = min(h, float(max(orig_y_px + orig_h_px, drawn_bound.bottom())) + pad_y)
                    panel_rect = QRectF(p_left, p_top, max(16.0, p_right - p_left), max(12.0, p_bottom - p_top))

                    self._last_render_info = {
                        "mode": "exact",
                        "text_rect": (text_rect.x(), text_rect.y(), text_rect.width(), text_rect.height()),
                        "panel_rect": (panel_rect.x(), panel_rect.y(), panel_rect.width(), panel_rect.height()),
                        "font_pixel_size": font.pixelSize(),
                        "font_point_size": font.pointSize(),
                        "text_color": text_color.name().upper(),
                        "bg_color": bg_color.name().upper(),
                        "word_colors": list(getattr(self._style_meta, "word_colors", [])),
                    }
                    return panel_rect, text_rect, font, text_color, alignment, "exact"
            except Exception as exc:
                if not isinstance(exc, StageError):
                    log_stage_exception(log, "paint_exact_overlay", exc)

        # Standart (Klasik) Ortalı Panel Modu
        panel_rect = QRectF(0.0, 0.0, w, h)
        padding_x = max(12.0, w * 0.04)
        padding_y = max(6.0, h * 0.08)
        text_rect = QRect(
            int(padding_x),
            int(padding_y),
            max(10, int(w - 2 * padding_x)),
            max(10, int(h - 2 * padding_y)),
        )
        font = self._compute_fitted_font(display_text, text_rect)
        text_color = QColor(self.cfg.text_color)
        if not text_color.isValid():
            text_color = QColor("#F5F5F7")
        alignment = Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap

        self._last_render_info = {
            "mode": "standard",
            "text_rect": (text_rect.x(), text_rect.y(), text_rect.width(), text_rect.height()),
            "panel_rect": (panel_rect.x(), panel_rect.y(), panel_rect.width(), panel_rect.height()),
            "font_pixel_size": font.pixelSize(),
            "font_point_size": font.pointSize(),
            "text_color": text_color.name().upper(),
            "bg_color": QColor(self.cfg.panel_color).name().upper(),
            "word_colors": [],
        }
        return panel_rect, text_rect, font, text_color, alignment, "standard"

    def paintEvent(self, event: QPaintEvent) -> None:
        # Metin yokken veya kullanıcı overlay'i gizlediyse ASLA panel/arka plan çizilmez!
        display_text = (self._status_text or self._text or "").strip()
        if not self._user_visible or not display_text or self._opacity <= 0.005:
            return

        w, h = float(self.width()), float(self.height())
        if w < 10 or h < 10:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        panel_rect, text_rect, font, text_color, alignment, mode = self.compute_render_layout(
            w, h, display_text
        )
        if sys.platform == "win32":
            self._sync_win32_mask(panel_rect)
            self._apply_win32_window_opacity(exact_mode=(mode == "exact"))
        radius = float(self.cfg.corner_radius)

        # 1. Arka plan paneli
        # Opaklık 0.0 ise panel tamamen şeffaftır (yalnızca yazı ve gölgesi görünür)
        base_alpha = max(0.0, min(1.0, float(self.cfg.opacity)))
        alpha = 255 if sys.platform == "win32" else int(base_alpha * self._opacity * 255)
        bg_luma = 15.0

        if alpha > 0:
            if mode == "exact" and self._style_meta is not None:
                # Tam Hizalama modunda alttaki orijinal İngilizce yazının arkadan görünmemesi (bleed-through olmaması)
                # ve açık/koyu sayfa arka planıyla birebir bütünleşmesi için örneklenen bg_color_hex kullanılır.
                bg_hex = getattr(self._style_meta, "bg_color_hex", "") or self.cfg.panel_color
                c_bg = QColor(bg_hex)
                if not c_bg.isValid():
                    c_bg = QColor(self.cfg.panel_color)
                bg_luma = self._color_luma(c_bg)
                exact_alpha = 255 if sys.platform == "win32" else int(max(base_alpha, 0.96) * self._opacity * 255)
                c_bg.setAlpha(exact_alpha)
                painter.setBrush(c_bg)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(
                    panel_rect.adjusted(0.5, 0.5, -0.5, -0.5),
                    min(radius, 6.0),
                    min(radius, 6.0),
                )
            else:
                gradient = QLinearGradient(0, panel_rect.top(), 0, panel_rect.bottom())
                # Blur açıkken buzlu cam efektinin arkasındaki oyunu göstermesi için panel yarı saydamdır
                panel_alpha = int(alpha * 0.70) if self.cfg.blur else alpha
                c_top = QColor(self.cfg.panel_color)
                c_top.setAlpha(panel_alpha)
                c_bottom = QColor(10, 10, 14, panel_alpha)
                bg_luma = self._color_luma(c_top)
                gradient.setColorAt(0.0, c_top)
                gradient.setColorAt(1.0, c_bottom)

                painter.setBrush(gradient)
                border_alpha = int(min(45, alpha * 0.4))
                painter.setPen(
                    QPen(QColor(255, 255, 255, border_alpha), 1.0)
                    if border_alpha > 5
                    else Qt.PenStyle.NoPen
                )
                painter.drawRoundedRect(panel_rect.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)

        # 2. Metin Çizimi (Çok Renkli Kelime Vurgulama veya Tek Renk)
        painter.setFont(font)
        word_colors = (
            list(getattr(self._style_meta, "word_colors", []))
            if (mode == "exact" and self._style_meta is not None and getattr(self.cfg, "match_text_color", True))
            else []
        )

        if word_colors:
            self._draw_rich_multicolor_text(
                painter=painter,
                text_rect=text_rect,
                font=font,
                base_color=text_color,
                word_colors=word_colors,
                display_text=display_text,
                bg_luma=bg_luma,
            )
            return

        text_color.setAlpha(int(self._opacity * 255))

        # Gölge Çizimi (Yalnızca koyu arka planlarda okunabilirlik gölgesi çiz; açık sayfada siyah yazıyı kirletme)
        if getattr(self.cfg, "text_shadow", True) and bg_luma < 155.0:
            shadow_color = QColor(0, 0, 0, int(self._opacity * 220))
            for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1), (0, 2), (0, -1)):
                s_rect = text_rect.translated(dx, dy)
                painter.setPen(shadow_color)
                painter.drawText(
                    s_rect,
                    int(alignment),
                    display_text,
                )

        painter.setPen(text_color)
        painter.drawText(
            text_rect,
            int(alignment),
            display_text,
        )

    def _draw_rich_multicolor_text(
        self,
        painter: QPainter,
        text_rect: QRect,
        font: QFont,
        base_color: QColor,
        word_colors: list[tuple[str, str]],
        display_text: str,
        bg_luma: float,
    ) -> None:
        """Cümle içindeki farklı renkli vurgu kelimelerini (`word_colors`) kendi renklerinde çizer."""
        doc = QTextDocument()
        doc.setDocumentMargin(0.0)
        doc.setDefaultFont(font)
        doc.setTextWidth(float(text_rect.width()))

        # Koyu arka planda gölge katmanı
        if getattr(self.cfg, "text_shadow", True) and bg_luma < 155.0:
            shadow_doc = QTextDocument()
            shadow_doc.setDocumentMargin(0.0)
            shadow_doc.setDefaultFont(font)
            shadow_doc.setTextWidth(float(text_rect.width()))
            shadow_doc.setHtml(f'<div style="color: #000000;">{html.escape(display_text)}</div>')
            for dx, dy in ((-1, 1), (1, 1), (0, 2)):
                painter.save()
                painter.setOpacity(self._opacity * 0.85)
                painter.translate(float(text_rect.x() + dx), float(text_rect.y() + dy))
                shadow_doc.drawContents(painter, QRectF(0.0, 0.0, float(text_rect.width()), float(text_rect.height())))
                painter.restore()

        rich_html = self._build_highlighted_html(display_text, base_color.name(), word_colors)
        doc.setHtml(rich_html)
        painter.save()
        painter.setOpacity(self._opacity)
        painter.translate(float(text_rect.x()), float(text_rect.y()))
        doc.drawContents(painter, QRectF(0.0, 0.0, float(text_rect.width()), float(text_rect.height())))
        painter.restore()

    def _compute_fitted_font(self, text: str, target_rect: QRect) -> QFont:
        """Metni hedef dikdörtgene sığdıracak en ideal font boyutunu bulur."""
        font = QFont(self.cfg.font_family)
        font.setWeight(QFont.Weight.Bold)

        target_w = target_rect.width()
        target_h = target_rect.height()

        low = self.cfg.font_min
        high = self.cfg.font_max
        best_size = low

        while low <= high:
            mid = (low + high) // 2
            font.setPointSize(mid)
            fm = QFontMetrics(font)
            bound = fm.boundingRect(
                target_rect,
                Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                text,
            )
            if bound.width() <= target_w and bound.height() <= target_h:
                best_size = mid
                low = mid + 1
            else:
                high = mid - 1

        font.setPointSize(best_size)
        return font
