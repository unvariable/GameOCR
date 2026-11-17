"""Kalıcı çeviri önbelleği (SQLite + bellek içi indeks).

* Kayıtlar dil çiftine göre ayrılır: (src_lang, tgt_lang, norm_key).
* Aktif dil çiftinin anahtarları bellekte tutulur; bulanık arama
  RapidFuzz ile bu liste üzerinde yapılır (disk erişimi gerekmez).
* ``max_entries`` aşılınca en uzun süredir kullanılmayan kayıtlar
  silinir (LRU).
* Filter, Translator ve UI thread'leri aynı nesneyi kullanır; tüm
  erişim tek bir kilitle seri hale getirilir.
"""
from __future__ import annotations

import logging
import sqlite3
import threading
import time
from pathlib import Path

from rapidfuzz import fuzz, process

from .security import harden_private_path

log = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS translations (
    src_lang    TEXT NOT NULL,
    tgt_lang    TEXT NOT NULL,
    norm_key    TEXT NOT NULL,
    source      TEXT NOT NULL,
    translation TEXT NOT NULL,
    hits        INTEGER NOT NULL DEFAULT 0,
    last_used   REAL NOT NULL,
    PRIMARY KEY (src_lang, tgt_lang, norm_key)
);
CREATE INDEX IF NOT EXISTS idx_last_used ON translations(last_used);
"""

# Bu uzunluğun altındaki metinlerde bulanık eşleşme yapılmaz
# ("Yes" ile "Yet" gibi kısa kelimelerin karışmaması için).
MIN_FUZZY_LEN = 8


class CacheStore:
    def __init__(self, path: Path, max_entries: int = 5000) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        harden_private_path(self.path.parent, is_dir=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(self.path), check_same_thread=False)
        harden_private_path(self.path, is_dir=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=NORMAL")
        self._db.executescript(_SCHEMA)
        # Eski sürümde ağırlık indirilmeden önbelleğe yazılmış '[TR-EN] ...' yer tutucu kayıtları temizle
        self._db.execute(r"DELETE FROM translations WHERE translation GLOB '\[[A-Z]*-[A-Z]*\] *'")
        self._db.commit()
        self._max_entries = max(1, int(max_entries))
        self._pair: tuple[str, str] = ("", "")
        self._index: dict[str, str] = {}   # norm_key -> translation (aktif dil çifti)

    # ------------------------------------------------------------------ #
    def set_lang_pair(self, src: str, tgt: str) -> None:
        with self._lock:
            self._pair = (src, tgt)
            rows = self._db.execute(
                "SELECT norm_key, translation FROM translations WHERE src_lang=? AND tgt_lang=?",
                self._pair,
            ).fetchall()
            self._index = dict(rows)
        log.info("Önbellek: %s→%s için %d kayıt yüklendi", src, tgt, len(self._index))

    def lookup(self, norm_key: str, threshold: int = 90) -> str | None:
        """Önce birebir arama yapar.

        Bulanık arama yalnızca kelime sayıları tam olarak eşit ve benzerliği
        en az `threshold` (ve en az %90) olan minör OCR harf hatalarında geçerlidir;
        uzayan, eksik veya farklı cümleler asla önbellekten dönmez.
        """
        with self._lock:
            key = norm_key if norm_key in self._index else None
            if key is None and len(norm_key) >= MIN_FUZZY_LEN and self._index:
                cutoff = max(threshold, 90)
                match = process.extractOne(
                    norm_key, self._index.keys(), scorer=fuzz.ratio, score_cutoff=cutoff
                )
                if match is not None:
                    matched_key = match[0]
                    # Biri diğerinin eksik daktilo parçası veya uzantısı olamaz (kelime sayıları eşit olmalı)
                    if len(norm_key.split()) == len(matched_key.split()):
                        key = matched_key

            if key is None:
                return None
            self._db.execute(
                "UPDATE translations SET hits=hits+1, last_used=? "
                "WHERE src_lang=? AND tgt_lang=? AND norm_key=?",
                (time.time(), *self._pair, key),
            )
            self._db.commit()
            return self._index[key]

    def put(self, src: str, tgt: str, norm_key: str, source: str, translation: str) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO translations(src_lang, tgt_lang, norm_key, source, translation, hits, last_used) "
                "VALUES (?,?,?,?,?,0,?) "
                "ON CONFLICT(src_lang, tgt_lang, norm_key) DO UPDATE SET "
                "translation=excluded.translation, last_used=excluded.last_used",
                (src, tgt, norm_key, source, translation, time.time()),
            )
            if (src, tgt) == self._pair:
                self._index[norm_key] = translation
            self._evict_locked()
            self._db.commit()

    # ------------------------------------------------------------------ #
    def set_max_entries(self, n: int) -> None:
        with self._lock:
            self._max_entries = max(1, int(n))
            self._evict_locked()
            self._db.commit()

    @property
    def max_entries(self) -> int:
        return self._max_entries

    def _evict_locked(self) -> None:
        (count,) = self._db.execute("SELECT COUNT(*) FROM translations").fetchone()
        excess = count - self._max_entries
        if excess <= 0:
            return
        victims = self._db.execute(
            "SELECT src_lang, tgt_lang, norm_key FROM translations ORDER BY last_used ASC LIMIT ?",
            (excess,),
        ).fetchall()
        self._db.executemany(
            "DELETE FROM translations WHERE src_lang=? AND tgt_lang=? AND norm_key=?", victims
        )
        for s, t, k in victims:
            if (s, t) == self._pair:
                self._index.pop(k, None)
        log.debug("Önbellek: %d eski kayıt silindi (LRU)", len(victims))

    def clear(self) -> None:
        with self._lock:
            self._db.execute("DELETE FROM translations")
            self._db.commit()
            self._db.execute("VACUUM")
            self._index.clear()
        log.info("Önbellek temizlendi")

    def stats(self) -> tuple[int, int]:
        """(kayıt sayısı, diskteki toplam bayt)."""
        with self._lock:
            (count,) = self._db.execute("SELECT COUNT(*) FROM translations").fetchone()
        size = 0
        for suffix in ("", "-wal", "-shm"):
            p = Path(str(self.path) + suffix)
            if p.exists():
                size += p.stat().st_size
        return count, size

    def get_history(self, limit: int = 500, query: str = "") -> list[dict[str, object]]:
        """Çeviri geçmişini en yeniden eskiye doğru döndürür."""
        with self._lock:
            if query.strip():
                sql = (
                    "SELECT src_lang, tgt_lang, norm_key, source, translation, hits, last_used "
                    "FROM translations WHERE source LIKE ? OR translation LIKE ? "
                    "ORDER BY last_used DESC LIMIT ?"
                )
                q = f"%{query.strip()}%"
                rows = self._db.execute(sql, (q, q, limit)).fetchall()
            else:
                sql = (
                    "SELECT src_lang, tgt_lang, norm_key, source, translation, hits, last_used "
                    "FROM translations ORDER BY last_used DESC LIMIT ?"
                )
                rows = self._db.execute(sql, (limit,)).fetchall()
            return [
                {
                    "src_lang": r[0],
                    "tgt_lang": r[1],
                    "norm_key": r[2],
                    "source": r[3],
                    "translation": r[4],
                    "hits": r[5],
                    "last_used": r[6],
                }
                for r in rows
            ]

    def delete_entry(self, src: str, tgt: str, norm_key: str) -> None:
        """Belirli bir çeviri kaydını önbellekten siler."""
        with self._lock:
            self._db.execute(
                "DELETE FROM translations WHERE src_lang=? AND tgt_lang=? AND norm_key=?",
                (src, tgt, norm_key),
            )
            self._db.commit()
            if (src, tgt) == self._pair:
                self._index.pop(norm_key, None)

    def close(self) -> None:
        with self._lock:
            try:
                self._db.commit()
                self._db.close()
            except sqlite3.Error:
                pass
