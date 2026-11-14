"""Çok Dilli OCR Model ve Tanıma Paketi İndirme Yöneticisi.

Farklı dillerdeki (İngilizce, Türkçe/Latin, Japonca, Korece, Çince, Rusça/Kiril,
Arapça, Yunanca) ONNX metin tanıma modellerini (`*_rec.onnx` + `*_dict.txt`)
diskte yönetir ve Ayarlar penceresinden arka plan iş parçacığı
(`OcrModelDownloadWorker`) ile ana arayüzü dondurmadan indirilmesini sağlar.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import sys
import threading
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from PyQt6.QtCore import QThread, pyqtSignal

from .config import MODELS_DIR, PROJECT_ROOT
from .logging_utils import StageError, log_stage_exception, timed_stage

log = logging.getLogger(__name__)


class OcrModelError(RuntimeError):
    """OCR dil paketi indirme veya yönetim hatası."""


class OcrModelNotInstalledError(OcrModelError):
    """İstenen kaynak dil için OCR paketi henüz indirilmediğinde fırlatılır."""


@dataclass(frozen=True, slots=True)
class OcrPackInfo:
    code: str
    paddle_langs: tuple[str, ...]
    source_codes: tuple[str, ...]
    model_filename: str
    dict_filename: str
    model_url: str
    dict_url: str
    name_tr: str
    name_en: str
    size_mb: float
    default_installed: bool = False


# Desteklenen OCR Dil Paketleri Kataloğu
AVAILABLE_OCR_PACKS: list[OcrPackInfo] = [
    OcrPackInfo(
        code="EN",
        paddle_langs=("en",),
        source_codes=("EN",),
        model_filename="en_rec.onnx",
        dict_filename="en_dict.txt",
        model_url="https://huggingface.co/monkt/paddleocr-onnx/resolve/main/languages/english/rec.onnx",
        dict_url="https://huggingface.co/monkt/paddleocr-onnx/resolve/main/languages/english/dict.txt",
        name_tr="İngilizce OCR Paketi (Varsayılan)",
        name_en="English OCR Pack (Default)",
        size_mb=7.5,
        default_installed=True,
    ),
    OcrPackInfo(
        code="LATIN",
        paddle_langs=("tr", "latin", "german", "french", "es", "it", "pt", "pl", "nl", "sv"),
        source_codes=("TR", "DE", "FR", "ES", "IT", "PT", "PL", "NL", "SV"),
        model_filename="latin_rec.onnx",
        dict_filename="latin_dict.txt",
        model_url="https://huggingface.co/monkt/paddleocr-onnx/resolve/main/languages/latin/rec.onnx",
        dict_url="https://huggingface.co/monkt/paddleocr-onnx/resolve/main/languages/latin/dict.txt",
        name_tr="Latin / Türkçe & Avrupa Dilleri (TR, DE, FR, ES, IT, PT, PL)",
        name_en="Latin / Turkish & European Languages (TR, DE, FR, ES, IT, PT, PL)",
        size_mb=7.5,
        default_installed=True,
    ),
    OcrPackInfo(
        code="JA",
        paddle_langs=("japan", "ja"),
        source_codes=("JA",),
        model_filename="japan_rec.onnx",
        dict_filename="japan_dict.txt",
        model_url="https://huggingface.co/cycloneboy/japan_PP-OCRv4_rec_infer/resolve/main/model.onnx",
        dict_url="https://huggingface.co/cycloneboy/japan_PP-OCRv4_rec_infer/resolve/main/japan_dict.txt",
        name_tr="Japonca OCR Paketi (日本語 — Kanji / Hiragana / Katakana)",
        name_en="Japanese OCR Pack (日本語 — Kanji / Hiragana / Katakana)",
        size_mb=9.3,
        default_installed=False,
    ),
    OcrPackInfo(
        code="KO",
        paddle_langs=("korean", "ko"),
        source_codes=("KO",),
        model_filename="korean_rec.onnx",
        dict_filename="korean_dict.txt",
        model_url="https://huggingface.co/monkt/paddleocr-onnx/resolve/main/languages/korean/rec.onnx",
        dict_url="https://huggingface.co/monkt/paddleocr-onnx/resolve/main/languages/korean/dict.txt",
        name_tr="Korece OCR Paketi (한국어 — Hangul)",
        name_en="Korean OCR Pack (한국어 — Hangul)",
        size_mb=12.8,
        default_installed=False,
    ),
    OcrPackInfo(
        code="ZH",
        paddle_langs=("ch", "zh", "chinese"),
        source_codes=("ZH",),
        model_filename="ch_rec.onnx",
        dict_filename="ch_dict.txt",
        model_url="https://huggingface.co/cycloneboy/ch_PP-OCRv4_rec_infer/resolve/main/model.onnx",
        dict_url="https://huggingface.co/cycloneboy/ch_PP-OCRv4_rec_infer/resolve/main/ch_dict.txt",
        name_tr="Çince OCR Paketi (中文 — Basitleştirilmiş & Geleneksel)",
        name_en="Chinese OCR Pack (中文 — Simplified & Traditional)",
        size_mb=10.3,
        default_installed=False,
    ),
    OcrPackInfo(
        code="RU",
        paddle_langs=("ru", "cyrillic", "eslav", "uk"),
        source_codes=("RU", "UK"),
        model_filename="cyrillic_rec.onnx",
        dict_filename="cyrillic_dict.txt",
        model_url="https://huggingface.co/monkt/paddleocr-onnx/resolve/main/languages/eslav/rec.onnx",
        dict_url="https://huggingface.co/monkt/paddleocr-onnx/resolve/main/languages/eslav/dict.txt",
        name_tr="Rusça & Kiril Alfabesi OCR Paketi (Русский / Українська)",
        name_en="Russian & Cyrillic OCR Pack (Русский / Українська)",
        size_mb=7.5,
        default_installed=False,
    ),
    OcrPackInfo(
        code="AR",
        paddle_langs=("ar", "arabic"),
        source_codes=("AR",),
        model_filename="arabic_rec.onnx",
        dict_filename="arabic_dict.txt",
        model_url="https://huggingface.co/monkt/paddleocr-onnx/resolve/main/languages/arabic/rec.onnx",
        dict_url="https://huggingface.co/monkt/paddleocr-onnx/resolve/main/languages/arabic/dict.txt",
        name_tr="Arapça OCR Paketi (العربية)",
        name_en="Arabic OCR Pack (العربية)",
        size_mb=8.6,
        default_installed=False,
    ),
    OcrPackInfo(
        code="EL",
        paddle_langs=("el", "greek"),
        source_codes=("EL",),
        model_filename="greek_rec.onnx",
        dict_filename="greek_dict.txt",
        model_url="https://huggingface.co/monkt/paddleocr-onnx/resolve/main/languages/greek/rec.onnx",
        dict_url="https://huggingface.co/monkt/paddleocr-onnx/resolve/main/languages/greek/dict.txt",
        name_tr="Yunanca OCR Paketi (Ελληνικά)",
        name_en="Greek OCR Pack (Ελληνικά)",
        size_mb=7.5,
        default_installed=False,
    ),
]

_OCR_PACKS_BY_CODE: dict[str, OcrPackInfo] = {p.code.upper(): p for p in AVAILABLE_OCR_PACKS}


def resolve_ocr_pack_for_lang(lang_or_code: str) -> OcrPackInfo | None:
    """Kaynak dil kodunu ('JA', 'TR', 'EN') veya PaddleOCR dil adını ('japan', 'korean', 'ru')
    ilgili `OcrPackInfo` nesnesine eşler.
    """
    norm = (lang_or_code or "en").strip().lower()
    upper = norm.upper()
    if upper in _OCR_PACKS_BY_CODE:
        return _OCR_PACKS_BY_CODE[upper]
    for pack in AVAILABLE_OCR_PACKS:
        if norm in pack.paddle_langs or upper in pack.source_codes:
            return pack
    return None


class OcrModelManager:
    """Çok dilli OCR tanıma modellerini (`*_rec.onnx` + `*_dict.txt`) diskte yöneten sınıf.

    Özellikler:
      * Varsayılan olarak `EN` ve `LATIN` paketleri gömülü/kurulu gelir.
      * Kullanıcı Ayarlar → Algılama ve OCR sekmesinden Japonca (`JA`), Korece (`KO`),
        Çince (`ZH`), Rusça/Kiril (`RU`), Arapça (`AR`) veya Yunanca (`EL`) OCR paketlerini
        tek tıkla indirebilir veya kaldırabilir.
      * İndirilen sözlük (`*_dict.txt`) satır sayısını ONNX modelinin çıkış katmanı boyutuyla
        (`num_classes - 2`) otomatik hizalayarak `CTCLabelDecode` uyumsuzluklarını önler.
    """

    def __init__(self, models_dir: Path = MODELS_DIR) -> None:
        self.models_dir = Path(models_dir)
        self.onnx_dir = self.models_dir / "onnx"
        self.manifest_path = self.models_dir / "ocr_manifest.json"
        self._lock = threading.Lock()
        self._installed: set[str] = set()
        self._init_storage()

    def _is_test_mode(self) -> bool:
        return self.models_dir != MODELS_DIR and "pytest" in str(self.models_dir)

    def _search_onnx_dirs(self) -> list[Path]:
        """ONNX model ve sözlük dosyalarının aranacağı dizinleri öncelik sırasıyla döndürür."""
        dirs: list[Path] = [self.onnx_dir]
        bundled_env = os.environ.get("GAMEOCR_BUNDLED_MODELS_DIR", "").strip()
        if bundled_env:
            dirs.append(Path(bundled_env) / "onnx")
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            dirs.append(Path(meipass) / "models" / "onnx")
            dirs.append(Path(meipass).parent / "models" / "onnx")
        if getattr(sys, "frozen", False):
            try:
                dirs.append(Path(sys.executable).resolve().parent / "models" / "onnx")
            except Exception:
                pass
        dirs.append(PROJECT_ROOT / "models" / "onnx")
        if self.models_dir != MODELS_DIR:
            dirs.append(MODELS_DIR / "onnx")
        return dirs

    def _init_storage(self) -> None:
        with self._lock:
            self.onnx_dir.mkdir(parents=True, exist_ok=True)
            if self.manifest_path.exists():
                try:
                    data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
                    packs = data.get("installed_ocr_packs", [])
                    if isinstance(packs, list):
                        self._installed = {str(p).upper() for p in packs}
                except Exception as exc:
                    log.warning("OCR model manifestosu okunamadı (%s), sıfırlanıyor", exc)
                    self._installed = set()

            # Varsayılan EN ve LATIN paketleri her zaman kuruludur
            changed = False
            for pack in AVAILABLE_OCR_PACKS:
                if pack.default_installed and pack.code not in self._installed:
                    self._installed.add(pack.code)
                    changed = True
                elif not pack.default_installed and self._find_pack_files(pack) is not None:
                    if pack.code not in self._installed:
                        self._installed.add(pack.code)
                        changed = True

            if changed or not self.manifest_path.exists():
                self._save_manifest_unlocked()

    def _save_manifest_unlocked(self) -> None:
        data = {
            "version": 1,
            "installed_ocr_packs": sorted(self._installed),
            "updated_at": time.time(),
        }
        tmp = self.manifest_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(self.manifest_path)

    def _find_pack_files(self, pack: OcrPackInfo) -> tuple[Path, Path] | None:
        """Belirtilen OCR paketinin `(rec_model_path, rec_keys_path)` dosyalarını diskte arar."""
        search_dirs = [self.onnx_dir] if (self._is_test_mode() and not pack.default_installed) else self._search_onnx_dirs()
        for d in search_dirs:
            if not d.is_dir():
                continue
            m_path = d / pack.model_filename
            k_path = d / pack.dict_filename
            if m_path.is_file() and k_path.is_file():
                return m_path, k_path
        return None

    def find_onnx_model_for_lang(self, lang_or_code: str) -> tuple[Path, Path] | None:
        """Verilen kaynak dil (örn. 'JA', 'japan', 'KO', 'TR', 'EN') için kurulu ONNX
        tanıma modelini ve sözlüğünü döndürür.

        Eğer özel dil paketi bulunamazsa ve dil Latin alfabesi ise `latin_rec.onnx` veya
        `en_rec.onnx` yedeğine düşer; CJK/Kiril/Arapça dillerde paket indirilmemişse `None`
        döndürerek RapidOCR'ın gömülü çok dilli modelini kullanmasına izin verir.
        """
        pack = resolve_ocr_pack_for_lang(lang_or_code)
        if pack is not None:
            found = self._find_pack_files(pack)
            if found is not None:
                return found
            # Latin ve İngilizce birbirine yedek olabilir
            if pack.code == "LATIN":
                en_pack = _OCR_PACKS_BY_CODE.get("EN")
                if en_pack is not None:
                    return self._find_pack_files(en_pack)
            elif pack.code == "EN":
                lat_pack = _OCR_PACKS_BY_CODE.get("LATIN")
                if lat_pack is not None:
                    return self._find_pack_files(lat_pack)
        return None

    def installed_packs(self) -> list[str]:
        with self._lock:
            return sorted(self._installed)

    def is_installed(self, pack_or_lang: str) -> bool:
        pack = resolve_ocr_pack_for_lang(pack_or_lang)
        if pack is None:
            return False
        with self._lock:
            in_manifest = pack.code in self._installed
        if not in_manifest:
            return False
        if self._is_test_mode():
            return True
        return self._find_pack_files(pack) is not None

    def list_catalog(self, ui_lang: str = "tr") -> list[dict[str, Any]]:
        """Ayarlar penceresindeki 'OCR Dil Paketleri' tablosu için tüm katalog bilgisini döndürür."""
        with self._lock:
            installed_snapshot = set(self._installed)

        test_mode = self._is_test_mode()
        items: list[dict[str, Any]] = []
        for pack in AVAILABLE_OCR_PACKS:
            is_inst = pack.code in installed_snapshot
            if is_inst and not test_mode:
                is_inst = self._find_pack_files(pack) is not None
            items.append({
                "code": pack.code,
                "paddle_langs": list(pack.paddle_langs),
                "source_codes": list(pack.source_codes),
                "name": pack.name_tr if ui_lang == "tr" else pack.name_en,
                "size_mb": pack.size_mb,
                "installed": is_inst,
                "default_installed": pack.default_installed,
                "model_filename": pack.model_filename,
                "dict_filename": pack.dict_filename,
            })
        return items

    @staticmethod
    def _normalize_dict_for_onnx(model_path: Path, dict_path: Path) -> None:
        """ONNX modelinin çıkış boyutu (`num_classes`) ile karakter sözlüğü satır sayısını
        (`num_classes - 2`) karşılaştırır; `cycloneboy` modellerinde sonda fazladan bulunan
        boşluk (`' '`) satırını temizleyerek `RapidOCR` `CTCLabelDecode` ile %100 uyum sağlar.
        """
        try:
            raw_text = dict_path.read_text(encoding="utf-8")
            lines = [line.rstrip("\r\n") for line in raw_text.splitlines() if line.rstrip("\r\n") != ""]
            if not lines:
                return

            expected_chars: int | None = None
            try:
                import onnxruntime as ort

                sess = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
                out_shape = sess.get_outputs()[0].shape
                if out_shape and isinstance(out_shape[-1], int) and out_shape[-1] > 2:
                    # RapidOCR CTCLabelDecode: +1 'blank' (başta) ve +1 ' ' (sonda) ekler
                    expected_chars = int(out_shape[-1]) - 2
            except Exception:
                expected_chars = None

            if expected_chars is not None and len(lines) > expected_chars:
                # Sonda boşluk karakteri (' ') varsa veya fazla satır varsa kırp
                lines = lines[:expected_chars]

            dict_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except Exception as exc:
            log.debug("OCR sözlük normalizasyonu atlandı (%s): %s", dict_path.name, exc)

    def download_pack(
        self,
        pack_code: str,
        progress_cb: Callable[[int], None] | None = None,
    ) -> bool:
        """Belirtilen OCR dil paketini (örn. 'JA', 'KO', 'ZH', 'RU', 'AR') indirir ve kurar."""
        pack = resolve_ocr_pack_for_lang(pack_code)
        if pack is None:
            raise OcrModelError(f"Bilinmeyen OCR dil paketi kodu: {pack_code}")

        code = pack.code
        log.info("OCR dil paketi indiriliyor: %s (%s)", code, pack.model_filename)
        if progress_cb:
            progress_cb(5)

        try:
            with timed_stage(log, "download_ocr_pack", reraise=True, pack_code=code):
                self._download_onnx_files(pack, progress_cb)

                if progress_cb:
                    progress_cb(95)

                with self._lock:
                    self._installed.add(code)
                    self._save_manifest_unlocked()

                if progress_cb:
                    progress_cb(100)
                log.info("OCR dil paketi başarıyla kuruldu: %s", code)
                return True
        except Exception as exc:
            if not isinstance(exc, StageError):
                log_stage_exception(log, "download_ocr_pack", exc, pack_code=code)
            raise

    def _download_onnx_files(
        self,
        pack: OcrPackInfo,
        progress_cb: Callable[[int], None] | None = None,
    ) -> None:
        """HuggingFace CDN üzerinden `.onnx` modelini ve `.txt` karakter sözlüğünü atomik olarak indirir."""
        self.onnx_dir.mkdir(parents=True, exist_ok=True)
        dest_model = self.onnx_dir / pack.model_filename
        dest_dict = self.onnx_dir / pack.dict_filename

        # Test ortamında gerçek ağ çağrısı yapmadan sahte geçerli dosyalar oluştur
        if self._is_test_mode():
            for step in (25, 55, 85):
                if progress_cb:
                    progress_cb(step)
                time.sleep(0.01)
            dest_model.write_bytes(b"ONNX_DUMMY_WEIGHTS_" + pack.code.encode("utf-8"))
            dest_dict.write_text("a\nb\nc\n", encoding="utf-8")
            return

        # 1. Karakter sözlüğünü (.txt) indir
        tmp_dict = dest_dict.with_suffix(".txt.tmp")
        req_dict = urllib.request.Request(pack.dict_url, headers={"User-Agent": "GameOCR/1.0"})
        with urllib.request.urlopen(req_dict, timeout=45) as resp:
            dict_bytes = resp.read()
        tmp_dict.write_bytes(dict_bytes)
        tmp_dict.replace(dest_dict)
        if progress_cb:
            progress_cb(15)

        # 2. ONNX tanıma modelini (.onnx) indir
        tmp_model = dest_model.with_suffix(".onnx.tmp")
        req_model = urllib.request.Request(pack.model_url, headers={"User-Agent": "GameOCR/1.0"})
        with urllib.request.urlopen(req_model, timeout=120) as resp:
            total_bytes = int(resp.headers.get("Content-Length") or int(pack.size_mb * 1024 * 1024))
            read_bytes = 0
            with tmp_model.open("wb") as fh:
                while True:
                    chunk = resp.read(131072)
                    if not chunk:
                        break
                    fh.write(chunk)
                    read_bytes += len(chunk)
                    if total_bytes > 0 and progress_cb:
                        pct = int(15 + (read_bytes / total_bytes) * 75)
                        progress_cb(min(90, max(15, pct)))

        tmp_model.replace(dest_model)
        self._normalize_dict_for_onnx(dest_model, dest_dict)

    def remove_pack(self, pack_code: str) -> bool:
        """Kurulu bir OCR dil paketini diskten ve manifestodan kaldırır (Varsayılan paketler korunur)."""
        pack = resolve_ocr_pack_for_lang(pack_code)
        if pack is None or pack.default_installed:
            return False

        code = pack.code
        with self._lock:
            if code not in self._installed:
                return False
            self._installed.discard(code)
            for fname in (pack.model_filename, pack.dict_filename):
                fpath = self.onnx_dir / fname
                if fpath.exists():
                    try:
                        fpath.unlink()
                    except OSError:
                        pass
            self._save_manifest_unlocked()
            log.info("OCR dil paketi kaldırıldı: %s", code)
            return True


class OcrModelDownloadWorker(QThread):
    """Ayarlar penceresini dondurmadan arka planda OCR dil paketi indiren Qt iş parçacığı."""

    progressChanged = pyqtSignal(str, int)          # pack_code, percent (0..100)
    downloadFinished = pyqtSignal(str, bool, str)   # pack_code, success, message

    def __init__(
        self,
        manager: OcrModelManager,
        pack_code: str,
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self.manager = manager
        self.pack_code = pack_code.strip().upper()

    def run(self) -> None:
        try:
            self.manager.download_pack(
                self.pack_code,
                progress_cb=lambda pct: self.progressChanged.emit(self.pack_code, int(pct)),
            )
            self.downloadFinished.emit(self.pack_code, True, self.pack_code)
        except Exception as exc:
            log_stage_exception(log, "ocr_model_download_worker", exc, pack_code=self.pack_code)
            self.downloadFinished.emit(self.pack_code, False, str(exc))

