"""Ayarların yüklenmesi/kaydedilmesi.

Kullanıcı ayarları XDG standardına göre ``~/.config/gameocr/config.toml``
dosyasında tutulur. Dosya yoksa paketle gelen ``config.default.toml``
kopyalanır. Eksik anahtarlar dataclass varsayılanlarıyla tamamlanır,
böylece eski bir config dosyası yeni sürümde de çalışır.
"""
from __future__ import annotations

import copy
import logging
import os
import shutil
import sys
import threading
import tomllib
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any

import tomli_w
from dotenv import load_dotenv

log = logging.getLogger(__name__)

_MEIPASS_DIR = getattr(sys, "_MEIPASS", None)
PROJECT_ROOT = Path(_MEIPASS_DIR) if _MEIPASS_DIR else Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_FILE = PROJECT_ROOT / "config.default.toml"

if sys.platform == "win32":
    CONFIG_DIR = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "GameOCR"
    DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "GameOCR"
else:
    CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "gameocr"
    DATA_DIR = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "gameocr"

CONFIG_FILE = CONFIG_DIR / "config.toml"
CACHE_DB_FILE = DATA_DIR / "cache.sqlite"
MODELS_DIR = DATA_DIR / "models"
LOGS_DIR = DATA_DIR / "logs"


# --------------------------------------------------------------------------- #
# Bölümler
# --------------------------------------------------------------------------- #
@dataclass
class GeneralConfig:
    source_lang: str = "EN"
    target_lang: str = "TR"
    ui_language: str = "tr"               # tr | en
    log_level: str = "INFO"
    translation_engine: str = "auto_fallback"  # auto_fallback | deepl | local


@dataclass
class CaptureConfig:
    backend: str = "auto"                 # auto | portal | xcomposite | mss | win32
    fps: float = 8.0
    # ROI, yakalanan kaynağa (pencere/ekran) göre 0..1 aralığında oransal: x, y, w, h
    roi: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0])
    portal_restore_token: str = ""        # Wayland: KDE pencere seçimini hatırlar
    x11_window_id: int = 0                # X11: seçilen oyun penceresi
    win32_hwnd: int = 0                   # Windows: seçilen oyun penceresi HWND
    mss_monitor: int = 1                  # mss yedeği: 1 = birincil ekran

    def has_roi(self) -> bool:
        return len(self.roi) == 4 and self.roi[2] > 0.005 and self.roi[3] > 0.005


@dataclass
class PreprocessConfig:
    mode: str = "none"                    # none (en net/hızlı) | otsu | adaptive
    scale: float = 2.0
    denoise: bool = False                 # modern derin öğrenme modellerinde anti-aliasing'i korur
    change_threshold: float = 0.4         # % ortalama piksel farkı; altındaysa OCR atlanır


@dataclass
class OcrConfig:
    engine: str = "auto"                  # auto | rapidocr (ONNX-CPU Lite) | paddle (NVIDIA/CUDA)
    use_gpu: bool = True
    device: str = "auto"                  # auto | gpu | cpu
    low_end_mode: bool = False            # Düşük donanımlı (low-end) sistemler için hafifletilmiş mod
    min_confidence: float = 0.6
    det_limit_side_len: int = 960
    det_limit_type: str = "max"           # max | min — 'max' geniş altyazı ve ekran alanlarında bellek patlamasını önler
    cpu_threads: int = 4                  # ONNX Runtime / CPU çıkarım iş parçacığı sayısı
    enable_tensorrt: bool = False         # NVIDIA CUDA sürümünde opsiyonel TensorRT hızlandırması
    installed_ocr_packs: list[str] = field(default_factory=lambda: ["EN", "LATIN"])

    def resolved_device(self) -> str:
        if os.environ.get("GAMEOCR_FORCE_CPU", "").strip().lower() in ("1", "true", "yes"):
            return "cpu"
        env_eng = os.environ.get("GAMEOCR_OCR_ENGINE", "").strip().lower()
        if env_eng in ("rapidocr", "onnx", "lite", "cpu"):
            return "cpu"
        cfg_eng = (self.engine or "auto").strip().lower()
        if cfg_eng in ("rapidocr", "onnx", "lite"):
            return "cpu"
        dev = (self.device or "auto").strip().lower()
        if dev in ("cpu", "gpu"):
            return dev
        if not self.use_gpu or self.low_end_mode:
            return "cpu"
        return "auto"

    def resolved_engine(self) -> str:
        """Fabrika (Factory) için hedef OCR motor tipini ('rapidocr' | 'paddle' | 'auto') belirler."""
        env_eng = os.environ.get("GAMEOCR_OCR_ENGINE", "").strip().lower()
        if env_eng in ("rapidocr", "onnx", "lite", "cpu"):
            return "rapidocr"
        if env_eng in ("paddle", "cuda", "nvidia", "gpu"):
            return "paddle"
        cfg_eng = (self.engine or "auto").strip().lower()
        if cfg_eng in ("rapidocr", "onnx", "lite", "cpu"):
            return "rapidocr"
        if cfg_eng in ("paddle", "cuda", "nvidia", "gpu"):
            return "paddle"
        return "auto"


@dataclass
class FilterConfig:
    similarity_threshold: int = 90        # RapidFuzz 0..100
    min_chars: int = 2
    stable_frames: int = 1                # ChangeGate ile uyumlu anında çeviri
    clear_after_empty_frames: int = 5     # Titremeyi önleyen ve diyalog bittiğinde söndüren boş kare eşiği
    settle_time: float = 0.35             # Daktilo efekti durulma bekleme süresi (sn) - hızlı tepki


@dataclass
class CacheConfig:
    max_entries: int = 5000


@dataclass
class DeepLConfig:
    auth_key: str = ""                    # boşsa DEEPL_AUTH_KEY ortam değişkeni kullanılır
    formality: str = "default"            # default | more | less | prefer_more | prefer_less
    free_char_limit: int = 500_000

    def resolved_key(self) -> str:
        return (self.auth_key or os.environ.get("DEEPL_AUTH_KEY", "")).strip()


@dataclass
class LocalTranslatorConfig:
    device: str = "auto"                  # auto | cpu | cuda
    compute_type: str = "int8"            # int8 | float16 | default
    installed_packs: list[str] = field(default_factory=lambda: ["EN-TR"])


@dataclass
class OverlayConfig:
    opacity: float = 0.72
    blur: bool = True
    blur_strength: int = 5                # 1..15 buzlu cam yoğunluğu
    text_shadow: bool = True              # Yazı arkasına okunabilirlik gölgesi
    font_family: str = "Inter"
    font_min: int = 12
    font_max: int = 30
    text_color: str = "#F5F5F7"
    panel_color: str = "#0F0F14"
    corner_radius: int = 14
    exact_alignment: bool = True          # Tam Hizalama: Orijinal X/Y koordinatı, boyut ve renk
    match_font_size: bool = True          # OCR bounding box yüksekliğinden font boyutu
    match_text_color: bool = True         # Orijinal metin rengini örnekle


@dataclass
class HotkeysConfig:
    enabled: bool = True
    pause: str = "ctrl+alt+p"             # Duraklat / Devam Et
    select_roi: str = "ctrl+alt+s"        # Altyazı Alanı Seç
    toggle_overlay: str = "ctrl+alt+o"    # Overlay Göster / Gizle
    history: str = "ctrl+alt+h"           # Çeviri Geçmişi


@dataclass
class Config:
    general: GeneralConfig = field(default_factory=GeneralConfig)
    capture: CaptureConfig = field(default_factory=CaptureConfig)
    preprocess: PreprocessConfig = field(default_factory=PreprocessConfig)
    ocr: OcrConfig = field(default_factory=OcrConfig)
    filter: FilterConfig = field(default_factory=FilterConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    deepl: DeepLConfig = field(default_factory=DeepLConfig)
    local_translator: LocalTranslatorConfig = field(default_factory=LocalTranslatorConfig)
    overlay: OverlayConfig = field(default_factory=OverlayConfig)
    hotkeys: HotkeysConfig = field(default_factory=HotkeysConfig)

    def copy(self) -> "Config":
        return copy.deepcopy(self)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------- #
# Yükleme / kaydetme
# --------------------------------------------------------------------------- #
def _merge(dc_obj: Any, data: dict[str, Any]) -> Any:
    """TOML sözlüğünü dataclass'a uygular; bilinmeyen anahtarlar yok sayılır,
    tip uyuşmazlığında varsayılan korunur."""
    for f in fields(dc_obj):
        if f.name not in data:
            continue
        current = getattr(dc_obj, f.name)
        value = data[f.name]
        if is_dataclass(current) and isinstance(value, dict):
            _merge(current, value)
        elif isinstance(current, bool):
            if isinstance(value, bool):
                setattr(dc_obj, f.name, value)
        elif isinstance(current, float) and isinstance(value, (int, float)):
            setattr(dc_obj, f.name, float(value))
        elif isinstance(current, int) and isinstance(value, int) and not isinstance(value, bool):
            setattr(dc_obj, f.name, value)
        elif isinstance(current, str) and isinstance(value, str):
            setattr(dc_obj, f.name, value)
        elif isinstance(current, list) and isinstance(value, list):
            setattr(dc_obj, f.name, list(value))
        else:
            log.warning("Config: '%s' için geçersiz değer (%r), varsayılan kullanılıyor", f.name, value)
    return dc_obj


_save_lock = threading.Lock()


def load_config(path: Path = CONFIG_FILE) -> Config:
    load_dotenv(PROJECT_ROOT / ".env")
    load_dotenv(CONFIG_DIR / ".env")
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        if DEFAULT_CONFIG_FILE.exists():
            shutil.copy(DEFAULT_CONFIG_FILE, path)
            log.info("Varsayılan ayarlar kopyalandı: %s", path)
        else:
            save_config(Config(), path)
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        log.error("Config okunamadı (%s), varsayılanlar kullanılıyor", exc)
        data = {}
    cfg = _merge(Config(), data)
    # Eski varsayılan config.toml dosyalarındaki (mode='otsu', denoise=True) kombinasyonu
    # derin öğrenme OCR motorlarında harfleri sildiği için otomatik olarak 'none' moduna yükseltilir:
    if path == CONFIG_FILE and cfg.preprocess.mode == "otsu" and cfg.preprocess.denoise is True:
        cfg.preprocess.mode = "none"
        cfg.preprocess.denoise = False
        try:
            save_config(cfg, path)
        except Exception:
            pass
    return cfg


def save_config(cfg: Config, path: Path = CONFIG_FILE) -> None:
    with _save_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        with tmp.open("wb") as fh:
            tomli_w.dump(cfg.to_dict(), fh)
        tmp.replace(path)  # atomik yazım: yarım dosya kalmaz
    log.debug("Config kaydedildi: %s", path)
