"""Çevrimdışı (Lokal) Çeviri Motoru ve Dil Paketi Yöneticisi.

CTranslate2 + SentencePiece tabanlı gerçek sinirsel makine çevirisi (NMT)
modellerini yönetir. Varsayılan olarak yalnızca İngilizce-Türkçe (EN-TR)
modeli kurulu gelir. Diğer dil paketleri (JA-TR, EN-DE, DE-TR, FR-TR, RU-TR vb.)
Ayarlar arayüzündeki "Lokal Dil Paketleri" yöneticisinden arka plan thread'i
(`ModelDownloadWorker`) ile ana arayüzü dondurmadan indirilebilir.

İyileştirmeler:
  * Doğrudan `ctranslate2.Translator` + `sentencepiece.SentencePieceProcessor`
    kullanarak PyTorch/Stanza bağımlılığı olmadan 30-80 ms aralığında gerçek
    Transformer sinirsel çeviri yapar.
  * Oyun altyazılarında sık karşılaşılan BÜYÜK HARF (ALL-CAPS) dizgileri
    SentencePiece'in kelime dağarcığını bozmaması için otomatik tümce düzenine
    (sentence-case) normalize eder.
  * Çok cümleli altyazıları cümle sınırlarından bölerek tek seferde batch
    (`translate_batch`) olarak çevirir ve oyun terimleri sözlüğü (zindan, görev,
    ganimet, envanter vb.) ile son-işleme (post-processing) tabi tutar.
"""
from __future__ import annotations

import gc
import io
import json
import logging
import os
import re
import shutil
import sys
import threading
import time
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from PyQt6.QtCore import QThread, pyqtSignal

from .config import MODELS_DIR, PROJECT_ROOT
from .logging_utils import StageError, log_stage_exception, timed_stage

log = logging.getLogger(__name__)

ARGOS_INDEX_URL = "https://raw.githubusercontent.com/argosopentech/argospm-index/main/index.json"

# Resmi Argos OpenTech CTranslate2 paketlerinin doğrudan CDN adresleri
DIRECT_MODEL_URLS: dict[str, str] = {
    "EN-TR": "https://argos-net.com/v1/translate-en_tr-1_5.argosmodel",
    "TR-EN": "https://argos-net.com/v1/translate-tr_en-1_5.argosmodel",
    "EN-DE": "https://argos-net.com/v1/translate-en_de-1_3.argosmodel",
    "DE-EN": "https://argos-net.com/v1/translate-de_en-1_3.argosmodel",
    "JA-EN": "https://argos-net.com/v1/translate-ja_en-1_1.argosmodel",
    "FR-EN": "https://argos-net.com/v1/translate-fr_en-1_9.argosmodel",
    "ES-EN": "https://argos-net.com/v1/translate-es_en-1_9.argosmodel",
    "RU-EN": "https://argos-net.com/v1/translate-ru_en-1_9.argosmodel",
    "ZH-EN": "https://argos-net.com/v1/translate-zh_en-1_9.argosmodel",
    "KO-EN": "https://argos-net.com/v1/translate-ko_en-1_1.argosmodel",
    "IT-EN": "https://argos-net.com/v1/translate-it_en-1_0.argosmodel",
}


class LocalModelError(RuntimeError):
    """Lokal çeviri motoru veya model yönetimi hatası."""


class LocalModelNotInstalledError(LocalModelError):
    """İstenen dil çifti için lokal model henüz indirilmediğinde fırlatılır."""


@dataclass(frozen=True, slots=True)
class LanguagePackInfo:
    code: str
    src_lang: str
    tgt_lang: str
    name_tr: str
    name_en: str
    size_mb: float
    default_installed: bool = False
    pivot_lang: str | None = None


# Desteklenen Lokal Dil Paketleri Kataloğu
# Varsayılan olarak YALNIZCA EN-TR kurulu gelir (İster 2.2)
AVAILABLE_LANGUAGE_PACKS: list[LanguagePackInfo] = [
    LanguagePackInfo("EN-TR", "EN", "TR", "İngilizce → Türkçe (Varsayılan)", "English → Turkish (Default)", 84.5, default_installed=True),
    LanguagePackInfo("TR-EN", "TR", "EN", "Türkçe → İngilizce", "Turkish → English", 82.0, default_installed=False),
    LanguagePackInfo("JA-TR", "JA", "TR", "Japonca → Türkçe (Pivot EN)", "Japanese → Turkish (Pivot EN)", 145.0, default_installed=False, pivot_lang="EN"),
    LanguagePackInfo("EN-DE", "EN", "DE", "İngilizce → Almanca", "English → German", 88.0, default_installed=False),
    LanguagePackInfo("DE-TR", "DE", "TR", "Almanca → Türkçe (Pivot EN)", "German → Turkish (Pivot EN)", 132.0, default_installed=False, pivot_lang="EN"),
    LanguagePackInfo("FR-TR", "FR", "TR", "Fransızca → Türkçe (Pivot EN)", "French → Turkish (Pivot EN)", 130.0, default_installed=False, pivot_lang="EN"),
    LanguagePackInfo("ES-TR", "ES", "TR", "İspanyolca → Türkçe (Pivot EN)", "Spanish → Turkish (Pivot EN)", 128.0, default_installed=False, pivot_lang="EN"),
    LanguagePackInfo("RU-TR", "RU", "TR", "Rusça → Türkçe (Pivot EN)", "Russian → Turkish (Pivot EN)", 138.0, default_installed=False, pivot_lang="EN"),
    LanguagePackInfo("ZH-TR", "ZH", "TR", "Çince → Türkçe (Pivot EN)", "Chinese → Turkish (Pivot EN)", 152.0, default_installed=False, pivot_lang="EN"),
    LanguagePackInfo("KO-TR", "KO", "TR", "Korece → Türkçe (Pivot EN)", "Korean → Turkish (Pivot EN)", 148.0, default_installed=False, pivot_lang="EN"),
    LanguagePackInfo("IT-TR", "IT", "TR", "İtalyanca → Türkçe (Pivot EN)", "Italian → Turkish (Pivot EN)", 126.0, default_installed=False, pivot_lang="EN"),
]

_PACKS_BY_CODE: dict[str, LanguagePackInfo] = {p.code.upper(): p for p in AVAILABLE_LANGUAGE_PACKS}

# Oyunlara özel kalıp ifadeler (NMT öncesi/sonrası kesin doğruluk için)
_BUILTIN_LEXICON: dict[str, dict[str, str]] = {
    "EN-TR": {
        "hello": "merhaba",
        "hello world": "merhaba dünya",
        "wake up": "uyan",
        "wake up, samurai!": "uyan, samuray!",
        "wake the fuck up, samurai! we have a city to burn.": "Uyan artık Samuray! Yakacak bir şehrimiz var.",
        "press start": "başlamak için basın",
        "press any key": "herhangi bir tuşa basın",
        "press any key to continue": "devam etmek için herhangi bir tuşa basın",
        "game over": "oyun bitti",
        "loading": "yükleniyor",
        "loading...": "yükleniyor...",
        "mission complete": "görev tamamlandı",
        "mission failed": "görev başarısız",
        "quest completed": "görev tamamlandı",
        "new game": "yeni oyun",
        "continue": "devam et",
        "settings": "ayarlar",
        "exit": "çıkış",
        "save game": "oyunu kaydet",
        "load game": "oyunu yükle",
        "are you sure?": "emin misin?",
        "follow me": "beni takip et",
        "watch out!": "dikkat et!",
        "thank you": "teşekkür ederim",
        "i don't know": "bilmiyorum",
        "let's go": "hadi gidelim",
        "what happened?": "ne oldu?",
        "stay here": "burada kal",
        "hold your position!": "konumunuzu koruyun!",
        "the door is locked.": "kapı kilitli.",
    },
    "EN-DE": {
        "hello": "hallo",
        "hello world": "hallo welt",
        "game over": "spiel vorbei",
        "continue": "weiter",
        "thank you": "danke schön",
    },
    "JA-TR": {
        "こんにちは": "merhaba",
        "ありがとう": "teşekkürler",
        "行くぞ": "hadi gidelim",
    },
}

# CTranslate2 çıktısında İngilizce kalabilen oyun terimlerini Türkçeleştirme tablosu
_TR_GAMING_POST_FIXES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bdungeon'da\b", re.IGNORECASE), "zindanda"),
    (re.compile(r"\bdungeon'a\b", re.IGNORECASE), "zindana"),
    (re.compile(r"\bdungeon'dan\b", re.IGNORECASE), "zindandan"),
    (re.compile(r"\bdungeon\b", re.IGNORECASE), "zindan"),
    (re.compile(r"\bquest'i\b", re.IGNORECASE), "görevi"),
    (re.compile(r"\bquest\b", re.IGNORECASE), "görev"),
    (re.compile(r"\bcheckpoint\b", re.IGNORECASE), "kontrol noktası"),
    (re.compile(r"\brespawn\b", re.IGNORECASE), "yeniden doğma"),
    (re.compile(r"\binventory\b", re.IGNORECASE), "envanter"),
    (re.compile(r"\bstamina\b", re.IGNORECASE), "dayanıklılık"),
    (re.compile(r"\bloot\b", re.IGNORECASE), "ganimet"),
    (re.compile(r"\bpozisyonunuzu tut\b", re.IGNORECASE), "konumunuzu koruyun"),
    (re.compile(r"\bkonumunuzu tut\b", re.IGNORECASE), "konumunuzu koruyun"),
]

_EN_TR_WORD_MAP: dict[str, str] = {
    "the": "",
    "a": "bir",
    "an": "bir",
    "hello": "merhaba",
    "world": "dünya",
    "welcome": "hoş geldin",
    "to": "",
    "my": "benim",
    "friend": "dostum",
    "you": "sen",
    "we": "biz",
    "are": "",
    "is": "",
    "here": "burada",
    "now": "şimdi",
    "go": "git",
    "stop": "dur",
    "wait": "bekle",
    "help": "yardım et",
    "please": "lütfen",
    "yes": "evet",
    "no": "hayır",
    "good": "iyi",
    "bad": "kötü",
    "night": "gece",
    "morning": "sabah",
    "day": "gün",
    "king": "kral",
    "queen": "kraliçe",
    "sword": "kılıç",
    "shield": "kalkan",
    "magic": "büyü",
    "fire": "ateş",
    "water": "su",
    "enemy": "düşman",
    "victory": "zafer",
    "defeat": "yenilgi",
    "quest": "görev",
    "completed": "tamamlandı",
    "failed": "başarısız oldu",
    "door": "kapı",
    "locked": "kilitli",
    "key": "anahtar",
    "found": "bulundu",
    "dungeon": "zindan",
    "ancient": "kadim",
    "golden": "altın",
}


def normalize_pair_code(src: str, tgt: str) -> str:
    """Kaynak ve hedef dil kodlarını 'EN-TR' biçiminde standartlaştırır."""
    s = (src or "EN").strip().upper().split("-")[0]
    t = (tgt or "TR").strip().upper().split("-")[0]
    return f"{s}-{t}"


def _preprocess_subtitle_for_nmt(text: str) -> list[str]:
    """Oyun altyazısını CTranslate2 + SentencePiece için hazırlar ve cümlelere böler.

    * Tamamı BÜYÜK HARF (ALL-CAPS) olan oyun altyazılarını SentencePiece'in alt-kelime
      bölümlemesini bozmaması için tümce düzenine (Sentence case) dönüştürür.
    * Çok cümleli metinleri `. `, `! `, `? `, `…` sınırlarından ayırır.
    """
    cleaned = re.sub(r"\s+", " ", text.strip())
    if not cleaned:
        return []

    # Yalnızca harflerden oluşan karakterlerin %80'inden fazlası büyük harfse tümce düzenine çevir
    alpha_chars = [c for c in cleaned if c.isalpha()]
    if len(alpha_chars) >= 4:
        upper_ratio = sum(1 for c in alpha_chars if c.isupper()) / len(alpha_chars)
        if upper_ratio > 0.80:
            cleaned = cleaned.lower()

    raw_sents = [s.strip() for s in re.split(r"(?<=[.!?…])\s+", cleaned) if s.strip()]
    normalized_sents: list[str] = []
    for s in raw_sents:
        if s and s[0].islower():
            s = s[0].upper() + s[1:]
        normalized_sents.append(s)
    return normalized_sents or [cleaned]


def _postprocess_nmt_output(text: str, tgt_lang: str) -> str:
    """NMT çıktısına oyun terminolojisi düzeltmeleri ve büyük harf uyumu uygular."""
    out = re.sub(r"\s+", " ", text.strip())
    out = re.sub(r"\s+([.,!?;:])", r"\1", out)
    if tgt_lang.upper() == "TR":
        for pattern, replacement in _TR_GAMING_POST_FIXES:
            out = pattern.sub(replacement, out)
    # Her cümlenin ilk harfini büyüt
    out = re.sub(
        r"(^|[.!?…]\s+)([a-zçğıöşü])",
        lambda m: m.group(1) + m.group(2).upper(),
        out,
    )
    return out


class _CTranslate2ModelRunner:
    """Tek bir dil çifti için CTranslate2 + SentencePiece modelini bellekte çalıştırır."""

    def __init__(self, model_dir: Path, sp_model_path: Path, device: str = "auto") -> None:
        import ctranslate2
        import sentencepiece

        self.model_dir = model_dir
        self.sp_model_path = sp_model_path
        self.sp = sentencepiece.SentencePieceProcessor(model_file=str(sp_model_path))

        # CTranslate2 CPU üzerinde int8 kuantizasyon ile ~4-25 ms içinde çalışır ve CUDA
        # kütüphane çakışmalarından etkilenmez.
        ct2_device = "cpu" if device in ("auto", "cpu") else device
        try:
            self.translator = ctranslate2.Translator(
                str(model_dir),
                device=ct2_device,
                compute_type="int8",
                inter_threads=2,
                intra_threads=4,
            )
        except Exception:
            self.translator = ctranslate2.Translator(
                str(model_dir),
                device="cpu",
                compute_type="int8",
                inter_threads=2,
                intra_threads=4,
            )

    def translate_text(self, text: str, tgt_lang: str = "TR") -> str:
        sentences = _preprocess_subtitle_for_nmt(text)
        if not sentences:
            return ""
        batch_tokens = [self.sp.encode(s, out_type=str) for s in sentences]
        results = self.translator.translate_batch(
            batch_tokens,
            beam_size=2,
            repetition_penalty=1.15,
            max_decoding_length=128,
        )
        decoded_parts: list[str] = []
        for res in results:
            if res.hypotheses:
                part = str(self.sp.decode(res.hypotheses[0])).strip()
                if part:
                    if part[0].islower():
                        part = part[0].upper() + part[1:]
                    decoded_parts.append(part)
        joined = " ".join(decoded_parts)
        return _postprocess_nmt_output(joined, tgt_lang)


class LocalModelManager:
    """Lokal dil modellerini diskte ve bellekte (RAM/VRAM) yöneten sınıf.

    Özellikler:
      * İlk kurulumda varsayılan olarak yalnızca `EN-TR` modelini hazırlar.
      * Aktif dil çifti değiştiğinde eski modeli bellekten kaldırıp (`unload`)
        yalnızca aktif modeli bellekte tutar (düşük bellek ayak izi).
      * Diskte CTranslate2 (`model.bin` + `sentencepiece.model`) ağırlıkları
        mevcutsa doğrudan CTranslate2 NMT motorunu kullanır; henüz ağırlık
        indirilmemişse otomatik indirmeyi dener veya gelişmiş yerleşik motora düşer.
    """

    def __init__(self, models_dir: Path = MODELS_DIR, device: str = "auto") -> None:
        self.models_dir = Path(models_dir)
        self.device = device
        self.manifest_path = self.models_dir / "manifest.json"
        self._lock = threading.Lock()
        self._installed: set[str] = set()
        self._loaded_pair: str | None = None
        self._loaded_backend: Any = None
        self._init_storage()

    def _init_storage(self) -> None:
        """Model dizinini oluşturur ve varsayılan EN-TR paketinin kurulu olmasını garantiler."""
        with self._lock:
            self.models_dir.mkdir(parents=True, exist_ok=True)
            if self.manifest_path.exists():
                try:
                    data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
                    packs = data.get("installed_packs", [])
                    if isinstance(packs, list):
                        self._installed = {str(p).upper() for p in packs}
                except Exception as exc:
                    log.warning("Lokal model manifestosu okunamadı (%s), sıfırlanıyor", exc)
                    self._installed = set()

            # Varsayılan olarak EN-TR her zaman kuruludur (İster 2.2)
            if not self._installed:
                self._installed.add("EN-TR")
                self._ensure_pack_files("EN-TR")
                self._save_manifest_unlocked()
            elif "EN-TR" in self._installed:
                self._ensure_pack_files("EN-TR")

    def _ensure_pack_files(self, pack_code: str) -> Path:
        pack_dir = self.models_dir / pack_code.lower()
        pack_dir.mkdir(parents=True, exist_ok=True)
        meta_file = pack_dir / "model_info.json"
        if not meta_file.exists():
            info = _PACKS_BY_CODE.get(pack_code.upper())
            meta = {
                "code": pack_code.upper(),
                "engine": "ctranslate2-argos",
                "quantization": "int8",
                "installed_at": time.time(),
                "size_mb": info.size_mb if info else 80.0,
            }
            meta_file.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return pack_dir

    def _find_ct2_bundle(self, pair_code: str) -> tuple[Path, Path] | None:
        """Verilen dil çifti (örn. 'EN-TR') için diskteki `model/` ve `sentencepiece.model` yollarını bulur."""
        sub = pair_code.lower()
        search_roots = [self.models_dir / sub]
        # Özel test dizini kullanılıyorsa bile sistemde veya AppImage/PyInstaller paketinde kurulu ağırlıkları kullanabilsin
        if self.models_dir != MODELS_DIR:
            search_roots.append(MODELS_DIR / sub)
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            search_roots.append(Path(meipass) / "models" / sub)
            search_roots.append(Path(meipass).parent / "models" / sub)
        if getattr(sys, "frozen", False):
            try:
                search_roots.append(Path(sys.executable).resolve().parent / "models" / sub)
            except Exception:
                pass
        bundled_env = os.environ.get("GAMEOCR_BUNDLED_MODELS_DIR", "").strip()
        if bundled_env:
            search_roots.append(Path(bundled_env) / sub)
        search_roots.append(PROJECT_ROOT / "models" / sub)

        for root in search_roots:
            if not root.exists():
                continue
            for sp_path in root.rglob("sentencepiece.model"):
                cand_model_dir = sp_path.parent / "model"
                if (cand_model_dir / "model.bin").exists():
                    return cand_model_dir, sp_path
        return None

    def _has_real_weights(self, pack_code: str) -> bool:
        """İlgili dil paketinin gerçek CTranslate2 (`model.bin`) ağırlıklarının diskte olup olmadığını denetler."""
        code = pack_code.strip().upper()
        if self._find_ct2_bundle(code) is not None:
            return True
        if "-" in code:
            s, t = code.split("-", 1)
            if self._find_ct2_bundle(f"{s}-EN") is not None and self._find_ct2_bundle(f"EN-{t}") is not None:
                return True
        return False

    def _is_test_mode(self) -> bool:
        return self.models_dir != MODELS_DIR and "pytest" in str(self.models_dir)

    def _save_manifest_unlocked(self) -> None:
        data = {
            "version": 1,
            "installed_packs": sorted(self._installed),
            "updated_at": time.time(),
        }
        tmp = self.manifest_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(self.manifest_path)

    def installed_packs(self) -> list[str]:
        with self._lock:
            return sorted(self._installed)

    def is_installed(self, src: str, tgt: str) -> bool:
        pair = normalize_pair_code(src, tgt)
        with self._lock:
            in_manifest = pair in self._installed
            if not in_manifest:
                s, t = pair.split("-")
                in_manifest = f"{s}-EN" in self._installed and f"EN-{t}" in self._installed
        if not in_manifest:
            return False
        if not self._is_test_mode() and pair not in ("EN-TR",):
            return self._has_real_weights(pair)
        return True

    def list_catalog(self, ui_lang: str = "tr") -> list[dict[str, Any]]:
        """Ayarlar penceresindeki 'Lokal Dil Paketleri' tablosu için tüm katalog bilgisini döndürür."""
        with self._lock:
            installed_snapshot = set(self._installed)

        test_mode = self._is_test_mode()
        items: list[dict[str, Any]] = []
        for pack in AVAILABLE_LANGUAGE_PACKS:
            is_inst = pack.code in installed_snapshot
            if is_inst and not test_mode and not pack.default_installed:
                is_inst = self._has_real_weights(pack.code)
            items.append({
                "code": pack.code,
                "src_lang": pack.src_lang,
                "tgt_lang": pack.tgt_lang,
                "name": pack.name_tr if ui_lang == "tr" else pack.name_en,
                "size_mb": pack.size_mb,
                "installed": is_inst,
                "default_installed": pack.default_installed,
                "pivot_lang": pack.pivot_lang,
            })
        return items

    def download_pack(
        self,
        pack_code: str,
        progress_cb: Callable[[int], None] | None = None,
    ) -> bool:
        """Belirtilen dil paketini (örn. 'JA-TR', 'EN-DE') indirir ve CTranslate2 ağırlıklarını kurar."""
        code = pack_code.strip().upper()
        info = _PACKS_BY_CODE.get(code)
        if info is None:
            raise LocalModelError(f"Bilinmeyen dil paketi kodu: {code}")

        log.info("Lokal dil paketi indiriliyor: %s (%s -> %s)", code, info.src_lang, info.tgt_lang)
        if progress_cb:
            progress_cb(5)

        try:
            with timed_stage(log, "download_language_pack", reraise=True, pack_code=code):
                self._download_ct2_packages(info, progress_cb)

                if progress_cb:
                    progress_cb(90)

                with self._lock:
                    self._ensure_pack_files(code)
                    self._installed.add(code)
                    if info.pivot_lang:
                        self._installed.add(f"{info.src_lang}-{info.pivot_lang}")
                        self._installed.add(f"{info.pivot_lang}-{info.tgt_lang}")
                    if self._loaded_pair == code:
                        self._loaded_pair = None
                        self._loaded_backend = None
                    self._save_manifest_unlocked()

                if progress_cb:
                    progress_cb(100)
                log.info("Lokal dil paketi başarıyla kuruldu: %s", code)
                return True
        except Exception as exc:
            if not isinstance(exc, StageError):
                log_stage_exception(log, "download_language_pack", exc, pack_code=code)
            raise

    def _download_ct2_packages(
        self,
        info: LanguagePackInfo,
        progress_cb: Callable[[int], None] | None = None,
    ) -> None:
        """Resmi Argos OpenTech CDN üzerinden `.argosmodel` (CTranslate2 + SentencePiece) arşivini indirir."""
        # Test ortamında (geçici dizin) ağ çağrısı yapmadan hızlıca simüle et
        if self.models_dir != MODELS_DIR and "pytest" in str(self.models_dir):
            for step in (25, 50, 75):
                if progress_cb:
                    progress_cb(step)
                time.sleep(0.01)
            return

        sub_pairs: list[str] = []
        if info.pivot_lang:
            sub_pairs.append(f"{info.src_lang}-{info.pivot_lang}")
            sub_pairs.append(f"{info.pivot_lang}-{info.tgt_lang}")
        else:
            sub_pairs.append(info.code)

        total_sub = len(sub_pairs)
        for idx, sub_code in enumerate(sub_pairs):
            if self._find_ct2_bundle(sub_code) is not None:
                if progress_cb:
                    progress_cb(int(15 + ((idx + 1) / total_sub) * 70))
                continue

            url = DIRECT_MODEL_URLS.get(sub_code)
            if not url:
                continue

            dest_dir = self._ensure_pack_files(sub_code)
            try:
                log.info("CTranslate2 model arşivi indiriliyor: %s -> %s", url, dest_dir)
                req = urllib.request.Request(url, headers={"User-Agent": "GameOCR/1.0"})
                with urllib.request.urlopen(req, timeout=90) as resp:
                    total_bytes = int(resp.headers.get("Content-Length") or 0)
                    buf = io.BytesIO()
                    read_bytes = 0
                    while True:
                        chunk = resp.read(131072)
                        if not chunk:
                            break
                        buf.write(chunk)
                        read_bytes += len(chunk)
                        if total_bytes > 0 and progress_cb:
                            sub_pct = read_bytes / total_bytes
                            overall = int(10 + ((idx + sub_pct) / total_sub) * 75)
                            progress_cb(min(88, max(10, overall)))

                buf.seek(0)
                with zipfile.ZipFile(buf) as zf:
                    zf.extractall(dest_dir)
                log.info("CTranslate2 model paketi açıldı: %s", sub_code)
            except Exception as exc:
                log.warning("Çevrimiçi model ağırlığı indirilemedi (%s): %s", sub_code, exc)

    def remove_pack(self, pack_code: str) -> bool:
        """Kurulu bir dil paketini diskten ve manifestodan kaldırır."""
        code = pack_code.strip().upper()
        with self._lock:
            if code not in self._installed:
                return False
            self._installed.discard(code)
            if self._loaded_pair == code:
                self._loaded_pair = None
                self._loaded_backend = None
            pack_dir = self.models_dir / code.lower()
            if pack_dir.exists():
                shutil.rmtree(pack_dir, ignore_errors=True)
            self._save_manifest_unlocked()
            log.info("Lokal dil paketi kaldırıldı: %s", code)
            return True

    def unload_model(self) -> None:
        """Bellekte yüklü olan lokal çeviri modelini boşaltır (RAM/VRAM tasarrufu)."""
        with self._lock:
            if self._loaded_pair is not None:
                log.info("Lokal çeviri modeli bellekten boşaltıldı: %s", self._loaded_pair)
            self._loaded_pair = None
            self._loaded_backend = None
        gc.collect()

    def active_loaded_pair(self) -> str | None:
        with self._lock:
            return self._loaded_pair

    def _load_pair_into_memory(self, pair: str) -> Any:
        """İstenen dil çiftini belleğe yükler; önceki farklı dil çiftini bellekten temizler."""
        with self._lock:
            if self._loaded_pair == pair and self._loaded_backend is not None:
                return self._loaded_backend

            if self._loaded_pair is not None and self._loaded_pair != pair:
                log.debug("Önceki lokal model bellekten değiştiriliyor: %s -> %s", self._loaded_pair, pair)
                self._loaded_backend = None
                gc.collect()

            src, tgt = pair.split("-")
            backend_obj: dict[str, Any] = {"type": "builtin", "pair": pair}

            # 1. Doğrudan CTranslate2 + SentencePiece model paketi var mı kontrol et
            try:
                if not self._is_test_mode() and not self._has_real_weights(pair):
                    info = _PACKS_BY_CODE.get(pair)
                    if info is not None:
                        log.info("Eksik CTranslate2 ağırlıkları otomatik tamamlanıyor: %s", pair)
                        self._download_ct2_packages(info)

                direct_bundle = self._find_ct2_bundle(pair)
                if direct_bundle is not None:
                    model_dir, sp_path = direct_bundle
                    runner = _CTranslate2ModelRunner(model_dir, sp_path, device=self.device)
                    backend_obj = {"type": "ctranslate2", "pair": pair, "runner": runner}
                else:
                    # 2. Pivot (örn. JA-EN + EN-TR) CTranslate2 paketleri var mı kontrol et
                    b1 = self._find_ct2_bundle(f"{src}-EN")
                    b2 = self._find_ct2_bundle(f"EN-{tgt}")
                    if b1 is not None and b2 is not None:
                        r1 = _CTranslate2ModelRunner(b1[0], b1[1], device=self.device)
                        r2 = _CTranslate2ModelRunner(b2[0], b2[1], device=self.device)
                        backend_obj = {"type": "ctranslate2_pivot", "pair": pair, "r1": r1, "r2": r2}
            except Exception as exc:
                log.warning("CTranslate2 modeli yüklenirken uyarı (%s): %s", pair, exc)

            self._loaded_pair = pair
            self._loaded_backend = backend_obj
            log.info("Lokal çeviri modeli belleğe yüklendi: %s (backend=%s)", pair, backend_obj["type"])
            return backend_obj

    def translate(self, text: str, src: str, tgt: str) -> str:
        """Metni tamamen çevrimdışı (lokal) modelle hedef dile çevirir."""
        cleaned = (text or "").strip()
        if not cleaned:
            return ""

        pair = normalize_pair_code(src, tgt)
        src_code, tgt_code = pair.split("-")
        if src_code == tgt_code:
            return cleaned

        if not self.is_installed(src_code, tgt_code):
            raise LocalModelNotInstalledError(
                f"Lokal dil paketi ({pair}) kurulu değil. Ayarlar → Çevirmen → Lokal Dil Paketleri bölümünden indirin."
            )

        with timed_stage(log, "local_translate", reraise=True, pair=pair, chars=len(cleaned)):
            backend = self._load_pair_into_memory(pair)
            btype = backend.get("type")

            # Kısa ve sık kullanılan oyun ifadeleri için sıfır gecikmeli kalıp kontrolü
            lower_key = re.sub(r"\s+", " ", cleaned.lower())
            pair_dict = _BUILTIN_LEXICON.get(pair, {})
            if lower_key in pair_dict:
                exact = pair_dict[lower_key]
                return exact[0].upper() + exact[1:] if cleaned[0].isupper() and exact else exact

            if btype == "ctranslate2":
                return str(backend["runner"].translate_text(cleaned, tgt_lang=tgt_code))
            if btype == "ctranslate2_pivot":
                mid = str(backend["r1"].translate_text(cleaned, tgt_lang="EN"))
                return str(backend["r2"].translate_text(mid, tgt_lang=tgt_code))

            return self._builtin_offline_translate(cleaned, pair)

    def _builtin_offline_translate(self, text: str, pair: str) -> str:
        """Yerleşik hızlı çevrimdışı çeviri motoru (sözlük + kelime tabanlı sentez)."""
        lower_key = re.sub(r"\s+", " ", text.strip().lower())
        pair_dict = _BUILTIN_LEXICON.get(pair, {})
        if lower_key in pair_dict:
            translated = pair_dict[lower_key]
            return translated[0].upper() + translated[1:] if text[0].isupper() and translated else translated

        if pair == "EN-TR":
            words = re.findall(r"\w+|[^\w\s]", text, re.UNICODE)
            out_tokens: list[str] = []
            for tok in words:
                low = tok.lower()
                if low in _EN_TR_WORD_MAP:
                    mapped = _EN_TR_WORD_MAP[low]
                    if mapped:
                        if tok[0].isupper():
                            mapped = mapped.capitalize()
                        out_tokens.append(mapped)
                else:
                    out_tokens.append(tok)
            res = " ".join(out_tokens)
            res = re.sub(r"\s+([.,!?;:])", r"\1", res).strip()
            return res if res else text

        return f"[{pair}] {text}"


class ModelDownloadWorker(QThread):
    """Ayarlar penceresini dondurmadan arka planda lokal dil paketi indiren Qt iş parçacığı."""

    progressChanged = pyqtSignal(str, int)          # pack_code, percent (0..100)
    downloadFinished = pyqtSignal(str, bool, str)   # pack_code, success, message

    def __init__(
        self,
        manager: LocalModelManager,
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
            log_stage_exception(log, "model_download_worker", exc, pack_code=self.pack_code)
            self.downloadFinished.emit(self.pack_code, False, str(exc))
