"""Güvenlik ve gizlilik yardımcıları.

* POSIX dosya/dizin izinlerinin sıkılaştırılması (``0o600`` / ``0o700``).
* İndirme URL'lerinde ``https://`` şema zorunluluğu.
* ZIP arşivlerinde Zip Slip (path traversal), sembolik link ve Zip Bomb koruması.
* Log ve hata mesajlarında API anahtarı / kimlik bilgisi maskelemesi (redaction).
"""
from __future__ import annotations

import os
import re
import stat
import time
import urllib.parse
import zipfile
from pathlib import Path

# DeepL API anahtarları (UUID v4 ve ':fx' ücretsiz sürüm son eki) ile Authorization başlıkları
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}(?::fx)?\b"
    ),
    re.compile(r"(?i)(DeepL-Auth-Key|Authorization)\s*[:=]\s*[^\s,;\"']+"),
)


def harden_private_path(path: Path, is_dir: bool = False) -> None:
    """POSIX sistemlerde özel veri dosya/dizinlerini yalnızca sahip erişimine sınırlar."""
    if os.name != "posix":
        return
    try:
        if path.exists():
            os.chmod(path, 0o700 if is_dir else 0o600)
    except OSError:
        pass


def validate_https_url(url: str) -> str:
    """URL'nin yalnızca güvenli ``https://`` şemasını ve geçerli bir alan adını kullandığını doğrular."""
    parsed = urllib.parse.urlparse((url or "").strip())
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        raise ValueError(f"Güvensiz veya geçersiz indirme URL'si reddedildi: {url!r}")
    return url


def safe_extract_zip(
    zf: zipfile.ZipFile,
    dest_dir: Path,
    *,
    max_total_bytes: int = 1024 * 1024 * 1024,
) -> None:
    """Zip Slip (path traversal), sembolik link ve aşırı boyutlu arşivlere karşı güvenli açma."""
    dest_root = dest_dir.resolve()
    dest_root.mkdir(parents=True, exist_ok=True)
    total_size = 0

    for member in zf.infolist():
        # Sembolik linkleri reddet (POSIX S_IFLNK = 0o120000)
        unix_mode = (member.external_attr >> 16) & 0o170000
        if unix_mode == stat.S_IFLNK:
            raise ValueError(f"Arşiv içinde güvensiz sembolik link reddedildi: {member.filename!r}")

        member_name = member.filename
        if not member_name or member_name.startswith(("/", "\\")) or "\x00" in member_name:
            raise ValueError(f"Arşiv içinde geçersiz dosya yolu reddedildi: {member_name!r}")

        target = (dest_root / member_name).resolve()
        if not target.is_relative_to(dest_root):
            raise ValueError(f"Arşiv içinde dizin dışına taşan yol (Zip Slip) reddedildi: {member_name!r}")

        total_size += max(0, int(member.file_size))
        if total_size > max_total_bytes:
            raise ValueError(f"Arşiv boyutu güvenlik sınırını aşıyor: {total_size} > {max_total_bytes}")

    zf.extractall(dest_root)


def atomic_replace(src: Path, dst: Path, retries: int = 6, delay_s: float = 0.025) -> None:
    """Windows Defender / dosya kilidi altında geçici PermissionError'a dayanıklı atomik dosya değişimi."""
    last_exc: Exception | None = None
    attempts = max(1, int(retries))
    for i in range(attempts):
        try:
            src.replace(dst)
            return
        except PermissionError as exc:
            last_exc = exc
            if i + 1 < attempts:
                time.sleep(delay_s)
    if last_exc is not None:
        raise last_exc


def redact_secrets(text: str) -> str:
    """Metin içindeki API anahtarlarını ve kimlik doğrulama başlıklarını maskeler."""
    if not text:
        return text
    masked = text
    for pat in _SECRET_PATTERNS:
        masked = pat.sub("[REDACTED]", masked)
    return masked
