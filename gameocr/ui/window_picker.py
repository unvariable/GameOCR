"""Dinamik Pencere Seçimi Arayüzü (Wayland Portal, X11 Pencere Listesi ve Windows).

Sistemin oturum tipine (`XDG_SESSION_TYPE`) göre pencere seçimi yapar:
  * Wayland (`wayland`): `xdg-desktop-portal` (`ScreenCast.SelectSources`) üzerinden
    kompozitörün yerel pencere seçicisini tetikler.
  * X11 (`x11`): `xwininfo` / `python-xlib` ile açık pencerelerin listesini getirir;
    kullanıcının listeden program seçebileceği veya doğrudan ekranda pencereye
    tıklayabileceği (`crosshair`) bir menü/diyalog (`WindowPickerDialog`) açar.
  * Windows (`win32`): Win32 `EnumWindows` API'si ile açık pencereleri listeler.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..capture.base import session_type
from ..i18n import t
from ..logging_utils import log_stage_exception, timed_stage

log = logging.getLogger(__name__)


@dataclass(slots=True)
class WindowEntry:
    win_id: int
    title: str
    wm_class: str = ""
    width: int = 0
    height: int = 0

    @property
    def hex_id(self) -> str:
        return f"0x{self.win_id:x}"


def list_x11_windows() -> list[WindowEntry]:
    """X11 oturumunda açık ve görünür uygulama pencerelerini Xlib veya `xwininfo` ile listeler."""
    entries: list[WindowEntry] = []
    try:
        with timed_stage(log, "list_x11_windows", reraise=False):
            entries = _list_x11_via_xlib()
            if not entries and shutil.which("xwininfo"):
                entries = _list_x11_via_xwininfo()
    except Exception as exc:
        log_stage_exception(log, "list_x11_windows", exc)
    return entries


def _list_x11_via_xlib() -> list[WindowEntry]:
    try:
        from Xlib import X, Xatom, display
    except ImportError:
        return []

    results: list[WindowEntry] = []
    d = None
    try:
        d = display.Display()
        root = d.screen().root
        net_client_list = d.intern_atom("_NET_CLIENT_LIST")
        net_wm_name = d.intern_atom("_NET_WM_NAME")
        utf8_string = d.intern_atom("UTF8_STRING")

        prop = root.get_full_property(net_client_list, Xatom.WINDOW)
        win_ids: list[int] = list(prop.value) if prop is not None else []
        if not win_ids:
            tree = root.query_tree()
            win_ids = [w.id for w in tree.children]

        seen: set[int] = set()
        for wid in win_ids:
            wid_int = int(wid)
            if wid_int in seen or wid_int == 0:
                continue
            seen.add(wid_int)
            try:
                win = d.create_resource_object("window", wid_int)
                attrs = win.get_attributes()
                if attrs.map_state != X.IsViewable:
                    continue
                geom = win.get_geometry()
                if geom.width < 120 or geom.height < 80:
                    continue

                title = ""
                name_prop = win.get_full_property(net_wm_name, utf8_string)
                if name_prop and name_prop.value:
                    val = name_prop.value
                    title = val.decode("utf-8", errors="replace") if isinstance(val, bytes) else str(val)
                if not title:
                    wm_name = win.get_wm_name()
                    if wm_name:
                        title = wm_name.decode("utf-8", errors="replace") if isinstance(wm_name, bytes) else str(wm_name)

                title = (title or "").strip()
                if not title or "GameOCR" in title:
                    continue

                wm_class_tuple = win.get_wm_class()
                wm_class = wm_class_tuple[1] if wm_class_tuple and len(wm_class_tuple) > 1 else ""
                if wm_class.lower().strip() in ("plasmashell", "kwin", "krunner", "xwaylandvideobridge"):
                    continue

                results.append(
                    WindowEntry(
                        win_id=wid_int,
                        title=title,
                        wm_class=str(wm_class),
                        width=int(geom.width),
                        height=int(geom.height),
                    )
                )
            except Exception:
                continue
    except Exception as exc:
        log.debug("Xlib pencere listeleme uyarısı: %s", exc)
    finally:
        if d is not None:
            try:
                d.close()
            except Exception:
                pass
    return results


_XWININFO_LINE_RE = re.compile(
    r'^\s*(0x[0-9a-fA-F]+)\s+"([^"]+)":\s+\((?:"([^"]*)"\s*"([^"]*)")?\)\s+(\d+)x(\d+)\+'
)


def parse_xwininfo_output(raw_text: str) -> list[WindowEntry]:
    """`xwininfo -root -tree` çıktısını ayrıştırarak anlamlı uygulama pencerelerini döndürür."""
    entries: list[WindowEntry] = []
    seen: set[int] = set()
    for line in raw_text.splitlines():
        m = _XWININFO_LINE_RE.search(line)
        if not m:
            continue
        hex_id, title, cls1, cls2, w_str, h_str = m.groups()
        wid = int(hex_id, 16)
        w, h = int(w_str), int(h_str)
        title = title.strip()
        wm_cls = (cls2 or cls1 or "").strip()
        if wid in seen or w < 120 or h < 80 or not title or "GameOCR" in title:
            continue
        if wm_cls.lower() in ("plasmashell", "kwin", "desktop"):
            continue
        seen.add(wid)
        entries.append(WindowEntry(win_id=wid, title=title, wm_class=wm_cls, width=w, height=h))
    return entries


def _list_x11_via_xwininfo() -> list[WindowEntry]:
    if not shutil.which("xwininfo"):
        return []
    out = subprocess.run(
        ["xwininfo", "-root", "-tree"],
        capture_output=True,
        text=True,
        check=False,
        timeout=4.0,
    )
    if out.returncode != 0:
        return []
    return parse_xwininfo_output(out.stdout)


def select_x11_window_by_click() -> int | None:
    """Kullanıcının ekranda bir pencereye tıklayarak (xdotool veya xwininfo ile) XID seçmesini sağlar."""
    try:
        if shutil.which("xdotool"):
            out = subprocess.run(
                ["xdotool", "selectwindow"],
                capture_output=True,
                text=True,
                check=False,
                timeout=30.0,
            )
            if out.returncode == 0 and out.stdout.strip().isdigit():
                return int(out.stdout.strip())

        if shutil.which("xwininfo"):
            out = subprocess.run(
                ["xwininfo"],
                capture_output=True,
                text=True,
                check=False,
                timeout=30.0,
            )
            if out.returncode == 0:
                m = re.search(r"Window id:\s+(0x[0-9a-fA-F]+)", out.stdout)
                if m:
                    return int(m.group(1), 16)
    except Exception as exc:
        log_stage_exception(log, "select_x11_window_by_click", exc)
    return None


def list_win32_windows() -> list[WindowEntry]:
    """Windows (win32) üzerinde açık ve görünür pencereleri EnumWindows ile listeler."""
    if sys.platform != "win32":
        return []
    entries: list[WindowEntry] = []
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        class RECT(ctypes.Structure):
            _fields_ = [
                ("left", ctypes.c_long),
                ("top", ctypes.c_long),
                ("right", ctypes.c_long),
                ("bottom", ctypes.c_long),
            ]

        def _enum_cb(hwnd: int, _lparam: int) -> bool:
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value.strip()
            if not title or "GameOCR" in title:
                return True
            rect = RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            w = max(0, int(rect.right - rect.left))
            h = max(0, int(rect.bottom - rect.top))
            if w < 120 or h < 80:
                return True
            cls_buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls_buf, 256)
            entries.append(
                WindowEntry(win_id=int(hwnd), title=title, wm_class=cls_buf.value, width=w, height=h)
            )
            return True

        user32.EnumWindows(WNDENUMPROC(_enum_cb), 0)
    except Exception as exc:
        log_stage_exception(log, "list_win32_windows", exc)
    return entries


class WindowPickerDialog(QDialog):
    """X11 ve Windows ortamlarında açık pencereleri listeleyen ve tıklayarak seçime izin veren diyalog."""

    def __init__(
        self,
        entries: list[WindowEntry] | None = None,
        allow_click_pick: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("winpicker.title"))
        self.resize(620, 420)
        self.selected_window_id: int | None = None
        self._all_entries: list[WindowEntry] = (
            entries if entries is not None else (list_win32_windows() if sys.platform == "win32" else list_x11_windows())
        )
        self._filtered_entries: list[WindowEntry] = list(self._all_entries)

        layout = QVBoxLayout(self)

        # Üst bilgi ve arama çubuğu
        top_row = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(t("winpicker.search_ph"))
        self.search_edit.textChanged.connect(self._apply_filter)
        top_row.addWidget(self.search_edit)

        self.refresh_btn = QPushButton(t("winpicker.refresh"))
        self.refresh_btn.clicked.connect(self._refresh_list)
        top_row.addWidget(self.refresh_btn)

        if allow_click_pick and sys.platform != "win32":
            self.click_pick_btn = QPushButton(t("winpicker.pick_click"))
            self.click_pick_btn.setStyleSheet(
                "QPushButton { background-color: #1e3a5f; color: #93c5fd; font-weight: bold; padding: 6px 12px; border-radius: 4px; }"
            )
            self.click_pick_btn.clicked.connect(self._on_click_pick)
            top_row.addWidget(self.click_pick_btn)

        layout.addLayout(top_row)

        # Pencere Tablosu
        self.table = QTableWidget(0, 4, self)
        self.table.setHorizontalHeaderLabels([
            t("winpicker.col_id"),
            t("winpicker.col_title"),
            t("winpicker.col_class"),
            t("winpicker.col_size"),
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        header = self.table.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemDoubleClicked.connect(lambda *_: self._accept_selected())
        layout.addWidget(self.table)

        # Alt butonlar
        btn_row = QHBoxLayout()
        self.status_lbl = QLabel("")
        self.status_lbl.setStyleSheet("color: #9ca3af; font-size: 12px;")
        btn_row.addWidget(self.status_lbl)
        btn_row.addStretch()

        self.select_btn = QPushButton(t("winpicker.btn_select"))
        self.select_btn.setStyleSheet(
            "QPushButton { background-color: #2e6db4; color: white; font-weight: bold; padding: 6px 16px; border-radius: 4px; }"
        )
        self.select_btn.clicked.connect(self._accept_selected)
        btn_row.addWidget(self.select_btn)

        cancel_btn = QPushButton(t("btn.cancel"))
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        layout.addLayout(btn_row)
        self._populate_table()

    def _refresh_list(self) -> None:
        self._all_entries = list_win32_windows() if sys.platform == "win32" else list_x11_windows()
        self._apply_filter(self.search_edit.text())

    def _apply_filter(self, query: str) -> None:
        q = (query or "").strip().lower()
        if not q:
            self._filtered_entries = list(self._all_entries)
        else:
            self._filtered_entries = [
                e for e in self._all_entries
                if q in e.title.lower() or q in e.wm_class.lower() or q in e.hex_id.lower()
            ]
        self._populate_table()

    def _populate_table(self) -> None:
        self.table.setRowCount(len(self._filtered_entries))
        for row, entry in enumerate(self._filtered_entries):
            self.table.setItem(row, 0, QTableWidgetItem(entry.hex_id))
            self.table.setItem(row, 1, QTableWidgetItem(entry.title))
            self.table.setItem(row, 2, QTableWidgetItem(entry.wm_class))
            self.table.setItem(row, 3, QTableWidgetItem(f"{entry.width}x{entry.height}"))
        if self._filtered_entries:
            self.table.selectRow(0)
        self.status_lbl.setText(t("winpicker.count_status", count=len(self._filtered_entries)))

    def _accept_selected(self) -> None:
        row = self.table.currentRow()
        if 0 <= row < len(self._filtered_entries):
            self.selected_window_id = self._filtered_entries[row].win_id
            self.accept()

    def _on_click_pick(self) -> None:
        self.hide()
        wid = select_x11_window_by_click()
        if wid:
            self.selected_window_id = wid
            self.accept()
        else:
            self.show()


def trigger_window_selection(
    on_wayland_portal: Callable[[], None],
    on_window_id_selected: Callable[[int], None],
    parent: QWidget | None = None,
    force_session_type: str | None = None,
) -> str:
    """Oturum tipine (`XDG_SESSION_TYPE`) göre pencere seçimini tetikler.

    Dönüş değeri:
      * `"wayland"`: `xdg-desktop-portal` pencere seçimi tetiklendi.
      * `"x11"`: X11 pencere seçim diyaloğu açıldı.
      * `"win32"`: Windows pencere seçim diyaloğu açıldı.
    """
    if sys.platform == "win32" and not force_session_type:
        st = "win32"
    else:
        st = (force_session_type or session_type()).lower()

    log.info("Dinamik pencere seçimi başlatıldı (oturum tipi: %s)", st)

    if st == "wayland":
        on_wayland_portal()
        return "wayland"

    dlg = WindowPickerDialog(parent=parent)
    if dlg.exec() == int(QDialog.DialogCode.Accepted) and dlg.selected_window_id:
        on_window_id_selected(dlg.selected_window_id)
    return "win32" if st == "win32" else "x11"

