"""GameOCR Çeviri Geçmişi Penceresi (PyQt6 QDialog).

Kullanıcının daha önce çevrilmiş tüm replikleri ve metinleri arayabileceği,
kopyalayabileceği ve yönetebileceği modern bir geçmiş arayüzü sunar.
"""
from __future__ import annotations

import datetime
import logging
import sys
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..cache_store import CacheStore
from ..i18n import t

log = logging.getLogger(__name__)


class HistoryDialog(QDialog):
    def __init__(self, cache_store: CacheStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.cache_store = cache_store
        self._entries: list[dict[str, Any]] = []

        self.setWindowTitle(t("history.title"))
        self.resize(780, 560)

        layout = QVBoxLayout(self)

        # Üst Arama Çubuğu
        search_row = QHBoxLayout()
        search_label = QLabel("🔍")
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(t("history.search_ph"))
        self.search_edit.textChanged.connect(self._on_search_changed)
        self.search_edit.setClearButtonEnabled(True)

        search_row.addWidget(search_label)
        search_row.addWidget(self.search_edit)
        layout.addLayout(search_row)

        # Geçmiş Tablosu
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([
            t("history.col_time"),
            t("history.col_src_lang") + " → " + t("history.col_tgt_lang"),
            t("history.col_source"),
            t("history.col_target"),
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._on_row_selected)
        layout.addWidget(self.table)

        # Önizleme ve Detay Alanı
        detail_layout = QHBoxLayout()

        src_box = QVBoxLayout()
        src_box.addWidget(QLabel(t("history.col_source") + ":"))
        self.src_view = QTextEdit()
        self.src_view.setReadOnly(True)
        self.src_view.setMaximumHeight(80)
        src_box.addWidget(self.src_view)

        tgt_box = QVBoxLayout()
        tgt_box.addWidget(QLabel(t("history.col_target") + ":"))
        self.tgt_view = QTextEdit()
        self.tgt_view.setReadOnly(True)
        self.tgt_view.setMaximumHeight(80)
        tgt_box.addWidget(self.tgt_view)

        detail_layout.addLayout(src_box)
        detail_layout.addLayout(tgt_box)
        layout.addLayout(detail_layout)

        # Alt Butonlar
        btn_row = QHBoxLayout()
        self.status_label = QLabel("")

        copy_btn = QPushButton(t("btn.copy"))
        copy_btn.clicked.connect(self._copy_translation)

        delete_btn = QPushButton(t("btn.delete"))
        delete_btn.clicked.connect(self._delete_selected)

        clear_all_btn = QPushButton(t("btn.clear_all"))
        clear_all_btn.setStyleSheet("color: #ff5555;")
        clear_all_btn.clicked.connect(self._clear_all)

        close_btn = QPushButton(t("btn.close"))
        close_btn.clicked.connect(self.close)

        btn_row.addWidget(self.status_label)
        btn_row.addStretch()
        btn_row.addWidget(copy_btn)
        btn_row.addWidget(delete_btn)
        btn_row.addWidget(clear_all_btn)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self.reload_data()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if sys.platform == "win32":
            from ..capture.win32_backend import set_win32_exclude_from_capture

            set_win32_exclude_from_capture(int(self.winId()), exclude=True)

    def reload_data(self) -> None:
        query = self.search_edit.text().strip()
        self._entries = self.cache_store.get_history(limit=500, query=query)
        self._render_table()

    def _on_search_changed(self, text: str) -> None:
        self.reload_data()

    def _render_table(self) -> None:
        self.table.setRowCount(len(self._entries))
        for row_idx, item in enumerate(self._entries):
            ts = float(item.get("last_used", 0.0))
            time_str = datetime.datetime.fromtimestamp(ts).strftime("%H:%M:%S") if ts > 0 else "-"
            lang_str = f"{item.get('src_lang', '')} → {item.get('tgt_lang', '')}"

            item_time = QTableWidgetItem(time_str)
            item_lang = QTableWidgetItem(lang_str)
            item_src = QTableWidgetItem(str(item.get("source", "")))
            item_tgt = QTableWidgetItem(str(item.get("translation", "")))

            item_time.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_lang.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self.table.setItem(row_idx, 0, item_time)
            self.table.setItem(row_idx, 1, item_lang)
            self.table.setItem(row_idx, 2, item_src)
            self.table.setItem(row_idx, 3, item_tgt)

        total_count = self.cache_store.stats()[0]
        if self.search_edit.text().strip():
            self.status_label.setText(t("history.status_filtered", shown=len(self._entries), total=total_count))
        else:
            self.status_label.setText(t("history.status", total=len(self._entries)))

        if self._entries:
            self.table.selectRow(0)
        else:
            self.src_view.clear()
            self.tgt_view.clear()

    def _on_row_selected(self) -> None:
        row = self.table.currentRow()
        if 0 <= row < len(self._entries):
            item = self._entries[row]
            self.src_view.setPlainText(str(item.get("source", "")))
            self.tgt_view.setPlainText(str(item.get("translation", "")))

    def _copy_translation(self) -> None:
        text = self.tgt_view.toPlainText().strip()
        if text:
            clipboard = QApplication.clipboard()
            if clipboard is not None:
                clipboard.setText(text)

    def _delete_selected(self) -> None:
        row = self.table.currentRow()
        if 0 <= row < len(self._entries):
            item = self._entries[row]
            src = str(item.get("src_lang", ""))
            tgt = str(item.get("tgt_lang", ""))
            norm_key = str(item.get("norm_key", ""))
            self.cache_store.delete_entry(src, tgt, norm_key)
            self.reload_data()

    def _clear_all(self) -> None:
        reply = QMessageBox.question(
            self,
            t("history.clear_title"),
            t("history.clear_prompt"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.cache_store.clear()
            self.reload_data()
