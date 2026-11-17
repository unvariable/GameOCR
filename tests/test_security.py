"""Güvenlik ve gizlilik önlemleri için birim testleri."""
from __future__ import annotations

import io
import logging
import os
import stat
import zipfile
from pathlib import Path

import pytest

from gameocr.cache_store import CacheStore
from gameocr.config import Config, save_config
from gameocr.logging_utils import setup_logging
from gameocr.security import (
    harden_private_path,
    redact_secrets,
    safe_extract_zip,
    validate_https_url,
)


def test_validate_https_url_rejects_insecure_schemes() -> None:
    assert validate_https_url("https://example.com/model.onnx") == "https://example.com/model.onnx"
    for bad in ("http://example.com/a", "file:///etc/passwd", "ftp://host/a", "", "not-a-url"):
        with pytest.raises(ValueError):
            validate_https_url(bad)


def test_safe_extract_zip_blocks_zip_slip_symlink_and_size_limit(tmp_path: Path) -> None:
    # 1. Path traversal (Zip Slip)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../../outside.txt", "evil")
    buf.seek(0)
    with zipfile.ZipFile(buf, "r") as zf:
        with pytest.raises(ValueError, match="Zip Slip"):
            safe_extract_zip(zf, tmp_path / "dest1")
    assert not (tmp_path / "outside.txt").exists()

    # 2. Sembolik link reddi
    buf2 = io.BytesIO()
    with zipfile.ZipFile(buf2, "w") as zf:
        info = zipfile.ZipInfo("link.txt")
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        zf.writestr(info, "/etc/passwd")
    buf2.seek(0)
    with zipfile.ZipFile(buf2, "r") as zf:
        with pytest.raises(ValueError, match="sembolik link"):
            safe_extract_zip(zf, tmp_path / "dest2")

    # 3. Boyut sınırı (Zip Bomb koruması)
    buf3 = io.BytesIO()
    with zipfile.ZipFile(buf3, "w") as zf:
        zf.writestr("big.bin", b"A" * 1024)
    buf3.seek(0)
    with zipfile.ZipFile(buf3, "r") as zf:
        with pytest.raises(ValueError, match="boyut"):
            safe_extract_zip(zf, tmp_path / "dest3", max_total_bytes=512)

    # 4. Geçerli arşiv başarıyla açılır
    buf4 = io.BytesIO()
    with zipfile.ZipFile(buf4, "w") as zf:
        zf.writestr("model/weights.bin", b"ok")
    buf4.seek(0)
    dest4 = tmp_path / "dest4"
    with zipfile.ZipFile(buf4, "r") as zf:
        safe_extract_zip(zf, dest4)
    assert (dest4 / "model" / "weights.bin").read_bytes() == b"ok"


def test_secret_redaction_and_logging_filter(tmp_path: Path) -> None:
    fake_key = "12345678-1234-4321-abcd-1234567890ab:fx"
    assert fake_key not in redact_secrets(f"DeepL error with key {fake_key}")
    assert "[REDACTED]" in redact_secrets("Authorization: DeepL-Auth-Key secret123")

    root_logger = logging.getLogger()
    old_handlers = list(root_logger.handlers)
    for h in old_handlers:
        root_logger.removeHandler(h)
    try:
        log_dir = tmp_path / "logs"
        setup_logging("INFO", log_dir=log_dir)
        logger = logging.getLogger("gameocr.test_security")
        logger.warning("API key failed: %s", fake_key)

        log_file = log_dir / "gameocr.log"
        content = log_file.read_text(encoding="utf-8")
        assert fake_key not in content
        assert "[REDACTED]" in content
        assert stat.S_IMODE(log_dir.stat().st_mode) == 0o700
        assert stat.S_IMODE(log_file.stat().st_mode) == 0o600
    finally:
        for h in list(root_logger.handlers):
            root_logger.removeHandler(h)
            if h not in old_handlers:
                h.close()
        for h in old_handlers:
            root_logger.addHandler(h)


def test_private_file_permissions_on_posix(tmp_path: Path) -> None:
    if os.name != "posix":
        pytest.skip("POSIX dosya izinleri testi")

    cfg_dir = tmp_path / "cfg"
    cfg_path = cfg_dir / "config.toml"
    cfg = Config()
    cfg.deepl.auth_key = "12345678-1234-4321-abcd-1234567890ab:fx"
    save_config(cfg, cfg_path)

    assert stat.S_IMODE(cfg_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE(cfg_path.stat().st_mode) == 0o600

    db_dir = tmp_path / "data"
    db_path = db_dir / "cache.db"
    store = CacheStore(db_path)
    store.close()

    assert stat.S_IMODE(db_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE(db_path.stat().st_mode) == 0o600

    # harden_private_path var olmayan dosya için hata fırlatmamalı
    harden_private_path(tmp_path / "nonexistent.txt")


def test_stanza_constraint_and_lockfile_clean() -> None:
    root = Path(__file__).resolve().parent.parent
    pyproject_text = (root / "pyproject.toml").read_text(encoding="utf-8")
    assert "stanza>=1.12.2" in pyproject_text

    lock_text = (root / "uv.lock").read_text(encoding="utf-8")
    assert 'constraints = [{ name = "stanza", specifier = ">=1.12.2" }]' in lock_text
    assert '[[package]]\nname = "stanza"' not in lock_text
    assert '[[package]]\nname = "argostranslate"' not in lock_text
