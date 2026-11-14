"""GameOCR Ayarlar Penceresi (PyQt6 QDialog).

Dil çifti, DeepL API anahtarı ve kota takibi, kalıcı önbellek yönetimi,
overlay görünümü ve OCR/algılama parametrelerini yönetir.
i18n desteği ile Türkçe ve İngilizce arayüz sağlar.
"""
from __future__ import annotations

import logging
from typing import Callable

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QCloseEvent, QFocusEvent, QKeyEvent, QKeySequence
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..cache_store import CacheStore
from ..config import Config, save_config
from ..i18n import AVAILABLE_LANGUAGES, set_language, t
from ..languages import (
    get_source_languages,
    get_target_languages,
    normalize_target_lang,
)
from ..local_models import LocalModelManager, ModelDownloadWorker
from ..ocr_models import OcrModelDownloadWorker, OcrModelManager
from ..translator import Translator
from .blur import set_kwin_blur_strength

log = logging.getLogger(__name__)


class HotkeyButton(QPushButton):
    """Kullanıcının tıklayıp klavyeden kombinasyon basarak kısayol belirlediği buton."""
    shortcutChanged = pyqtSignal(str)

    def __init__(self, shortcut: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._shortcut = shortcut
        self._is_recording = False
        self._set_idle_style()
        self._update_text()
        self.clicked.connect(self._start_recording)

    def current_shortcut(self) -> str:
        return self._shortcut

    def set_shortcut(self, sc: str) -> None:
        self._shortcut = sc
        self._update_text()

    def _update_text(self) -> None:
        if self._shortcut:
            parts = [p.capitalize() for p in self._shortcut.split("+")]
            self.setText(" + ".join(parts))
        else:
            self.setText(t("hotkeys.none"))

    def _set_idle_style(self) -> None:
        self.setStyleSheet(
            "QPushButton { "
            "  background-color: #262938; "
            "  color: #e0e6ed; "
            "  border: 1px solid #3e445b; "
            "  border-radius: 6px; "
            "  padding: 6px 14px; "
            "  font-family: monospace; "
            "  font-size: 12px; "
            "  font-weight: bold; "
            "  min-width: 150px; "
            "} "
            "QPushButton:hover { "
            "  background-color: #31364a; "
            "  border-color: #556080; "
            "}"
        )

    def _set_recording_style(self) -> None:
        self.setStyleSheet(
            "QPushButton { "
            "  background-color: #1e3a5f; "
            "  color: #60a5fa; "
            "  border: 2px solid #3b82f6; "
            "  border-radius: 6px; "
            "  padding: 5px 13px; "
            "  font-family: monospace; "
            "  font-size: 12px; "
            "  font-weight: bold; "
            "  min-width: 150px; "
            "}"
        )

    def _start_recording(self) -> None:
        self._is_recording = True
        self._set_recording_style()
        self.setText(t("hotkeys.record_prompt"))
        self.grabKeyboard()

    def _stop_recording(self) -> None:
        if self._is_recording:
            self._is_recording = False
            self.releaseKeyboard()
            self._set_idle_style()
            self._update_text()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if not self._is_recording:
            super().keyPressEvent(event)
            return

        key = event.key()

        # Esc basılırsa iptal et
        if key == Qt.Key.Key_Escape:
            self._stop_recording()
            return

        # Yalnızca modifier tuşuna (Ctrl, Alt, Shift, Meta) basıldıysa kombineyi bekle
        if key in (
            Qt.Key.Key_Control,
            Qt.Key.Key_Alt,
            Qt.Key.Key_Shift,
            Qt.Key.Key_Meta,
            Qt.Key.Key_AltGr,
        ):
            return

        modifiers = event.modifiers()
        parts: list[str] = []

        if modifiers & Qt.KeyboardModifier.ControlModifier:
            parts.append("Ctrl")
        if modifiers & Qt.KeyboardModifier.AltModifier:
            parts.append("Alt")
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            parts.append("Shift")
        if modifiers & Qt.KeyboardModifier.MetaModifier:
            parts.append("Meta")

        key_seq = QKeySequence(key)
        key_str = key_seq.toString(QKeySequence.SequenceFormat.PortableText)
        if not key_str:
            return

        parts.append(key_str)
        self._shortcut = "+".join(parts)
        self._stop_recording()
        self.shortcutChanged.emit(self._shortcut)

    def focusOutEvent(self, event: QFocusEvent) -> None:
        self._stop_recording()
        super().focusOutEvent(event)


class SettingsDialog(QDialog):
    def __init__(
        self,
        cfg: Config,
        cache_store: CacheStore | None = None,
        translator: Translator | None = None,
        local_manager: LocalModelManager | None = None,
        ocr_manager: OcrModelManager | None = None,
        on_applied: Callable[[Config], None] | None = None,
        on_select_window: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.cfg = cfg.copy()
        self.cache_store = cache_store
        self.translator = translator
        self.local_manager = (
            local_manager
            or (translator.local_manager if translator is not None and hasattr(translator, "local_manager") else None)
            or LocalModelManager()
        )
        self.ocr_manager = ocr_manager or OcrModelManager()
        self.on_applied = on_applied
        self.on_select_window = on_select_window
        self._download_worker: ModelDownloadWorker | None = None
        self._ocr_download_worker: OcrModelDownloadWorker | None = None

        set_language(self.cfg.general.ui_language)

        self.setWindowTitle(t("settings.title"))
        self.resize(640, 620)

        main_layout = QVBoxLayout(self)

        self.tabs = QTabWidget(self)
        main_layout.addWidget(self.tabs)

        self._build_all_tabs()

        # Alt Buton Çubuğu (Varsayılanlara Sıfırla, Kaydet, Kapat)
        btn_layout = QHBoxLayout()

        self.status_msg_label = QLabel("")
        self.status_msg_label.setStyleSheet("color: #44dd88; font-weight: bold;")
        btn_layout.addWidget(self.status_msg_label)

        btn_layout.addStretch()

        self.reset_defaults_btn = QPushButton(t("btn.reset_defaults"))
        self.reset_defaults_btn.setStyleSheet(
            "QPushButton { background-color: #3b2024; color: #f87171; border: 1px solid #7f1d1d; padding: 6px 14px; border-radius: 4px; font-weight: bold; }"
            "QPushButton:hover { background-color: #4c1d24; color: #fca5a5; border-color: #991b1b; }"
        )
        self.reset_defaults_btn.clicked.connect(self._reset_to_defaults)
        btn_layout.addWidget(self.reset_defaults_btn)

        self.save_btn = QPushButton(t("btn.save"))
        self.save_btn.setStyleSheet(
            "QPushButton { background-color: #2e6db4; color: white; padding: 6px 16px; border-radius: 4px; font-weight: bold; }"
            "QPushButton:hover { background-color: #3b82f6; }"
        )
        self.save_btn.clicked.connect(self._save_changes)
        btn_layout.addWidget(self.save_btn)

        self.close_btn = QPushButton(t("btn.close"))
        self.close_btn.setStyleSheet("padding: 6px 16px;")
        self.close_btn.clicked.connect(self.close)
        btn_layout.addWidget(self.close_btn)

        main_layout.addLayout(btn_layout)

    def _build_all_tabs(self) -> None:
        self._build_lang_tab()
        self._build_cache_tab()
        self._build_appearance_tab()
        self._build_capture_tab()
        self._build_hotkeys_tab()

    # ------------------------------------------------------------------ #
    # 1. Dil ve Çeviri Sekmesi
    # ------------------------------------------------------------------ #
    def _build_lang_tab(self) -> None:
        tab = QWidget()
        layout = QFormLayout(tab)

        # Arayüz Dili Seçimi
        self.ui_lang_combo = QComboBox()
        for code, name in AVAILABLE_LANGUAGES.items():
            self.ui_lang_combo.addItem(name, code)
        self._select_combo_data(self.ui_lang_combo, self.cfg.general.ui_language)
        layout.addRow(t("settings.ui_language"), self.ui_lang_combo)

        # Çeviri Motoru Seçimi (DeepL / Lokal / Otomatik Yedek)
        self.engine_combo = QComboBox()
        self.engine_combo.addItem(t("engine.deepl"), "deepl")
        self.engine_combo.addItem(t("engine.local"), "local")
        self.engine_combo.addItem(t("engine.auto_fallback"), "auto_fallback")
        self._select_combo_data(
            self.engine_combo, getattr(self.cfg.general, "translation_engine", "deepl")
        )
        layout.addRow(t("settings.translation_engine"), self.engine_combo)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addRow(sep)

        # Kaynak ve Hedef dil seçimi
        lang_row = QHBoxLayout()
        self.src_combo = QComboBox()
        self.tgt_combo = QComboBox()

        for lang in get_source_languages():
            self.src_combo.addItem(f"{lang.display_name} ({lang.deepl_code})", lang.deepl_code)

        for lang in get_target_languages():
            self.tgt_combo.addItem(f"{lang.display_name} ({lang.deepl_code})", lang.deepl_code)

        self._select_combo_data(self.src_combo, self.cfg.general.source_lang)
        self._select_combo_data(self.tgt_combo, self.cfg.general.target_lang)

        swap_btn = QPushButton("⇄")
        swap_btn.setToolTip(t("settings.swap_langs"))
        swap_btn.setFixedWidth(36)
        swap_btn.clicked.connect(self._swap_languages)

        lang_row.addWidget(self.src_combo)
        lang_row.addWidget(swap_btn)
        lang_row.addWidget(self.tgt_combo)
        layout.addRow(t("settings.lang_pair"), lang_row)

        # DeepL API Anahtarı
        key_row = QHBoxLayout()
        self.key_edit = QLineEdit(self.cfg.deepl.auth_key)
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText(t("settings.deepl_key_ph"))
        self.key_edit.editingFinished.connect(self._verify_and_refresh_quota)

        show_key_btn = QPushButton("👁")
        show_key_btn.setCheckable(True)
        show_key_btn.setFixedWidth(36)
        show_key_btn.toggled.connect(
            lambda checked: self.key_edit.setEchoMode(
                QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
            )
        )

        verify_key_btn = QPushButton(t("btn.verify_key"))
        verify_key_btn.setToolTip("DeepL sunucusuna bağlanıp güncel kotayı kontrol eder")
        verify_key_btn.clicked.connect(self._verify_and_refresh_quota)

        key_row.addWidget(self.key_edit)
        key_row.addWidget(show_key_btn)
        key_row.addWidget(verify_key_btn)
        layout.addRow(t("settings.deepl_key"), key_row)

        # DeepL Kota Çubuğu
        self.quota_bar = QProgressBar()
        self.quota_bar.setRange(0, 100)
        self.quota_label = QLabel(t("settings.quota_loading"))
        layout.addRow(t("settings.monthly_quota"), self.quota_bar)
        layout.addRow("", self.quota_label)

        # Biçimsellik (Formality)
        self.formality_combo = QComboBox()
        formality_options = [
            ("default", t("formality.default")),
            ("more", t("formality.more")),
            ("less", t("formality.less")),
            ("prefer_more", t("formality.prefer_more")),
            ("prefer_less", t("formality.prefer_less")),
        ]
        for val, label in formality_options:
            self.formality_combo.addItem(label, val)
        self._select_combo_data(self.formality_combo, self.cfg.deepl.formality)
        layout.addRow(t("settings.formality"), self.formality_combo)

        # Lokal Dil Paketleri İndirme Yöneticisi (İster 2.3)
        sep_local = QFrame()
        sep_local.setFrameShape(QFrame.Shape.HLine)
        sep_local.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addRow(sep_local)

        packs_header = QLabel(t("settings.local_packs_title"))
        packs_header.setStyleSheet("font-weight: bold;")
        layout.addRow(packs_header)

        self.packs_table = QTableWidget(0, 4, tab)
        self.packs_table.setMinimumHeight(145)
        self.packs_table.setHorizontalHeaderLabels([
            t("settings.pack_col_pair"),
            t("settings.pack_col_size"),
            t("settings.pack_col_status"),
            t("settings.pack_col_action"),
        ])
        self.packs_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.packs_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        p_header = self.packs_table.horizontalHeader()
        if p_header is not None:
            p_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            p_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            p_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
            p_header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        layout.addRow(self.packs_table)

        pack_prog_row = QHBoxLayout()
        self.pack_progress_bar = QProgressBar()
        self.pack_progress_bar.setRange(0, 100)
        self.pack_progress_bar.setValue(0)
        self.pack_progress_bar.setVisible(False)
        self.pack_status_label = QLabel("")
        self.pack_status_label.setStyleSheet("color: #60a5fa; font-size: 11px;")
        pack_prog_row.addWidget(self.pack_progress_bar)
        pack_prog_row.addWidget(self.pack_status_label)
        layout.addRow("", pack_prog_row)

        self._refresh_packs_table()
        self._refresh_quota()
        self.tabs.addTab(tab, t("tab.translator"))

    def _refresh_packs_table(self) -> None:
        if not hasattr(self, "packs_table") or self.local_manager is None:
            return
        catalog = self.local_manager.list_catalog(ui_lang=self.cfg.general.ui_language)
        self.packs_table.setRowCount(len(catalog))
        is_busy = self._download_worker is not None and self._download_worker.isRunning()

        for row, item in enumerate(catalog):
            code = item["code"]
            installed = bool(item["installed"])
            self.packs_table.setItem(row, 0, QTableWidgetItem(f"{item['name']} [{code}]"))
            self.packs_table.setItem(row, 1, QTableWidgetItem(f"{item['size_mb']:.0f} MB"))
            status_item = QTableWidgetItem(
                t("settings.pack_installed") if installed else t("settings.pack_not_installed")
            )
            self.packs_table.setItem(row, 2, status_item)

            action_btn = QPushButton(
                t("settings.pack_btn_remove") if installed else t("settings.pack_btn_download")
            )
            action_btn.setProperty("pack_code", code)
            action_btn.setEnabled(not is_busy and not (installed and code == "EN-TR"))
            if installed:
                action_btn.clicked.connect(lambda _checked=False, c=code: self._remove_pack(c))
            else:
                action_btn.clicked.connect(lambda _checked=False, c=code: self._start_pack_download(c))
            self.packs_table.setCellWidget(row, 3, action_btn)

    def _start_pack_download(self, pack_code: str) -> None:
        if self._download_worker is not None and self._download_worker.isRunning():
            return
        self.pack_progress_bar.setVisible(True)
        self.pack_progress_bar.setValue(0)
        self.pack_status_label.setText(t("settings.pack_downloading", pack=pack_code, pct=0))

        self._download_worker = ModelDownloadWorker(self.local_manager, pack_code, self)
        self._download_worker.progressChanged.connect(self._on_pack_download_progress)
        self._download_worker.downloadFinished.connect(self._on_pack_download_finished)
        self._refresh_packs_table()
        self._download_worker.start()

    def _on_pack_download_progress(self, pack_code: str, pct: int) -> None:
        self.pack_progress_bar.setValue(pct)
        self.pack_status_label.setText(t("settings.pack_downloading", pack=pack_code, pct=pct))

    def _on_pack_download_finished(self, pack_code: str, ok: bool, msg: str) -> None:
        self.pack_progress_bar.setVisible(False)
        if ok:
            self.cfg.local_translator.installed_packs = self.local_manager.installed_packs()
            self.pack_status_label.setText(t("settings.pack_download_ok", pack=pack_code))
        else:
            self.pack_status_label.setText(t("settings.pack_download_err", pack=pack_code, err=msg))
        self._refresh_packs_table()

    def _remove_pack(self, pack_code: str) -> None:
        if self.local_manager is not None:
            self.local_manager.remove_pack(pack_code)
            self.cfg.local_translator.installed_packs = self.local_manager.installed_packs()
            self._refresh_packs_table()

    def _select_combo_data(self, combo: QComboBox, data_val: str) -> None:
        idx = combo.findData(data_val)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def _swap_languages(self) -> None:
        src = self.src_combo.currentData()
        tgt = self.tgt_combo.currentData()
        self._select_combo_data(self.src_combo, tgt)
        self._select_combo_data(self.tgt_combo, src)

    def _verify_and_refresh_quota(self) -> None:
        key = self.key_edit.text().strip()
        self.cfg.deepl.auth_key = key
        self.cfg.deepl.formality = self.formality_combo.currentData() or "default"
        if self.translator is not None:
            self.translator.update_config(self.cfg.deepl)
        self.quota_label.setText(t("settings.quota_loading"))
        QTimer.singleShot(100, self._refresh_quota)

    def _refresh_quota(self) -> None:
        if self.translator is not None:
            usage = self.translator.usage()
            if usage:
                count, limit = usage
                percent = int((count / max(1, limit)) * 100)
                remaining = max(0, limit - count)
                avail_percent = max(0, 100 - percent)
                self.quota_bar.setValue(min(100, percent))
                self.quota_label.setText(
                    t(
                        "settings.quota_info",
                        remaining=remaining,
                        limit=limit,
                        percent=avail_percent,
                        count=count,
                    )
                )
                if self.cfg.deepl.auth_key:
                    save_config(self.cfg)
                    if self.on_applied:
                        self.on_applied(self.cfg)
                return
        self.quota_bar.setValue(0)
        self.quota_label.setText(t("settings.quota_failed"))

    # ------------------------------------------------------------------ #
    # 2. Önbellek Sekmesi
    # ------------------------------------------------------------------ #
    def _build_cache_tab(self) -> None:
        tab = QWidget()
        layout = QFormLayout(tab)

        self.max_cache_spin = QSpinBox()
        self.max_cache_spin.setRange(100, 100_000)
        self.max_cache_spin.setSingleStep(500)
        self.max_cache_spin.setValue(self.cfg.cache.max_entries)
        layout.addRow(t("settings.max_cache"), self.max_cache_spin)

        self.cache_stats_label = QLabel()
        self._refresh_cache_stats()
        layout.addRow(t("settings.cache_status"), self.cache_stats_label)

        history_btn = QPushButton(t("settings.view_history"))
        history_btn.clicked.connect(self._open_history)
        layout.addRow(t("settings.history_label"), history_btn)

        clear_btn = QPushButton(t("settings.clear_cache"))
        clear_btn.setStyleSheet("color: #ff5555; padding: 4px 12px;")
        clear_btn.clicked.connect(self._clear_cache)
        layout.addRow("", clear_btn)

        self.tabs.addTab(tab, t("tab.cache"))

    def _open_history(self) -> None:
        if self.cache_store is not None:
            from .history_dialog import HistoryDialog
            dlg = HistoryDialog(self.cache_store, self)
            dlg.exec()
            self._refresh_cache_stats()

    def _refresh_cache_stats(self) -> None:
        if self.cache_store is not None:
            count, size_bytes = self.cache_store.stats()
            size_mb = size_bytes / (1024 * 1024)
            self.cache_stats_label.setText(t("settings.cache_stats", count=count, size_mb=size_mb))
        else:
            self.cache_stats_label.setText(t("settings.cache_unconnected"))

    def _clear_cache(self) -> None:
        reply = QMessageBox.question(
            self,
            t("settings.clear_cache_title"),
            t("settings.clear_cache_prompt"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes and self.cache_store:
            self.cache_store.clear()
            self._refresh_cache_stats()

    # ------------------------------------------------------------------ #
    # 3. Görünüm Sekmesi
    # ------------------------------------------------------------------ #
    def _build_appearance_tab(self) -> None:
        tab = QWidget()
        layout = QFormLayout(tab)

        # Dinamik Görsel Metin Hizalama (Tam Hizalama / Boyut / Renk)
        self.exact_alignment_check = QCheckBox(t("settings.exact_alignment"))
        self.exact_alignment_check.setChecked(getattr(self.cfg.overlay, "exact_alignment", True))
        layout.addRow(t("settings.exact_alignment_label"), self.exact_alignment_check)

        self.match_font_size_check = QCheckBox(t("settings.match_font_size"))
        self.match_font_size_check.setChecked(getattr(self.cfg.overlay, "match_font_size", True))
        self.match_font_size_check.setEnabled(self.exact_alignment_check.isChecked())
        layout.addRow("", self.match_font_size_check)

        self.match_text_color_check = QCheckBox(t("settings.match_text_color"))
        self.match_text_color_check.setChecked(getattr(self.cfg.overlay, "match_text_color", True))
        self.match_text_color_check.setEnabled(self.exact_alignment_check.isChecked())
        layout.addRow("", self.match_text_color_check)

        self.exact_alignment_check.toggled.connect(self.match_font_size_check.setEnabled)
        self.exact_alignment_check.toggled.connect(self.match_text_color_check.setEnabled)

        sep_align = QFrame()
        sep_align.setFrameShape(QFrame.Shape.HLine)
        sep_align.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addRow(sep_align)

        # KWin Blur Aç/Kapa
        self.blur_check = QCheckBox(t("settings.blur_kwin"))
        self.blur_check.setChecked(self.cfg.overlay.blur)
        layout.addRow(t("settings.bg_effect"), self.blur_check)

        # Bulanıklık Yoğunluğu
        blur_strength_row = QHBoxLayout()
        self.blur_strength_slider = QSlider(Qt.Orientation.Horizontal)
        self.blur_strength_slider.setRange(1, 15)
        self.blur_strength_slider.setValue(getattr(self.cfg.overlay, "blur_strength", 5))
        self.blur_strength_label = QLabel(t("settings.blur_level", v=self.blur_strength_slider.value()))
        self.blur_strength_slider.valueChanged.connect(
            lambda v: self.blur_strength_label.setText(t("settings.blur_level", v=v))
        )
        self.blur_strength_slider.sliderReleased.connect(
            lambda: set_kwin_blur_strength(self.blur_strength_slider.value())
        )
        blur_strength_row.addWidget(self.blur_strength_slider)
        blur_strength_row.addWidget(self.blur_strength_label)
        layout.addRow(t("settings.blur_strength"), blur_strength_row)

        # Opaklık Kaydırıcı (0 = Tamamen Şeffaf / Yalnızca Yazı)
        opacity_row = QHBoxLayout()
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(int(self.cfg.overlay.opacity * 100))
        self.opacity_label = QLabel(
            f"%{self.opacity_slider.value()}" if self.opacity_slider.value() > 0 else t("settings.opacity_transparent")
        )
        self.opacity_slider.valueChanged.connect(
            lambda v: self.opacity_label.setText(f"%{v}" if v > 0 else t("settings.opacity_transparent"))
        )
        opacity_row.addWidget(self.opacity_slider)
        opacity_row.addWidget(self.opacity_label)
        layout.addRow(t("settings.panel_opacity"), opacity_row)

        # Metin Gölgesi
        self.shadow_check = QCheckBox(t("settings.text_shadow"))
        self.shadow_check.setChecked(getattr(self.cfg.overlay, "text_shadow", True))
        layout.addRow(t("settings.text_shadow_label"), self.shadow_check)

        # Font Ayarları
        self.font_edit = QLineEdit(self.cfg.overlay.font_family)
        layout.addRow(t("settings.font_family"), self.font_edit)

        font_size_row = QHBoxLayout()
        self.font_min_spin = QSpinBox()
        self.font_min_spin.setRange(8, 24)
        self.font_min_spin.setValue(self.cfg.overlay.font_min)

        self.font_max_spin = QSpinBox()
        self.font_max_spin.setRange(16, 72)
        self.font_max_spin.setValue(self.cfg.overlay.font_max)

        font_size_row.addWidget(QLabel("Min:"))
        font_size_row.addWidget(self.font_min_spin)
        font_size_row.addWidget(QLabel("Max:"))
        font_size_row.addWidget(self.font_max_spin)
        layout.addRow(t("settings.font_range"), font_size_row)

        self.radius_spin = QSpinBox()
        self.radius_spin.setRange(0, 30)
        self.radius_spin.setValue(self.cfg.overlay.corner_radius)
        layout.addRow(t("settings.corner_radius"), self.radius_spin)

        self.tabs.addTab(tab, t("tab.appearance"))

    # ------------------------------------------------------------------ #
    # 4. Algılama ve Performans Sekmesi
    # ------------------------------------------------------------------ #
    def _build_capture_tab(self) -> None:
        tab = QWidget()
        layout = QFormLayout(tab)

        # Dinamik Pencere Seçimi Butonu (İster 3)
        self.select_window_btn = QPushButton(t("settings.btn_select_window"))
        self.select_window_btn.setStyleSheet(
            "QPushButton { background-color: #1e3a5f; color: #93c5fd; font-weight: bold; padding: 6px 12px; border-radius: 4px; }"
        )
        self.select_window_btn.clicked.connect(self._handle_select_window)
        layout.addRow(t("settings.target_window"), self.select_window_btn)

        # Donanım Hızlandırma Seçimi (GPU / CPU / Otomatik)
        self.hw_device_combo = QComboBox()
        self.hw_device_combo.addItem(t("device.auto"), "auto")
        self.hw_device_combo.addItem(t("device.gpu"), "gpu")
        self.hw_device_combo.addItem(t("device.cpu"), "cpu")
        initial_dev = getattr(self.cfg.ocr, "device", "auto")
        if initial_dev == "auto" and not getattr(self.cfg.ocr, "use_gpu", True):
            initial_dev = "cpu"
        self._select_combo_data(self.hw_device_combo, initial_dev)
        layout.addRow(t("settings.hw_device"), self.hw_device_combo)

        # Düşük Sistem (Low-End) Optimizasyonu Onay Kutusu
        self.low_end_check = QCheckBox(t("settings.low_end_mode"))
        self.low_end_check.setChecked(bool(getattr(self.cfg.ocr, "low_end_mode", False)))
        layout.addRow(t("settings.low_end_label"), self.low_end_check)

        self.fps_spin = QDoubleSpinBox()
        self.fps_spin.setRange(1.0, 30.0)
        self.fps_spin.setSingleStep(1.0)
        self.fps_spin.setValue(self.cfg.capture.fps)
        layout.addRow(t("settings.fps"), self.fps_spin)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["otsu", "adaptive", "none"])
        self.mode_combo.setCurrentText(self.cfg.preprocess.mode)
        layout.addRow(t("settings.preprocess_mode"), self.mode_combo)

        self.stable_spin = QSpinBox()
        self.stable_spin.setRange(1, 10)
        self.stable_spin.setValue(self.cfg.filter.stable_frames)
        layout.addRow(t("settings.stability_frames"), self.stable_spin)

        self.sim_spin = QSpinBox()
        self.sim_spin.setRange(50, 100)
        self.sim_spin.setValue(self.cfg.filter.similarity_threshold)
        layout.addRow(t("settings.similarity_threshold"), self.sim_spin)

        self.change_spin = QDoubleSpinBox()
        self.change_spin.setRange(0.1, 20.0)
        self.change_spin.setSingleStep(0.5)
        self.change_spin.setValue(self.cfg.preprocess.change_threshold)
        layout.addRow(t("settings.change_threshold"), self.change_spin)

        # Log Seviyesi Seçimi (İster 4)
        self.log_level_combo = QComboBox()
        self.log_level_combo.addItems(["INFO", "DEBUG", "WARNING", "ERROR"])
        self.log_level_combo.setCurrentText(self.cfg.general.log_level.upper())
        layout.addRow(t("settings.log_level"), self.log_level_combo)

        # Çok Dilli OCR Paketleri İndirme Yöneticisi (Aşama 18)
        sep_ocr_packs = QFrame()
        sep_ocr_packs.setFrameShape(QFrame.Shape.HLine)
        sep_ocr_packs.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addRow(sep_ocr_packs)

        ocr_packs_header = QLabel(t("settings.ocr_packs_title"))
        ocr_packs_header.setStyleSheet("font-weight: bold;")
        layout.addRow(ocr_packs_header)

        self.ocr_packs_table = QTableWidget(0, 4, tab)
        self.ocr_packs_table.setMinimumHeight(145)
        self.ocr_packs_table.setHorizontalHeaderLabels([
            t("settings.ocr_pack_col_lang"),
            t("settings.ocr_pack_col_size"),
            t("settings.ocr_pack_col_status"),
            t("settings.ocr_pack_col_action"),
        ])
        self.ocr_packs_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.ocr_packs_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        ocr_header = self.ocr_packs_table.horizontalHeader()
        if ocr_header is not None:
            ocr_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            ocr_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            ocr_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
            ocr_header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        layout.addRow(self.ocr_packs_table)

        ocr_prog_row = QHBoxLayout()
        self.ocr_pack_progress_bar = QProgressBar()
        self.ocr_pack_progress_bar.setRange(0, 100)
        self.ocr_pack_progress_bar.setValue(0)
        self.ocr_pack_progress_bar.setVisible(False)
        self.ocr_pack_status_label = QLabel("")
        self.ocr_pack_status_label.setStyleSheet("color: #60a5fa; font-size: 11px;")
        ocr_prog_row.addWidget(self.ocr_pack_progress_bar)
        ocr_prog_row.addWidget(self.ocr_pack_status_label)
        layout.addRow("", ocr_prog_row)

        self._refresh_ocr_packs_table()

        self.tabs.addTab(tab, t("tab.ocr"))

    def _refresh_ocr_packs_table(self) -> None:
        if not hasattr(self, "ocr_packs_table") or self.ocr_manager is None:
            return
        catalog = self.ocr_manager.list_catalog(ui_lang=self.cfg.general.ui_language)
        self.ocr_packs_table.setRowCount(len(catalog))
        is_busy = self._ocr_download_worker is not None and self._ocr_download_worker.isRunning()

        for row, item in enumerate(catalog):
            code = item["code"]
            installed = bool(item["installed"])
            default_inst = bool(item.get("default_installed", False))
            self.ocr_packs_table.setItem(row, 0, QTableWidgetItem(f"{item['name']} [{code}]"))
            self.ocr_packs_table.setItem(row, 1, QTableWidgetItem(f"{item['size_mb']:.1f} MB"))
            status_item = QTableWidgetItem(
                t("settings.pack_installed") if installed else t("settings.pack_not_installed")
            )
            self.ocr_packs_table.setItem(row, 2, status_item)

            action_btn = QPushButton(
                t("settings.pack_btn_remove") if installed else t("settings.pack_btn_download")
            )
            action_btn.setProperty("ocr_pack_code", code)
            action_btn.setEnabled(not is_busy and not (installed and default_inst))
            if installed:
                action_btn.clicked.connect(lambda _checked=False, c=code: self._remove_ocr_pack(c))
            else:
                action_btn.clicked.connect(lambda _checked=False, c=code: self._start_ocr_pack_download(c))
            self.ocr_packs_table.setCellWidget(row, 3, action_btn)

    def _start_ocr_pack_download(self, pack_code: str) -> None:
        if self._ocr_download_worker is not None and self._ocr_download_worker.isRunning():
            return
        self.ocr_pack_progress_bar.setVisible(True)
        self.ocr_pack_progress_bar.setValue(0)
        self.ocr_pack_status_label.setText(t("settings.ocr_pack_downloading", pack=pack_code, pct=0))

        self._ocr_download_worker = OcrModelDownloadWorker(self.ocr_manager, pack_code, self)
        self._ocr_download_worker.progressChanged.connect(self._on_ocr_pack_download_progress)
        self._ocr_download_worker.downloadFinished.connect(self._on_ocr_pack_download_finished)
        self._refresh_ocr_packs_table()
        self._ocr_download_worker.start()

    def _on_ocr_pack_download_progress(self, pack_code: str, pct: int) -> None:
        self.ocr_pack_progress_bar.setValue(pct)
        self.ocr_pack_status_label.setText(t("settings.ocr_pack_downloading", pack=pack_code, pct=pct))

    def _on_ocr_pack_download_finished(self, pack_code: str, ok: bool, msg: str) -> None:
        self.ocr_pack_progress_bar.setVisible(False)
        if ok:
            self.cfg.ocr.installed_ocr_packs = self.ocr_manager.installed_packs()
            save_config(self.cfg)
            if self.on_applied:
                self.on_applied(self.cfg)
            self.ocr_pack_status_label.setText(t("settings.ocr_pack_download_ok", pack=pack_code))
        else:
            self.ocr_pack_status_label.setText(t("settings.ocr_pack_download_err", pack=pack_code, err=msg))
        self._refresh_ocr_packs_table()

    def _remove_ocr_pack(self, pack_code: str) -> None:
        if self.ocr_manager is not None:
            self.ocr_manager.remove_pack(pack_code)
            self.cfg.ocr.installed_ocr_packs = self.ocr_manager.installed_packs()
            save_config(self.cfg)
            if self.on_applied:
                self.on_applied(self.cfg)
            self._refresh_ocr_packs_table()

    def _handle_select_window(self) -> None:
        self.lower()
        if self.on_select_window is not None:
            self.on_select_window()
            return
        from .window_picker import trigger_window_selection

        def _on_portal() -> None:
            self.cfg.capture.portal_restore_token = ""
            save_config(self.cfg)
            if self.on_applied:
                self.on_applied(self.cfg)

        def _on_wid(wid: int) -> None:
            self.cfg.capture.x11_window_id = wid
            save_config(self.cfg)
            if self.on_applied:
                self.on_applied(self.cfg)

        trigger_window_selection(_on_portal, _on_wid, parent=self)

    # ------------------------------------------------------------------ #
    # 5. Kısayollar Sekmesi (Tuş Kayıt Butonları ile)
    # ------------------------------------------------------------------ #
    def _build_hotkeys_tab(self) -> None:
        tab = QWidget()
        layout = QFormLayout(tab)

        self.hotkeys_enable_check = QCheckBox(t("settings.hotkeys_enable"))
        self.hotkeys_enable_check.setChecked(self.cfg.hotkeys.enabled)
        layout.addRow(t("settings.hotkeys_status"), self.hotkeys_enable_check)

        def _make_hotkey_row(initial_sc: str) -> tuple[QWidget, HotkeyButton]:
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            btn = HotkeyButton(initial_sc)
            clear_btn = QPushButton("✕")
            clear_btn.setToolTip(t("hotkeys.clear"))
            clear_btn.setFixedWidth(28)
            clear_btn.setStyleSheet("color: #8888aa; padding: 4px;")
            clear_btn.clicked.connect(lambda: btn.set_shortcut(""))
            row_layout.addWidget(btn)
            row_layout.addWidget(clear_btn)
            row_layout.addStretch()
            return row_widget, btn

        w_pause, self.hotkey_pause_btn = _make_hotkey_row(self.cfg.hotkeys.pause)
        layout.addRow(t("settings.hotkey_pause"), w_pause)

        w_roi, self.hotkey_roi_btn = _make_hotkey_row(self.cfg.hotkeys.select_roi)
        layout.addRow(t("settings.hotkey_roi"), w_roi)

        w_overlay, self.hotkey_overlay_btn = _make_hotkey_row(self.cfg.hotkeys.toggle_overlay)
        layout.addRow(t("settings.hotkey_overlay"), w_overlay)

        w_hist, self.hotkey_history_btn = _make_hotkey_row(self.cfg.hotkeys.history)
        layout.addRow(t("settings.hotkey_history"), w_hist)

        info_lbl = QLabel(t("settings.hotkeys_info"))
        info_lbl.setStyleSheet("color: #8888aa; font-size: 11px;")
        layout.addRow("", info_lbl)

        self.tabs.addTab(tab, t("tab.hotkeys"))

    # ------------------------------------------------------------------ #
    # Kaydetme (Pencereyi kapatmaz!)
    # ------------------------------------------------------------------ #
    def _save_changes(self) -> None:
        old_ui_lang = self.cfg.general.ui_language
        new_ui_lang = self.ui_lang_combo.currentData()

        self.cfg.general.ui_language = new_ui_lang
        set_language(new_ui_lang)

        self.cfg.general.source_lang = self.src_combo.currentData()
        self.cfg.general.target_lang = normalize_target_lang(self.tgt_combo.currentData())
        self.cfg.general.translation_engine = self.engine_combo.currentData() or "deepl"
        self.cfg.general.log_level = self.log_level_combo.currentText() or "INFO"
        logging.getLogger().setLevel(getattr(logging, self.cfg.general.log_level, logging.INFO))

        self.cfg.deepl.auth_key = self.key_edit.text().strip()
        self.cfg.deepl.formality = self.formality_combo.currentData() or "default"
        if self.translator is not None:
            self.translator.update_config(self.cfg.deepl, engine=self.cfg.general.translation_engine)
            self._refresh_quota()

        self.cfg.cache.max_entries = self.max_cache_spin.value()
        if self.cache_store is not None:
            self.cache_store.set_max_entries(self.cfg.cache.max_entries)

        self.cfg.overlay.exact_alignment = self.exact_alignment_check.isChecked()
        self.cfg.overlay.match_font_size = self.match_font_size_check.isChecked()
        self.cfg.overlay.match_text_color = self.match_text_color_check.isChecked()
        self.cfg.overlay.blur = self.blur_check.isChecked()
        self.cfg.overlay.blur_strength = self.blur_strength_slider.value()
        self.cfg.overlay.opacity = self.opacity_slider.value() / 100.0
        self.cfg.overlay.text_shadow = self.shadow_check.isChecked()
        self.cfg.overlay.font_family = self.font_edit.text().strip() or "sans-serif"
        self.cfg.overlay.font_min = self.font_min_spin.value()
        self.cfg.overlay.font_max = self.font_max_spin.value()
        self.cfg.overlay.corner_radius = self.radius_spin.value()

        self.cfg.capture.fps = self.fps_spin.value()
        self.cfg.preprocess.mode = self.mode_combo.currentText()
        self.cfg.filter.stable_frames = self.stable_spin.value()
        self.cfg.filter.similarity_threshold = self.sim_spin.value()
        self.cfg.preprocess.change_threshold = self.change_spin.value()

        chosen_dev = self.hw_device_combo.currentData() or "auto"
        self.cfg.ocr.device = chosen_dev
        self.cfg.ocr.low_end_mode = self.low_end_check.isChecked()
        self.cfg.ocr.use_gpu = (chosen_dev != "cpu") and not self.cfg.ocr.low_end_mode
        if self.ocr_manager is not None:
            self.cfg.ocr.installed_ocr_packs = self.ocr_manager.installed_packs()
        self.cfg.local_translator.device = "cpu" if (chosen_dev == "cpu" or self.cfg.ocr.low_end_mode) else chosen_dev

        self.cfg.hotkeys.enabled = self.hotkeys_enable_check.isChecked()
        self.cfg.hotkeys.pause = self.hotkey_pause_btn.current_shortcut()
        self.cfg.hotkeys.select_roi = self.hotkey_roi_btn.current_shortcut()
        self.cfg.hotkeys.toggle_overlay = self.hotkey_overlay_btn.current_shortcut()
        self.cfg.hotkeys.history = self.hotkey_history_btn.current_shortcut()

        save_config(self.cfg)
        log.info("Ayarlar güncellendi ve kaydedildi")

        if self.cfg.overlay.blur:
            set_kwin_blur_strength(self.cfg.overlay.blur_strength)

        if self.on_applied:
            self.on_applied(self.cfg)

        # Kullanıcıya görsel onay mesajı ver (pencereyi KAPATMADAN)
        self.status_msg_label.setText(t("msg.saved"))
        QTimer.singleShot(3000, lambda: self.status_msg_label.setText(""))

        # Eğer arayüz dili değiştiyse tüm sekmeleri ve metinleri anında yenile
        if old_ui_lang != new_ui_lang:
            self._retranslate_ui()

    def closeEvent(self, event: QCloseEvent) -> None:
        """Kullanıcı pencereyi çarpıdan veya Kapat butonundan kapattığında ayarları otomatik kaydeder."""
        self._save_changes()
        super().closeEvent(event)

    def _reset_to_defaults(self) -> None:
        """Tüm ayarları fabrika ayarlarına döndürür ve önbelleği temizler."""
        reply = QMessageBox.question(
            self,
            t("settings.reset_defaults_title"),
            t("settings.reset_defaults_confirm"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # DeepL API anahtarını, ROI ve oyun penceresini koru
        saved_key = self.cfg.deepl.auth_key
        saved_roi = self.cfg.capture.roi
        saved_win = self.cfg.capture.x11_window_id
        saved_token = self.cfg.capture.portal_restore_token
        current_ui_lang = self.cfg.general.ui_language

        # Varsayılan Config oluştur
        default_cfg = Config()
        default_cfg.deepl.auth_key = saved_key
        default_cfg.capture.roi = saved_roi
        default_cfg.capture.x11_window_id = saved_win
        default_cfg.capture.portal_restore_token = saved_token
        default_cfg.general.ui_language = current_ui_lang

        self.cfg = default_cfg
        save_config(self.cfg)

        # Eski takılı kalan önbellek kayıtlarını tamamen temizle
        if self.cache_store:
            self.cache_store.clear()

        # Boru hattını ve overlay'i yeni ayarlarla güncelle
        if self.on_applied:
            self.on_applied(self.cfg)

        self._retranslate_ui()
        self.status_msg_label.setText(t("settings.reset_defaults_success"))
        QTimer.singleShot(3500, lambda: self.status_msg_label.setText(""))

    def _retranslate_ui(self) -> None:
        """Arayüz dili değiştiğinde veya sıfırlandığında TÜM sekmeleri ve etiketleri anında dinamik olarak yeniden kurar."""
        curr_idx = self.tabs.currentIndex()

        while self.tabs.count() > 0:
            w = self.tabs.widget(0)
            self.tabs.removeTab(0)
            if w is not None:
                w.deleteLater()

        self._build_all_tabs()

        self.tabs.setCurrentIndex(min(curr_idx, max(0, self.tabs.count() - 1)))
        self.setWindowTitle(t("settings.title"))
        self.reset_defaults_btn.setText(t("btn.reset_defaults"))
        self.save_btn.setText(t("btn.save"))
        self.close_btn.setText(t("btn.close"))
