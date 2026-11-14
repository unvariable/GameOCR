"""Gereksiz DeepL isteklerini önleyen akıllı metin filtresi.

Özellikler:
  1. Daktilo (Typewriter) Koruması: Metin harf harf veya kelime kelime akarken
     çeviri isteği atılmaz. Metin durulup en az `settle_time` (0.45s) boyunca
     sabit kaldığında tek bir kez çevrilir.
  2. Zaman Aşımı Tetiklemesi (check_pending): ChangeGate kareyi bloklasa bile
     FilterWorker zaman aşımı dolduğunda bekleyen metni anında çeviriye gönderir.
  3. Tekrar Önleme: Son işlenen altyazıyla benzerse (%90) tekrar istek atılmaz.
  4. Yankı Koruması: Ekranda gösterilen çeviri metnine benziyorsa yok sayılır.
  5. Önbellek: SQLite önbelleğinde varsa doğrudan gösterilir (0 API kotası).
  6. Sönme: Altyazı ekrandan kaybolduğunda overlay otomatik söndürülür (CLEAR).
"""
from __future__ import annotations

import enum
import re
import time
from dataclasses import dataclass

from rapidfuzz import fuzz

from .cache_store import CacheStore
from .config import FilterConfig

_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_SPACE_RE = re.compile(r"\s+")
_UI_TAGS_RE = re.compile(r"\s+\b(AUTO|SKIP|LOG|BACK|LOAD|SAVE|CONFIG)\b(\s*\d+)?\s*$", re.IGNORECASE)
_INLINE_TAGS_RE = re.compile(r"\b(SPEAKING)\b", re.IGNORECASE)
_RESOLUTION_BADGE_RE = re.compile(r"\b\d{3,4}\s*[x×*·]\s*\d{3,4}\b", re.IGNORECASE)
_STRAY_BARS_RE = re.compile(r"\s*\|\s*")


def clean_game_text(text: str) -> str:
    """Oyun arayüzündeki statik butonları (AUTO, SKIP, SPEAKING vb.), çözünürlük etiketlerini ve gürültüleri temizler."""
    t = _UI_TAGS_RE.sub("", text.strip())
    t = _INLINE_TAGS_RE.sub("", t)
    t = _RESOLUTION_BADGE_RE.sub("", t)
    t = _STRAY_BARS_RE.sub(" ", t)
    return _SPACE_RE.sub(" ", t).strip()


def normalize(text: str) -> str:
    """Karşılaştırma ve önbellek anahtarı için metni sadeleştirir."""
    t = text.replace("|", "I").casefold()
    t = _PUNCT_RE.sub(" ", t)
    return _SPACE_RE.sub(" ", t).strip()


_TERMINAL_PUNCT = (
    ".", "!", "?", "…", "...", "—", "--", "-", "\"", "'", "”", "’",
    "。", "！", "？", "…", "」", "』", "～", "~"
)


def is_sentence_complete(text: str) -> bool:
    """Metnin cümle sonu noktalama işaretiyle veya replik sonu göstergesiyle bitip bitmediğini kontrol eder."""
    t = clean_game_text(text).strip()
    if not t:
        return False
    return any(t.endswith(p) for p in _TERMINAL_PUNCT)


class Action(enum.Enum):
    IGNORE = "ignore"
    CLEAR = "clear"
    SHOW_CACHED = "show_cached"
    TRANSLATE = "translate"


@dataclass(slots=True)
class Decision:
    action: Action
    text: str = ""        # SHOW_CACHED: çeviri, TRANSLATE: kaynak metin
    norm_key: str = ""


class TextFilter:
    def __init__(self, cfg: FilterConfig, cache: CacheStore | None = None) -> None:
        self.cfg = cfg
        self.cache = cache
        self.reset()

    def reset(self) -> None:
        self._last_norm = ""           # En son çevrilmiş/gösterilmiş tam metin
        self._shown_norm = ""          # Ekrana yansıtılmış Türkçe çevirinin normalize hali
        self._empty_count = 0
        self._empty_since = 0.0        # Boş kare algılanmaya başlandığı zaman damgası
        self._cleared = True

        # Daktilo / Debounce değişkenleri
        self._pending_text = ""        # Yazılmakta olan aday metin
        self._pending_norm = ""        # Aday metnin normalize hali
        self._last_change_ts = 0.0     # Metnin en son uzadığı/değiştiği zaman damgası
        self._is_typing = False        # Metnin daktilo gibi aktığı tespit edildi mi?
        self._typewriter_updates = 0   # Kaç kare boyunca uzadı?
        self._stable_count = 0         # Kaç kez sabit okundu?

    def set_shown(self, translation: str) -> None:
        self._shown_norm = normalize(translation)
        self._cleared = False
        self._empty_count = 0
        self._empty_since = 0.0

    def _similar(self, a: str, b: str) -> bool:
        return bool(a) and bool(b) and fuzz.ratio(a, b) >= self.cfg.similarity_threshold

    def _is_self_capture_echo(self, norm: str) -> bool:
        """Ekranda gösterilen çeviri metninin (overlay) ekran yakalamasına sızıp
        orijinal metinle karışması (self-capture geri besleme döngüsü) durumunu tespit eder.
        """
        if not norm:
            return False
        if "gameocr universal" in norm or "oyun0" in norm:
            return True
        if self._shown_norm and len(self._shown_norm) >= 6:
            if self._similar(norm, self._shown_norm):
                return True
            # Overlay çevirisi orijinal metnin üzerine çizildiğinde ikisi birleşmiş olabilir
            if len(norm) >= len(self._shown_norm) and fuzz.partial_ratio(self._shown_norm, norm) >= 82:
                return True
            # Gösterilen çevirinin kelimelerinin büyük kısmı yeni okumada geçiyorsa yankıdır
            shown_tokens = [w for w in self._shown_norm.split() if len(w) >= 4]
            if len(shown_tokens) >= 2:
                norm_tokens = set(norm.split())
                hits = sum(1 for w in shown_tokens if w in norm_tokens)
                if hits / len(shown_tokens) >= 0.65:
                    return True
        return False

    def _is_typewriter_extension(self, prev_norm: str, new_norm: str) -> bool:
        """Yeni metin eskisinin sonuna kelime eklenerek uzayan bir daktilo akışı mı?"""
        if not prev_norm or not new_norm:
            return False
        # Metin aynı veya daha kısaysa uzama değildir
        if len(new_norm) <= len(prev_norm):
            return False
        if new_norm.startswith(prev_norm):
            return True
        if fuzz.partial_ratio(prev_norm, new_norm) >= 85:
            return True
        if fuzz.token_set_ratio(prev_norm, new_norm) >= 85:
            return True
        return False

    def check_pending(
        self,
        now: float | None = None,
        is_ocr_busy: bool = False,
        is_stable: bool = False,
    ) -> Decision:
        """Kuyrukta yeni kare olmasa bile durulma süresi dolan bekleyen metni çeviriye gönderir
        veya ekranda gösterilen altyazı kaybolduğunda overlay'i temizler (CLEAR).
        """
        if now is None:
            now = time.monotonic()

        # 1. Boş Ekran Zaman Aşımı Kontrolü:
        # Eğer ekranda gösterilen bir altyazı varsa ve son gelen kare boş idiyse,
        # ChangeGate kareleri kesse bile belirli bir süre sonra altyazıyı temizle
        if not self._cleared and self._empty_since > 0.0:
            if now - self._empty_since >= 0.75:
                self._pending_text = ""
                self._pending_norm = ""
                self._cleared = True
                self._last_norm = ""
                self._shown_norm = ""
                self._empty_since = 0.0
                self._empty_count = 0
                self._is_typing = False
                self._typewriter_updates = 0
                self._stable_count = 0
                return Decision(Action.CLEAR)

        if not self._pending_norm:
            return Decision(Action.IGNORE)

        # Eğer OCR şu anda değişen yeni bir kare üzerinde çıkarım yapıyorsa,
        # eski/eksik metni aceleyle çeviriye gönderme!
        if is_ocr_busy:
            return Decision(Action.IGNORE)

        # En son çevrilmiş metinle aynıysa veya overlay yankısıysa tekrar çevrilmez
        if self._similar(self._pending_norm, self._last_norm) or self._is_self_capture_echo(self._pending_norm):
            return Decision(Action.IGNORE)

        dwell_time = now - self._last_change_ts
        base_settle = max(0.05, getattr(self.cfg, "settle_time", 0.35))

        # Akıllı daktilo ve cümle tamamlama analizi
        raw_text = clean_game_text(self._pending_text).strip()
        complete = is_sentence_complete(raw_text)

        if complete:
            # Cümle sonu noktalaması var (. ! ? ... - vb.)
            settle_threshold = base_settle
        else:
            # Cümle henüz tamamlanmamış
            ends_with_continuation = raw_text.endswith((",", ";", ":"))
            if ends_with_continuation:
                # Virgül veya iki nokta gibi ara duraklamalarda ekstra bekle
                settle_threshold = base_settle * 1.8
            elif (self._is_typing or self._typewriter_updates >= 1) and self._stable_count == 0 and not is_stable:
                # Daktilo akışı aktif, henüz cümle sonu gelmedi ve metin henüz durulmadı
                settle_threshold = base_settle * 1.6
            else:
                # Statik menü veya aynı kalan metin
                settle_threshold = base_settle

        if is_stable or self._stable_count >= 1:
            settle_threshold = min(settle_threshold, base_settle)

        if dwell_time >= settle_threshold:
            ready_text = clean_game_text(self._pending_text) or self._pending_text
            ready_norm = normalize(ready_text)

            self._last_norm = self._pending_norm
            self._pending_text = ""
            self._pending_norm = ""
            self._is_typing = False
            self._typewriter_updates = 0
            self._stable_count = 0

            thr = self.cfg.similarity_threshold
            if self.cache is not None:
                cached = self.cache.lookup(ready_norm, thr)
                if cached is not None:
                    return Decision(Action.SHOW_CACHED, cached, ready_norm)

            return Decision(Action.TRANSLATE, ready_text, ready_norm)

        return Decision(Action.IGNORE)

    def process(self, text: str, is_stable: bool = False) -> Decision:
        now = time.monotonic()
        norm = normalize(text)

        # 1) Altyazı ekranda yok veya çok kısa
        if len(norm.replace(" ", "")) < self.cfg.min_chars:
            if not self._empty_since:
                self._empty_since = now
            self._empty_count += 1
            if not self._cleared:
                if self._empty_count >= self.cfg.clear_after_empty_frames or (now - self._empty_since >= 0.75):
                    self._pending_text = ""
                    self._pending_norm = ""
                    self._cleared = True
                    self._last_norm = ""
                    self._shown_norm = ""
                    self._empty_since = 0.0
                    self._empty_count = 0
                    self._is_typing = False
                    self._typewriter_updates = 0
                    self._stable_count = 0
                    return Decision(Action.CLEAR)
            return Decision(Action.IGNORE)

        self._empty_count = 0
        self._empty_since = 0.0

        # 2) Tekrar ve Yankı (Self-Capture) Koruması
        if self._similar(norm, self._last_norm) or self._is_self_capture_echo(norm):
            return Decision(Action.IGNORE)

        # 3) Daktilo / Genişleme ve Durulma (Debounce) Mantığı
        if self._pending_norm:
            # Durum A: Metin hala yazılıyor (daktilo gibi uzuyor)
            if self._is_typewriter_extension(self._pending_norm, norm):
                self._pending_text = text
                self._pending_norm = norm
                self._last_change_ts = now
                self._is_typing = True
                self._typewriter_updates += 1
                self._stable_count = 0
                return Decision(Action.IGNORE)

            # Durum B: Metin aynı kaldı (yazım durdu veya ChangeGate stabilite karesi)
            if self._similar(norm, self._pending_norm):
                self._stable_count += 1
                return self.check_pending(now, is_stable=is_stable)

            # Durum C: Bambaşka yeni bir replik başladı
            self._pending_text = text
            self._pending_norm = norm
            self._last_change_ts = now
            self._is_typing = False
            self._typewriter_updates = 0
            self._stable_count = 0
            return Decision(Action.IGNORE)

        # Eğer daha önce bir metin çevrilmişti ama şimdi yeni kelimelerle uzuyorsa:
        if self._last_norm and self._is_typewriter_extension(self._last_norm, norm):
            self._pending_text = text
            self._pending_norm = norm
            self._last_change_ts = now
            self._is_typing = True
            self._typewriter_updates += 1
            self._stable_count = 0
            return Decision(Action.IGNORE)

        # Bekleyen bir aday yoksa yeni adayı başlat
        self._pending_text = text
        self._pending_norm = norm
        self._last_change_ts = now
        self._is_typing = False
        self._typewriter_updates = 0
        self._stable_count = 0
        return Decision(Action.IGNORE)
