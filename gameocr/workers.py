"""Arka plan worker thread'leri.

CaptureWorker   -> OcrWorker      -> FilterWorker    -> TranslatorWorker
[frame_q: max 1]   [text_q: max 4]   [translate_q: 8]   [cache + ui_q]
"""
from __future__ import annotations

import logging
import queue
import re
import sys
import threading
import time

from rapidfuzz import fuzz

from .cache_store import CacheStore
from .capture.base import CaptureBackend, OverlayHandle, roi_to_screen, session_type
from .config import Config, PreprocessConfig, save_config
from .messages import (
    Control,
    ControlKind,
    Frame,
    OcrResult,
    TextStyleMeta,
    TranslateJob,
    UiKind,
    UiMessage,
)
from .ocr_engine import BaseOcrEngine, OcrEngine
from .preprocess import ChangeGate, preprocess
from .text_filter import Action, TextFilter, normalize
from .translator import Translator, TranslatorError

log = logging.getLogger(__name__)


def _put_drop_oldest(q: queue.Queue, item: object) -> None:
    """Kuyruk doluysa en eski öğeyi atıp yenisini ekler."""
    while True:
        try:
            q.put_nowait(item)
            return
        except queue.Full:
            try:
                q.get_nowait()
            except queue.Empty:
                pass


def map_word_colors_to_translation(
    source_text: str,
    translated_text: str,
    word_colors: list[tuple[str, str]],
    src_lang: str,
    tgt_lang: str,
    translator: Translator | None = None,
) -> list[tuple[str, str]]:
    """Kaynak metindeki renkli vurgu kelimelerini (`word_colors`), çevrilmiş metindeki
    karşılık gelen kelime/ifadelere eşleştirir.
    """
    if not word_colors or not translated_text.strip():
        return []

    trans_words = translated_text.split()
    if not trans_words:
        return []

    src_words = source_text.split()
    mapped: list[tuple[str, str]] = []

    for src_phrase, hex_color in word_colors:
        phrase_clean = src_phrase.strip()
        if not phrase_clean:
            continue

        cand_translation = ""
        if translator is not None:
            try:
                # Önce hızlı lokal modelle (kota harcamadan ve gecikmesiz) ifadeyi çevir
                if translator.local_manager.is_installed(src_lang, tgt_lang):
                    cand_translation = translator.local_manager.translate(phrase_clean, src_lang, tgt_lang)
                else:
                    cand_translation = translator.translate(phrase_clean, src_lang, tgt_lang)
            except Exception:
                cand_translation = ""

        cand_clean = re.sub(r"^[^\w']+|[^\w']+$", "", cand_translation.strip(), flags=re.UNICODE)
        matched_span = ""

        if cand_clean:
            # 1. Doğrudan alt-dize (case-insensitive) kontrolü
            m = re.search(re.escape(cand_clean), translated_text, flags=re.IGNORECASE)
            if m:
                matched_span = m.group(0)
            else:
                # 2. Türkçe çekim eklerini (örn. "böyle şeyler" -> "böyle şeyleri") yakalamak için
                # çevrilen cümledeki ardışık kelime pencereleriyle (n-gram) bulanık eşleşme
                cand_tokens = cand_clean.lower().split()
                win_len = max(1, len(cand_tokens))
                best_score = 0.0
                best_ngram = ""
                for w_size in {win_len, max(1, win_len - 1), min(len(trans_words), win_len + 1)}:
                    for i in range(max(1, len(trans_words) - w_size + 1)):
                        ngram_raw = " ".join(trans_words[i : i + w_size])
                        ngram_clean = re.sub(r"[^\w\s']", "", ngram_raw.lower(), flags=re.UNICODE).strip()
                        if not ngram_clean:
                            continue
                        score = float(fuzz.ratio(cand_clean.lower(), ngram_clean))
                        if ngram_clean.startswith(cand_clean.lower()[: max(3, len(cand_clean) - 2)]):
                            score = max(score, 88.0)
                        if score > best_score:
                            best_score = score
                            best_ngram = re.sub(r"^[^\w']+|[^\w']+$", "", ngram_raw, flags=re.UNICODE)
                if best_score >= 68.0 and best_ngram:
                    matched_span = best_ngram

        # 3. Eğer sözlüksel eşleşme bulunamadıysa kaynak cümledeki oransal kelime konumunu kullan
        if not matched_span and src_words:
            src_tokens = phrase_clean.lower().split()
            start_idx = 0
            for idx, sw in enumerate(src_words):
                sw_clean = re.sub(r"[^\w']", "", sw.lower(), flags=re.UNICODE)
                if sw_clean == re.sub(r"[^\w']", "", src_tokens[0], flags=re.UNICODE):
                    start_idx = idx
                    break
            rel_pos = start_idx / max(1, len(src_words))
            t_idx = min(len(trans_words) - 1, max(0, int(round(rel_pos * len(trans_words)))))
            t_len = max(1, min(len(trans_words) - t_idx, len(src_tokens)))
            fallback_raw = " ".join(trans_words[t_idx : t_idx + t_len])
            matched_span = re.sub(r"^[^\w']+|[^\w']+$", "", fallback_raw, flags=re.UNICODE)

        if matched_span:
            mapped.append((matched_span, hex_color))

    return mapped


# --------------------------------------------------------------------------- #
# 1. CaptureWorker
# --------------------------------------------------------------------------- #
class CaptureWorker(threading.Thread):
    def __init__(
        self,
        backend: CaptureBackend,
        cfg: Config,
        frame_q: queue.Queue[Frame],
        ui_q: queue.Queue[UiMessage],
        control_q: queue.Queue[Control],
        stop_event: threading.Event,
    ) -> None:
        super().__init__(name="CaptureWorker", daemon=True)
        self.backend = backend
        self.cfg = cfg
        self.frame_q = frame_q
        self.ui_q = ui_q
        self.control_q = control_q
        self.stop_event = stop_event
        self.is_paused = False

    def run(self) -> None:
        log.info("CaptureWorker başladı (backend=%s)", self.backend.name)
        backend_ready = False
        # İlk açılışta ROI seçici tam ekran açıksa çakışmaması için ROI hazır olana dek bekle
        if (
            self.cfg.capture.has_roi()
            or self.cfg.capture.portal_restore_token
            or self.cfg.capture.x11_window_id
            or getattr(self.cfg.capture, "win32_hwnd", 0)
        ):
            try:
                self.backend.open()
                backend_ready = True
                self.backend.persist_state(self.cfg.capture)
                save_config(self.cfg)
                self.ui_q.put(UiMessage(UiKind.BACKEND, text=self.backend.name))
                geom = self.backend.source_geometry()
                if geom and self.cfg.capture.has_roi():
                    screen_roi = roi_to_screen(geom, self.cfg.capture.roi)
                    self.ui_q.put(UiMessage(UiKind.GEOMETRY, data=screen_roi))
            except Exception as exc:
                log.warning("Başlangıçta yakalama kaynağı açılamadı (kullanıcı seçimi bekleniyor): %s", exc)
                self.ui_q.put(UiMessage(UiKind.STATUS, text=f"Pencere seçimi bekleniyor: {exc}"))

        last_geom_check = 0.0

        while not self.stop_event.is_set():
            # Kontrol mesajlarını tüket
            while True:
                try:
                    ctrl = self.control_q.get_nowait()
                    if ctrl.kind == ControlKind.PAUSE:
                        self.is_paused = True
                    elif ctrl.kind == ControlKind.RESUME:
                        self.is_paused = False
                    elif ctrl.kind == ControlKind.SET_CONFIG:
                        self.cfg = ctrl.payload
                        if not backend_ready and self.cfg.capture.has_roi():
                            try:
                                self.backend.open()
                                backend_ready = True
                                self.backend.persist_state(self.cfg.capture)
                                save_config(self.cfg)
                                self.ui_q.put(UiMessage(UiKind.BACKEND, text=self.backend.name))
                            except Exception as exc:
                                log.warning("Yakalama kaynağı açılamadı: %s", exc)
                    elif ctrl.kind == ControlKind.RESELECT_WINDOW:
                        try:
                            self.backend.close()
                            if ctrl.payload is not None and int(ctrl.payload) > 0:
                                wid = int(ctrl.payload)
                                if sys.platform == "win32":
                                    self.cfg.capture.win32_hwnd = wid
                                    if hasattr(self.backend, "window_id"):
                                        self.backend.window_id = wid
                                    if hasattr(self.backend, "hwnd"):
                                        self.backend.hwnd = wid
                                else:
                                    from .capture.xcomposite_backend import XCompositeBackend
                                    if not isinstance(self.backend, XCompositeBackend):
                                        self.backend = XCompositeBackend(self.cfg.capture)
                                    self.backend.window_id = wid
                            else:
                                if session_type() == "wayland":
                                    from .capture.portal_backend import PortalBackend
                                    if not isinstance(self.backend, PortalBackend):
                                        self.backend = PortalBackend(self.cfg.capture)
                                self.backend.forget_source()
                            self.backend.open()
                            backend_ready = True
                            self.backend.persist_state(self.cfg.capture)
                            save_config(self.cfg)
                            self.ui_q.put(UiMessage(UiKind.BACKEND, text=self.backend.name))
                            geom = self.backend.source_geometry()
                            if geom and self.cfg.capture.has_roi():
                                self.ui_q.put(
                                    UiMessage(UiKind.GEOMETRY, data=roi_to_screen(geom, self.cfg.capture.roi))
                                )
                        except Exception as exc:
                            backend_ready = False
                            log.error("Pencere yeniden seçilirken hata: %s", exc)
                            self.ui_q.put(UiMessage(UiKind.STATUS, text=f"Pencere seçim hatası: {exc}"))
                except queue.Empty:
                    break

            if self.is_paused or not backend_ready or not self.cfg.capture.has_roi():
                time.sleep(0.05)
                continue

            eff_fps = float(self.cfg.capture.fps)
            if getattr(self.cfg.ocr, "low_end_mode", False):
                eff_fps = min(eff_fps, 5.0)
            interval = 1.0 / max(1.0, eff_fps)
            t0 = time.monotonic()

            try:
                # Periyodik geometri güncellemesi (ekran/pencere konumu)
                if t0 - last_geom_check >= 1.0:
                    geom = self.backend.source_geometry()
                    if geom:
                        screen_roi = roi_to_screen(geom, self.cfg.capture.roi)
                        self.ui_q.put(UiMessage(UiKind.GEOMETRY, data=screen_roi))
                    last_geom_check = t0

                # ROI karesini yakala
                img = self.backend.grab_roi(self.cfg.capture.roi)
                if img is not None and img.size > 0:
                    _put_drop_oldest(self.frame_q, Frame(image=img))
            except Exception as exc:
                log.debug("Kare yakalama hatası: %s", exc)

            elapsed = time.monotonic() - t0
            sleep_time = interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

        try:
            self.backend.close()
        except Exception:
            pass
        log.info("CaptureWorker sonlandı")


# --------------------------------------------------------------------------- #
# 2. OcrWorker
# --------------------------------------------------------------------------- #
class OcrWorker(threading.Thread):
    def __init__(
        self,
        ocr_engine: BaseOcrEngine,
        cfg: Config,
        frame_q: queue.Queue[Frame],
        text_q: queue.Queue[OcrResult],
        ui_q: queue.Queue[UiMessage],
        control_q: queue.Queue[Control],
        stop_event: threading.Event,
        ocr_busy: threading.Event | None = None,
    ) -> None:
        super().__init__(name="OcrWorker", daemon=True)
        self.ocr_engine: BaseOcrEngine = ocr_engine
        self.cfg = cfg
        self.frame_q = frame_q
        self.text_q = text_q
        self.ui_q = ui_q
        self.control_q = control_q
        self.stop_event = stop_event
        self.ocr_busy: threading.Event = ocr_busy if ocr_busy is not None else threading.Event()
        self.change_gate = ChangeGate(cfg.preprocess.change_threshold)
        self._last_had_text = False
        self._last_text = ""
        self._last_conf = 0.0
        self._last_style_meta: TextStyleMeta | None = None
        self._empty_burst = 0
        self._static_ticks = 0

    def run(self) -> None:
        eng_tag = getattr(self.ocr_engine, "engine_tag", "ONNX-CPU")
        log.info("OcrWorker başladı (engine=[OCR: %s], lang=%s)", eng_tag, self.ocr_engine.src_lang)

        while not self.stop_event.is_set():
            # Kontrol mesajları
            while True:
                try:
                    ctrl = self.control_q.get_nowait()
                    if ctrl.kind == ControlKind.SET_LANG:
                        src_lang, _ = ctrl.payload
                        self.ui_q.put(UiMessage(UiKind.STATUS, text="Model güncelleniyor…"))
                        self.ocr_engine.reload(src_lang)
                        self.ui_q.put(UiMessage(UiKind.CLEAR))
                    elif ctrl.kind == ControlKind.SET_CONFIG:
                        self.cfg = ctrl.payload
                        self.change_gate.threshold = self.cfg.preprocess.change_threshold
                        self.change_gate.reset()
                        if hasattr(self.ocr_engine, "update_config"):
                            self.ocr_engine.update_config(self.cfg.ocr, self.cfg.general.source_lang)
                except queue.Empty:
                    break

            try:
                frame = self.frame_q.get(timeout=0.2)
                if log.isEnabledFor(logging.DEBUG):
                    ipc_ms = (time.monotonic() - frame.ts) * 1000.0
                    log.debug("[IPC] frame_q -> OcrWorker: %.2f ms (qsize=%d)", ipc_ms, self.frame_q.qsize())
            except queue.Empty:
                continue

            # Ön işleme (Düşük donanım modunda ölçek <= 1.5 ile sınırlandırılır)
            prep_cfg = self.cfg.preprocess
            if getattr(self.cfg.ocr, "low_end_mode", False) and prep_cfg.scale > 1.5:
                prep_cfg = PreprocessConfig(
                    mode=prep_cfg.mode,
                    scale=1.5,
                    denoise=prep_cfg.denoise,
                    change_threshold=prep_cfg.change_threshold,
                )
            processed = preprocess(frame.image, prep_cfg)

            # Değişim kapısı (ChangeGate)
            has_changed = self.change_gate.changed(processed)
            if not has_changed:
                if self._last_had_text and self._static_ticks < 2:
                    self._static_ticks += 1
                    # ChangeGate ekranın değişmediğini (yazımın durduğunu) onayladı
                    _put_drop_oldest(
                        self.text_q,
                        OcrResult(
                            text=self._last_text,
                            confidence=self._last_conf,
                            is_stable=True,
                            style_meta=self._last_style_meta,
                        ),
                    )
                elif self._empty_burst > 0:
                    self._empty_burst -= 1
                    _put_drop_oldest(self.text_q, OcrResult(text="", confidence=0.0))
                continue
            else:
                self._static_ticks = 0

            # OCR çıkarımı
            self.ocr_busy.set()
            style_meta: TextStyleMeta | None = None
            t_infer = time.perf_counter()
            try:
                if hasattr(self.ocr_engine, "recognize_with_meta"):
                    text, conf, style_meta = self.ocr_engine.recognize_with_meta(
                        processed, raw_img=frame.image
                    )
                else:
                    text, conf = self.ocr_engine.recognize(processed)
            finally:
                self.ocr_busy.clear()
            infer_ms = (time.perf_counter() - t_infer) * 1000.0
            eng_tag = getattr(self.ocr_engine, "engine_tag", "ONNX-CPU")

            if text:
                log.info("[OCR: %s] %.2f ms | güven=%.2f | metin='%s'", eng_tag, infer_ms, conf, text)
                self._last_had_text = True
                self._last_text = text
                self._last_conf = conf
                self._last_style_meta = style_meta
                self._empty_burst = 0
            else:
                if self._last_had_text:
                    self._last_had_text = False
                    self._last_text = ""
                    self._last_conf = 0.0
                    self._last_style_meta = None
                    self._empty_burst = 3

            _put_drop_oldest(
                self.text_q,
                OcrResult(text=text, confidence=conf, style_meta=style_meta),
            )

        log.info("OcrWorker sonlandı")


# --------------------------------------------------------------------------- #
# 3. FilterWorker
# --------------------------------------------------------------------------- #
class FilterWorker(threading.Thread):
    def __init__(
        self,
        cfg: Config,
        cache_store: CacheStore,
        text_q: queue.Queue[OcrResult],
        translate_q: queue.Queue[TranslateJob],
        ui_q: queue.Queue[UiMessage],
        control_q: queue.Queue[Control],
        stop_event: threading.Event,
        ocr_busy: threading.Event | None = None,
    ) -> None:
        super().__init__(name="FilterWorker", daemon=True)
        self.cfg = cfg
        self.cache_store = cache_store
        self.text_q = text_q
        self.translate_q = translate_q
        self.ui_q = ui_q
        self.control_q = control_q
        self.stop_event = stop_event
        self.ocr_busy: threading.Event | None = ocr_busy
        self.filter = TextFilter(cfg.filter, cache=cache_store)
        self._latest_style_meta: TextStyleMeta | None = None

    def run(self) -> None:
        log.info("FilterWorker başladı")

        while not self.stop_event.is_set():
            # Kontrol mesajları
            while True:
                try:
                    ctrl = self.control_q.get_nowait()
                    if ctrl.kind == ControlKind.SHOWN_TEXT:
                        self.filter.set_shown(ctrl.payload)
                    elif ctrl.kind == ControlKind.SET_CONFIG:
                        self.cfg = ctrl.payload
                        self.filter.cfg = self.cfg.filter
                        self.filter.reset()
                except queue.Empty:
                    break

            try:
                ocr_res = self.text_q.get(timeout=0.1)
                if log.isEnabledFor(logging.DEBUG):
                    ipc_ms = (time.monotonic() - ocr_res.ts) * 1000.0
                    log.debug("[IPC] text_q -> FilterWorker: %.2f ms (qsize=%d)", ipc_ms, self.text_q.qsize())
                if getattr(ocr_res, "style_meta", None) is not None:
                    self._latest_style_meta = ocr_res.style_meta
                if ocr_res.text:
                    self._latest_raw_text = ocr_res.text
                decision = self.filter.process(
                    ocr_res.text,
                    is_stable=getattr(ocr_res, "is_stable", False),
                )
            except queue.Empty:
                is_busy = self.ocr_busy.is_set() if self.ocr_busy is not None else False
                decision = self.filter.check_pending(is_ocr_busy=is_busy)

            if decision.action == Action.CLEAR:
                self._latest_style_meta = None
                self.ui_q.put(UiMessage(UiKind.CLEAR))

            elif decision.action == Action.SHOW_CACHED:
                log.info("Önbellekten gösteriliyor: '%s'", decision.text)
                self.filter.set_shown(decision.text)
                meta_to_send = self._latest_style_meta
                if meta_to_send is not None and meta_to_send.word_colors:
                    from .local_models import LocalModelManager
                    if not hasattr(self, "_local_mgr"):
                        self._local_mgr = LocalModelManager()
                    mapped_colors = map_word_colors_to_translation(
                        getattr(self, "_latest_raw_text", ""),
                        decision.text,
                        meta_to_send.word_colors,
                        self.cfg.general.source_lang,
                        self.cfg.general.target_lang,
                        translator=None,
                    )
                    if mapped_colors:
                        meta_to_send = TextStyleMeta(
                            bbox_rel=meta_to_send.bbox_rel,
                            line_height_px=meta_to_send.line_height_px,
                            text_color_hex=meta_to_send.text_color_hex,
                            bg_color_hex=meta_to_send.bg_color_hex,
                            word_colors=mapped_colors,
                            raw_boxes=meta_to_send.raw_boxes,
                        )
                self.ui_q.put(
                    UiMessage(UiKind.SHOW, text=decision.text, data=meta_to_send)
                )

            elif decision.action == Action.TRANSLATE:
                job = TranslateJob(
                    source=decision.text,
                    norm_key=decision.norm_key,
                    src_lang=self.cfg.general.source_lang,
                    tgt_lang=self.cfg.general.target_lang,
                    context=getattr(self, "_last_context", ""),
                    style_meta=self._latest_style_meta,
                )
                self._last_context = decision.text
                log.info("Çeviri kuyruğuna iletildi: '%s' (context: '%s')", decision.text, job.context)
                _put_drop_oldest(self.translate_q, job)

        log.info("FilterWorker sonlandı")


# --------------------------------------------------------------------------- #
# 4. TranslatorWorker
# --------------------------------------------------------------------------- #
class TranslatorWorker(threading.Thread):
    def __init__(
        self,
        translator: Translator,
        cfg: Config,
        cache_store: CacheStore,
        translate_q: queue.Queue[TranslateJob],
        ui_q: queue.Queue[UiMessage],
        filter_control_q: queue.Queue[Control],
        control_q: queue.Queue[Control],
        stop_event: threading.Event,
    ) -> None:
        super().__init__(name="TranslatorWorker", daemon=True)
        self.translator = translator
        self.cfg = cfg
        self.cache_store = cache_store
        self.translate_q = translate_q
        self.ui_q = ui_q
        self.filter_control_q = filter_control_q
        self.control_q = control_q
        self.stop_event = stop_event
        self._count = 0

    def _drain_superseded(self, current_job: TranslateJob) -> TranslateJob:
        """Kuyrukta bekleyen daha yeni veya bu metnin daktilo uzantısı olan bir iş varsa ara isteği atlar."""
        job = current_job
        while not self.translate_q.empty():
            try:
                next_job = self.translate_q.get_nowait()
                norm_curr = normalize(job.source)
                norm_next = normalize(next_job.source)
                if (
                    norm_next.startswith(norm_curr)
                    or fuzz.partial_ratio(norm_curr, norm_next) >= 85
                    or len(norm_next) > len(norm_curr)
                ):
                    log.info("Daktilo ara çeviri isteği atlandı: '%s' -> '%s'", job.source, next_job.source)
                    job = next_job
                else:
                    job = next_job
            except queue.Empty:
                break
        return job

    def run(self) -> None:
        log.info("TranslatorWorker başladı")
        self._check_usage()

        while not self.stop_event.is_set():
            while True:
                try:
                    ctrl = self.control_q.get_nowait()
                    if ctrl.kind == ControlKind.SET_CONFIG:
                        self.cfg = ctrl.payload
                        self.translator.update_config(
                            self.cfg.deepl,
                            engine=getattr(self.cfg.general, "translation_engine", "deepl"),
                        )
                        self._check_usage()
                except queue.Empty:
                    break

            try:
                job = self.translate_q.get(timeout=0.2)
                if log.isEnabledFor(logging.DEBUG):
                    ipc_ms = (time.monotonic() - job.ts) * 1000.0
                    log.debug("[IPC] translate_q -> TranslatorWorker: %.2f ms (qsize=%d)", ipc_ms, self.translate_q.qsize())
            except queue.Empty:
                continue

            # Daktilo ara isteği koruması: kuyrukta bu işin devamı/daha günceli varsa eskisini atla
            job = self._drain_superseded(job)

            # Çeviri işlemi
            try:
                translated = self.translator.translate(
                    job.source, job.src_lang, job.tgt_lang, context=job.context
                )
                log.info("DeepL Çevirisi Tamamlandı: '%s' → '%s'", job.source, translated)
            except TranslatorError as exc:
                log.warning("Çeviri hatası: %s", exc)
                if exc.fatal:
                    self.ui_q.put(UiMessage(UiKind.STATUS, text=str(exc)))
                continue
            except Exception as exc:
                log.error("Beklenmeyen çeviri hatası: %s", exc)
                continue

            # Önbelleğe kaydet
            self.cache_store.put(job.src_lang, job.tgt_lang, job.norm_key, job.source, translated)

            # Çok renkli vurgu kelimelerini çevrilen metne eşleştir
            out_meta = job.style_meta
            if out_meta is not None and out_meta.word_colors:
                try:
                    mapped_colors = map_word_colors_to_translation(
                        job.source,
                        translated,
                        out_meta.word_colors,
                        job.src_lang,
                        job.tgt_lang,
                        translator=self.translator,
                    )
                    out_meta = TextStyleMeta(
                        bbox_rel=out_meta.bbox_rel,
                        line_height_px=out_meta.line_height_px,
                        text_color_hex=out_meta.text_color_hex,
                        bg_color_hex=out_meta.bg_color_hex,
                        word_colors=mapped_colors,
                        raw_boxes=out_meta.raw_boxes,
                    )
                except Exception as exc:
                    log.debug("Kelime renkleri çeviriye eşlenemedi: %s", exc)

            # Yankı filtresine bildir ve ekranda göster
            self.filter_control_q.put(Control(ControlKind.SHOWN_TEXT, payload=translated))
            self.ui_q.put(UiMessage(UiKind.SHOW, text=translated, data=out_meta))

            # Periyodik kota kontrolü
            self._count += 1
            if self._count % 25 == 0:
                self._check_usage()

        log.info("TranslatorWorker sonlandı")

    def _check_usage(self) -> None:
        try:
            usage = self.translator.usage()
        except Exception as exc:
            log.warning("DeepL kota kontrolü başarısız: %s", exc)
            return
        if usage:
            count, limit = usage
            self.ui_q.put(UiMessage(UiKind.USAGE, data=usage))
            if count >= limit:
                self.ui_q.put(UiMessage(UiKind.STATUS, text="DeepL aylık kota doldu!"))
