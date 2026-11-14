"""Çift Motorlu Çeviri İstemcisi (DeepL Bulut API & Lokal Çevrimdışı CTranslate2/Argos).

Desteklenen modlar (`translation_engine`):
  * `deepl`: DeepL Free/Pro API (anahtardan uç nokta otomatik seçilir).
  * `local`: Tamamen çevrimdışı çalışan CTranslate2 / Argos lokal dil modeli.
  * `auto_fallback`: Önce DeepL denenir; anahtar yoksa, kota dolmuşsa veya ağ hatası
    alınırsa otomatik olarak lokal çevrimdışı motora düşer.
"""
from __future__ import annotations

import logging
import threading
import time

import deepl

from .config import DeepLConfig
from .local_models import LocalModelError, LocalModelManager, LocalModelNotInstalledError
from .logging_utils import log_stage_exception

log = logging.getLogger(__name__)


class TranslatorError(Exception):
    def __init__(self, message: str, fatal: bool = False) -> None:
        super().__init__(message)
        self.fatal = fatal


class Translator:
    def __init__(
        self,
        cfg: DeepLConfig,
        max_attempts: int = 4,
        engine: str = "deepl",
        local_manager: LocalModelManager | None = None,
    ) -> None:
        self.cfg = cfg
        self.max_attempts = max_attempts
        self.engine = (engine or "deepl").strip().lower()
        self.local_manager = local_manager or LocalModelManager()
        self._client: deepl.Translator | None = None
        self._key = ""
        self._lock = threading.Lock()
        self.last_latency_ms: float = 0.0

    def _get_client(self) -> deepl.Translator:
        key = self.cfg.resolved_key()
        if not key:
            raise TranslatorError("DeepL API anahtarı yok (Ayarlar → DeepL)", fatal=True)
        with self._lock:
            if self._client is None or key != self._key:
                self._client = deepl.Translator(key, send_platform_info=False)
                self._key = key
                log.info("DeepL istemcisi hazır (%s)", "Free" if key.endswith(":fx") else "Pro")
            return self._client

    def update_config(self, cfg: DeepLConfig, engine: str | None = None) -> None:
        self.cfg = cfg
        if engine is not None:
            new_engine = engine.strip().lower()
            if new_engine != self.engine:
                log.info("Çeviri motoru değiştirildi: %s -> %s", self.engine, new_engine)
                if new_engine == "deepl":
                    self.local_manager.unload_model()
                self.engine = new_engine

    def translate(self, text: str, src: str, tgt: str, context: str = "") -> str:
        t0 = time.perf_counter()
        try:
            if self.engine == "local":
                res = self._translate_local(text, src, tgt)
                self.last_latency_ms = (time.perf_counter() - t0) * 1000.0
                log.debug(
                    "[TRANSLATE] engine=local | %.2f ms | %s->%s | '%s' -> '%s'",
                    self.last_latency_ms,
                    src,
                    tgt,
                    text,
                    res,
                )
                return res

            if self.engine == "auto_fallback":
                try:
                    res = self._translate_deepl(text, src, tgt, context=context)
                    self.last_latency_ms = (time.perf_counter() - t0) * 1000.0
                    log.debug("[TRANSLATE] engine=deepl(auto) | %.2f ms", self.last_latency_ms)
                    return res
                except TranslatorError as deepl_exc:
                    log.warning("DeepL kullanılamadı (%s), lokal çeviri motoruna düşülüyor…", deepl_exc)
                    res = self._translate_local(text, src, tgt)
                    self.last_latency_ms = (time.perf_counter() - t0) * 1000.0
                    log.debug("[TRANSLATE] engine=local(fallback) | %.2f ms", self.last_latency_ms)
                    return res

            res = self._translate_deepl(text, src, tgt, context=context)
            self.last_latency_ms = (time.perf_counter() - t0) * 1000.0
            log.debug(
                "[TRANSLATE] engine=deepl | %.2f ms | %s->%s | chars=%d",
                self.last_latency_ms,
                src,
                tgt,
                len(text),
            )
            return res
        except TranslatorError:
            raise
        except Exception as exc:
            log_stage_exception(log, f"translate_{self.engine}", exc, src=src, tgt=tgt)
            raise TranslatorError(f"Çeviri hatası ({self.engine}): {exc}") from exc

    def _translate_local(self, text: str, src: str, tgt: str) -> str:
        try:
            return self.local_manager.translate(text, src, tgt)
        except LocalModelNotInstalledError as exc:
            raise TranslatorError(str(exc), fatal=True) from exc
        except LocalModelError as exc:
            raise TranslatorError(f"Lokal çeviri hatası: {exc}", fatal=False) from exc

    def _translate_deepl(self, text: str, src: str, tgt: str, context: str = "") -> str:
        client = self._get_client()
        kwargs: dict[str, object] = {
            "split_sentences": "nonewlines",
        }
        # Formality yalnızca desteklenen dillerde gönderilir (TR desteklemez)
        if self.cfg.formality != "default":
            tgt_norm = tgt.upper().replace("_", "-")
            if any(tgt_norm.startswith(f) for f in ("DE", "ES", "FR", "IT", "JA", "NL", "PL", "PT", "RU")):
                kwargs["formality"] = self.cfg.formality
        if context and context.strip():
            kwargs["context"] = context.strip()
        delay = 0.25
        for attempt in range(1, self.max_attempts + 1):
            try:
                result = client.translate_text(text, source_lang=src, target_lang=tgt, **kwargs)
                return result.text  # type: ignore[union-attr]
            except deepl.AuthorizationException as exc:
                raise TranslatorError("DeepL anahtarı geçersiz", fatal=True) from exc
            except deepl.QuotaExceededException as exc:
                raise TranslatorError("DeepL aylık kotası doldu", fatal=True) from exc
            except (deepl.TooManyRequestsException, deepl.ConnectionException) as exc:
                if attempt == self.max_attempts:
                    raise TranslatorError(f"DeepL'e ulaşılamadı: {exc}") from exc
                log.warning("DeepL geçici hata (%s), %.1f sn sonra tekrar", exc, delay)
                time.sleep(delay)
                delay *= 2
            except deepl.DeepLException as exc:
                raise TranslatorError(f"DeepL hatası: {exc}") from exc
        raise TranslatorError("DeepL: bilinmeyen hata")

    def usage(self) -> tuple[int, int] | None:
        """(kullanılan, limit) karakter; lokal moddaysa veya alınamazsa None."""
        if self.engine == "local":
            return None
        try:
            u = self._get_client().get_usage()
        except (TranslatorError, deepl.DeepLException) as exc:
            log.debug("Kullanım bilgisi alınamadı: %s", exc)
            return None
        if u.character is None or not u.character.valid:
            return None
        return int(u.character.count), int(u.character.limit or self.cfg.free_char_limit)
