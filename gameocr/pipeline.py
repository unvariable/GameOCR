"""GameOCR Boru Hattı Koordinatörü.

Tüm worker'ları, kuyrukları, yakalama backend'ini, OCR motorunu ve
çeviri istemcisini birbirine bağlar ve yaşam döngüsünü (start/stop/pause)
yönetir.
"""
from __future__ import annotations

import logging
import queue
import sys
import threading
from typing import Any

import numpy as np

from .cache_store import CacheStore
from .capture.base import CaptureBackend, OverlayHandle, create_backend
from .config import Config, save_config
from .messages import Control, ControlKind, Frame, OcrResult, TranslateJob, UiMessage
from .ocr_engine import BaseOcrEngine, OcrEngine, OcrEngineFactory
from .translator import Translator
from .workers import CaptureWorker, FilterWorker, OcrWorker, TranslatorWorker

log = logging.getLogger(__name__)


class Pipeline:
    def __init__(
        self,
        cfg: Config,
        cache_store: CacheStore,
        ui_q: queue.Queue[UiMessage],
        overlay_handle: OverlayHandle | None = None,
    ) -> None:
        self.cfg = cfg
        self.cache_store = cache_store
        self.ui_q = ui_q
        self.overlay_handle = overlay_handle or OverlayHandle()

        self.stop_event = threading.Event()

        # Kuyruklar
        self.frame_q: queue.Queue[Frame] = queue.Queue(maxsize=1)
        self.text_q: queue.Queue[OcrResult] = queue.Queue(maxsize=4)
        self.translate_q: queue.Queue[TranslateJob] = queue.Queue(maxsize=8)

        # Kontrol Kuyrukları
        self.capture_ctrl_q: queue.Queue[Control] = queue.Queue()
        self.ocr_ctrl_q: queue.Queue[Control] = queue.Queue()
        self.filter_ctrl_q: queue.Queue[Control] = queue.Queue()
        self.trans_ctrl_q: queue.Queue[Control] = queue.Queue()

        # Çekirdek Bileşenler
        self.backend: CaptureBackend = create_backend(self.cfg.capture, self.overlay_handle)
        self.ocr_engine: BaseOcrEngine = OcrEngine(self.cfg.ocr, src_lang=self.cfg.general.source_lang)
        self.translator = Translator(
            self.cfg.deepl,
            engine=getattr(self.cfg.general, "translation_engine", "deepl"),
        )

        # Aktif dil çiftini önbelleğe bildir
        self.cache_store.set_lang_pair(self.cfg.general.source_lang, self.cfg.general.target_lang)

        # Senkronizasyon ve Durum Bayrakları
        self.ocr_busy = threading.Event()

        # Worker'lar
        self.capture_worker = CaptureWorker(
            backend=self.backend,
            cfg=self.cfg,
            frame_q=self.frame_q,
            ui_q=self.ui_q,
            control_q=self.capture_ctrl_q,
            stop_event=self.stop_event,
            ocr_ctrl_q=self.ocr_ctrl_q,
            filter_ctrl_q=self.filter_ctrl_q,
        )
        self.ocr_worker = OcrWorker(
            ocr_engine=self.ocr_engine,
            cfg=self.cfg,
            frame_q=self.frame_q,
            text_q=self.text_q,
            ui_q=self.ui_q,
            control_q=self.ocr_ctrl_q,
            stop_event=self.stop_event,
            ocr_busy=self.ocr_busy,
        )
        self.filter_worker = FilterWorker(
            cfg=self.cfg,
            cache_store=self.cache_store,
            text_q=self.text_q,
            translate_q=self.translate_q,
            ui_q=self.ui_q,
            control_q=self.filter_ctrl_q,
            stop_event=self.stop_event,
            ocr_busy=self.ocr_busy,
        )
        self.trans_worker = TranslatorWorker(
            translator=self.translator,
            cfg=self.cfg,
            cache_store=self.cache_store,
            translate_q=self.translate_q,
            ui_q=self.ui_q,
            filter_control_q=self.filter_ctrl_q,
            control_q=self.trans_ctrl_q,
            stop_event=self.stop_event,
        )

        self.workers = [
            self.capture_worker,
            self.ocr_worker,
            self.filter_worker,
            self.trans_worker,
        ]

    def start(self) -> None:
        log.info("Boru hattı başlatılıyor…")
        self.stop_event.clear()
        for worker in self.workers:
            worker.start()

    def pause(self) -> None:
        self.capture_ctrl_q.put(Control(ControlKind.PAUSE))

    def resume(self) -> None:
        self.capture_ctrl_q.put(Control(ControlKind.RESUME))

    def set_roi(self, roi: list[float]) -> None:
        self.cfg.capture.roi = roi
        save_config(self.cfg)
        self.capture_ctrl_q.put(Control(ControlKind.SET_CONFIG, self.cfg))
        log.info("Yeni ROI boru hattına uygulandı: %s", roi)

    def reselect_window(self, window_id: int | None = None) -> None:
        """İzlenen oyun penceresini canlı olarak değiştirir veya Wayland Portal seçimini tetikler."""
        if window_id is not None and window_id > 0:
            if sys.platform == "win32":
                self.cfg.capture.win32_hwnd = int(window_id)
                self.cfg.capture.x11_window_id = 0
            else:
                self.cfg.capture.x11_window_id = int(window_id)
        else:
            self.cfg.capture.portal_restore_token = ""
            self.cfg.capture.x11_window_id = 0
            self.cfg.capture.win32_hwnd = 0
        save_config(self.cfg)
        for b in (self.backend, getattr(self.capture_worker, "backend", None)):
            if b is not None and hasattr(b, "cancel_pending"):
                try:
                    b.cancel_pending()
                except Exception:
                    pass
        self.capture_ctrl_q.put(Control(ControlKind.RESELECT_WINDOW, window_id))
        log.info("Hedef pencere yeniden seçimi tetiklendi (window_id=%s)", window_id)

    def set_languages(self, src: str, tgt: str) -> None:
        self.cfg.general.source_lang = src
        self.cfg.general.target_lang = tgt
        save_config(self.cfg)

        self.cache_store.set_lang_pair(src, tgt)
        self.ocr_ctrl_q.put(Control(ControlKind.SET_LANG, (src, tgt)))
        self.update_config(self.cfg)

    def update_config(self, new_cfg: Config) -> None:
        # SettingsDialog içindeki eski kopyanın canlı ROI ve pencere seçimini ezmesini önle
        new_cfg.capture.roi = list(self.cfg.capture.roi)
        new_cfg.capture.win32_hwnd = int(self.cfg.capture.win32_hwnd or 0)
        new_cfg.capture.x11_window_id = int(self.cfg.capture.x11_window_id or 0)
        new_cfg.capture.portal_restore_token = self.cfg.capture.portal_restore_token
        self.backend.persist_state(new_cfg.capture)
        self.cfg = new_cfg
        save_config(self.cfg)
        self.translator.update_config(
            self.cfg.deepl,
            engine=getattr(self.cfg.general, "translation_engine", "deepl"),
        )

        self.capture_ctrl_q.put(Control(ControlKind.SET_CONFIG, self.cfg))
        self.ocr_ctrl_q.put(Control(ControlKind.SET_CONFIG, self.cfg))
        self.filter_ctrl_q.put(Control(ControlKind.SET_CONFIG, self.cfg))
        self.trans_ctrl_q.put(Control(ControlKind.SET_CONFIG, self.cfg))

    def grab_snapshot(self) -> np.ndarray | None:
        """ROI seçici için anlık tam kare alır."""
        try:
            return self.backend.grab_full()
        except Exception as exc:
            log.warning("Snapshot alınamadı: %s", exc)
            return None

    def stop(self, timeout: float = 2.0) -> None:
        log.info("Boru hattı durduruluyor…")
        self.stop_event.set()
        self.backend.persist_state(self.cfg.capture)
        save_config(self.cfg)

        for worker in self.workers:
            worker.join(timeout=timeout)

        self.backend.close()
        log.info("Boru hattı temizce kapatıldı")
