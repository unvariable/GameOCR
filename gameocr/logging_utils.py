"""Gelişmiş loglama, milisaniye bazlı performans telemetrisi ve aşamalı hata izleme (traceback).

Özellikle dinamik görsel metin hizalama (renk örnekleme, bounding box hesaplama,
koordinat dönüşümü) ve çeviri boru hattında oluşan hataların tam olarak hangi
alt aşamadan kaynaklandığını gösterir ve DEBUG modunda yürütme sürelerini (ms)
kayıt altına alır.
"""
from __future__ import annotations

import contextlib
import functools
import logging
import time
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Callable, Iterator, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


class StageError(RuntimeError):
    """Hatanın boru hattındaki hangi alt aşamada (stage) gerçekleştiğini taşıyan özel istisna."""

    def __init__(self, stage: str, message: str, context: dict[str, Any] | None = None) -> None:
        self.stage = stage
        self.context = context or {}
        ctx_str = ", ".join(f"{k}={v!r}" for k, v in self.context.items())
        full_msg = f"[AŞAMA HATASI: {stage}] {message}"
        if ctx_str:
            full_msg += f" | Bağlam: ({ctx_str})"
        super().__init__(full_msg)


def format_stage_traceback(stage: str, exc: BaseException, **context: Any) -> str:
    """Bir istisnayı aşama adı, bağlam parametreleri ve tam çağrı yığını (traceback) ile biçimlendirir."""
    ctx_str = ", ".join(f"{k}={v!r}" for k, v in context.items())
    header = f"=== HATA İZİ (Aşama: {stage}) ==="
    if ctx_str:
        header += f"\nBağlam: {ctx_str}"
    tb_lines = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    return f"{header}\n{tb_lines.rstrip()}\n================================="


def log_stage_exception(
    logger: logging.Logger,
    stage: str,
    exc: BaseException,
    **context: Any,
) -> str:
    """Aşama hatasını tam traceback ile birlikte loglar ve biçimlendirilmiş metni döndürür."""
    formatted = format_stage_traceback(stage, exc, **context)
    logger.error("Aşama '%s' sırasında hata oluştu: %s\n%s", stage, exc, formatted)
    return formatted


@contextlib.contextmanager
def timed_stage(
    logger: logging.Logger,
    stage: str,
    reraise: bool = True,
    **context: Any,
) -> Iterator[dict[str, Any]]:
    """Kod bloğunun çalışma süresini (ms) ölçer ve hata durumunda aşamalı traceback loglar."""
    t0 = time.perf_counter()
    metrics: dict[str, Any] = dict(context)
    try:
        yield metrics
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        metrics["elapsed_ms"] = round(elapsed_ms, 2)
        log_stage_exception(logger, stage, exc, **metrics)
        if reraise:
            if isinstance(exc, StageError):
                raise
            raise StageError(stage, str(exc), context=metrics) from exc
    else:
        if logger.isEnabledFor(logging.DEBUG):
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            extra = ", ".join(f"{k}={v!r}" for k, v in metrics.items())
            if extra:
                logger.debug("[TIMING] %s: %.2f ms (%s)", stage, elapsed_ms, extra)
            else:
                logger.debug("[TIMING] %s: %.2f ms", stage, elapsed_ms)


def log_timing(stage_name: str | None = None) -> Callable[[F], F]:
    """Fonksiyon yürütme süresini DEBUG seviyesinde milisaniye (ms) cinsinden loglayan dekoratör."""

    def decorator(func: F) -> F:
        label = stage_name or f"{func.__module__}.{func.__qualname__}"
        func_logger = logging.getLogger(func.__module__)

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not func_logger.isEnabledFor(logging.DEBUG):
                return func(*args, **kwargs)
            t0 = time.perf_counter()
            try:
                return func(*args, **kwargs)
            except Exception as exc:
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                log_stage_exception(func_logger, label, exc, elapsed_ms=round(elapsed_ms, 2))
                raise
            finally:
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                func_logger.debug("[TIMING] %s: %.2f ms", label, elapsed_ms)

        return wrapper  # type: ignore[return-value]

    return decorator


def setup_logging(level_name: str = "INFO", log_dir: Path | None = None) -> None:
    """Konsol ve opsiyonel dönen dosya (RotatingFileHandler) loglamasını yapılandırır."""
    level = getattr(logging, (level_name or "INFO").upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)

    fmt = logging.Formatter(
        fmt="%(asctime)s.%(msecs)03d [%(levelname)s] (%(threadName)s) %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    if not root.handlers:
        console = logging.StreamHandler()
        console.setFormatter(fmt)
        root.addHandler(console)
    else:
        for h in root.handlers:
            h.setFormatter(fmt)

    if log_dir is not None:
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / "gameocr.log"
            has_file = any(isinstance(h, RotatingFileHandler) for h in root.handlers)
            if not has_file:
                fh = RotatingFileHandler(
                    log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
                )
                fh.setFormatter(fmt)
                root.addHandler(fh)
        except OSError:
            pass

