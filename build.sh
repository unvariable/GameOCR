#!/usr/bin/env bash
# =============================================================================
# GameOCR — Akıllı ve İnteraktif Derleme Scripti (build.sh)
#
# Uygulamayı Python veya harici kütüphane gerektirmeden başka bilgisayarlarda
# çift tıklamayla çalışacak TAM BAĞIMSIZ (self-contained) çift sürüm Linux
# .AppImage paketine:
#   1) Varsayılan Ana Sürüm (Lite / ONNX-CPU): GameOCR-Universal-x86_64.AppImage
#      (rapidocr-onnxruntime + CPUExecutionProvider, CUDA/Paddle ağırlıklarından arındırılmış)
#   2) Opsiyonel Özel GPU Sürümü (--gpu nvidia): GameOCR_nvidia-x86_64.AppImage
#      (CUDA 12.6 + cuDNN + PaddleOCR GPU + TensorRT desteği gömülü)
# veya otomatik Python 3.12 kuruculu Windows 10/11 paketine dönüştürür.
# =============================================================================
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

# Renk tanımları
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# Varsayılan değişkenler (CLI argümanları ile de geçilebilir)
PLATFORM_CHOICE=""
DE_CHOICE=""
DISPLAY_CHOICE=""
GPU_CHOICE=""
COMPILER_CHOICE=""
BUNDLE_MODE="full"   # full (başka cihazlarda çalışan 2.3GB/600MB tam paket) | fast (yerel 233MB hızlı paket)
DRY_RUN=0

usage() {
    cat <<EOF
Kullanım: ./build.sh [SEÇENEKLER]

Seçenekler:
  --platform <linux|windows>             Hedef işletim sistemi (varsayılan: linux)
  --de <kde|gnome|xfce|other|windows>    Masaüstü ortamı veya Windows 10/11
  --display <wayland|x11|hybrid|win32>   Görüntü sunucusu
  --gpu <nvidia|amd|cpu|dual>            GPU üreticisi / hızlandırma hedefi (dual = her iki AppImage sürümü)
  --compiler <pyinstaller|nuitka>        Derleyici aracı
  --bundle-mode <full|fast>              full = tüm Python+CUDA/CPU kütüphaneleri gömülü (varsayılan), fast = yerel
  --dry-run                              Komutları çalıştırmadan üretilen bayrakları göster
  -h, --help                             Bu yardım mesajını göster
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --platform) PLATFORM_CHOICE="${2:-}"; shift 2 ;;
        --de) DE_CHOICE="${2:-}"; shift 2 ;;
        --display) DISPLAY_CHOICE="${2:-}"; shift 2 ;;
        --gpu) GPU_CHOICE="${2:-}"; shift 2 ;;
        --compiler) COMPILER_CHOICE="${2:-}"; shift 2 ;;
        --bundle-mode) BUNDLE_MODE="${2:-full}"; shift 2 ;;
        --dry-run) DRY_RUN=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo -e "${RED}Bilinmeyen argüman: $1${NC}"; usage; exit 1 ;;
    esac
done

if [[ "${PLATFORM_CHOICE,,}" == "windows" || "${PLATFORM_CHOICE,,}" == "win32" ]]; then
    DE_CHOICE="windows"
    DISPLAY_CHOICE="win32"
fi

echo -e "${CYAN}${BOLD}=================================================================${NC}"
echo -e "${CYAN}${BOLD}   GameOCR — Akıllı Standalone Linux & Windows Derleyici        ${NC}"
echo -e "${CYAN}${BOLD}=================================================================${NC}"

# 1. Masaüstü Ortamı / Platform Seçimi
if [[ -z "$DE_CHOICE" ]]; then
    echo -e "\n${BOLD}1) Hedef Masaüstü Ortamını / Platformu seçin:${NC}"
    echo "   1) KDE Plasma (KWin Blur + GlobalAccel + XWayland optimizasyonu)"
    echo "   2) GNOME (Mutter + AppIndicator + PipeWire Portal optimizasyonu)"
    echo "   3) XFCE / LXQt / MATE (Hafif X11 kompozitör optimizasyonu)"
    echo "   4) Diğer Linux / Evrensel (Tüm masaüstü ortamları)"
    echo "   5) Windows 10/11 (Otomatik Python 3.12 Kurulumu + Win32 DWM Blur + .exe)"
    read -rp "Seçiminiz [1-5, varsayılan: 1]: " de_input
    case "${de_input:-1}" in
        1|kde|KDE) DE_CHOICE="kde"; PLATFORM_CHOICE="linux" ;;
        2|gnome|GNOME) DE_CHOICE="gnome"; PLATFORM_CHOICE="linux" ;;
        3|xfce|XFCE) DE_CHOICE="xfce"; PLATFORM_CHOICE="linux" ;;
        5|windows|WINDOWS|win32|win)
            DE_CHOICE="windows"
            PLATFORM_CHOICE="windows"
            DISPLAY_CHOICE="win32"
            ;;
        *) DE_CHOICE="other"; PLATFORM_CHOICE="linux" ;;
    esac
fi

if [[ "$DE_CHOICE" == "windows" ]]; then
    PLATFORM_CHOICE="windows"
    DISPLAY_CHOICE="win32"
elif [[ -z "$PLATFORM_CHOICE" ]]; then
    PLATFORM_CHOICE="linux"
fi

# 2. Görüntü Sunucusu Seçimi
if [[ -z "$DISPLAY_CHOICE" ]]; then
    echo -e "\n${BOLD}2) Hedef Görüntü Sunucusunu (Display Server) seçin:${NC}"
    echo "   1) Wayland (xdg-desktop-portal + PipeWire + XWayland XCB)"
    echo "   2) X11 (XComposite + Xlib doğrudan pencere yakalama)"
    echo "   3) Hibrit / Her İkisi (Wayland + X11 tam paket)"
    echo "   4) Win32 / DWM (Windows 10/11 yakalama katmanı)"
    read -rp "Seçiminiz [1-4, varsayılan: 3]: " disp_input
    case "${disp_input:-3}" in
        1|wayland) DISPLAY_CHOICE="wayland" ;;
        2|x11) DISPLAY_CHOICE="x11" ;;
        4|win32|windows)
            DISPLAY_CHOICE="win32"
            DE_CHOICE="windows"
            PLATFORM_CHOICE="windows"
            ;;
        *) DISPLAY_CHOICE="hybrid" ;;
    esac
fi

# 3. GPU Üreticisi Seçimi
if [[ -z "$GPU_CHOICE" ]]; then
    echo -e "\n${BOLD}3) OCR Motorunu ve Donanım Hedefini seçin:${NC}"
    echo "   1) NVIDIA GPU Sürümü (--gpu nvidia — CUDA 12.6 + cuDNN — GameOCR_nvidia-x86_64.AppImage)"
    echo "   2) AMD GPU / Universal Lite (ONNX-CPU RapidOCR — GameOCR-Universal-x86_64.AppImage)"
    echo "   3) Ana Sürüm / Universal Lite (Varsayılan — ONNX-CPU RapidOCR — GameOCR-Universal-x86_64.AppImage)"
    echo "   4) Çift Sürüm (Her İkisi Birden: GameOCR-Universal-x86_64.AppImage + GameOCR_nvidia-x86_64.AppImage)"
    read -rp "Seçiminiz [1-4, varsayılan: 3 (Universal ONNX-CPU)]: " gpu_input
    case "${gpu_input:-3}" in
        1|nvidia|NVIDIA) GPU_CHOICE="nvidia" ;;
        2|amd|AMD) GPU_CHOICE="amd" ;;
        3|cpu|CPU|intel|lite|universal) GPU_CHOICE="cpu" ;;
        4|dual|DUAL|both) GPU_CHOICE="dual" ;;
        *) GPU_CHOICE="cpu" ;;
    esac
fi

# 4. Derleyici Seçimi
if [[ -z "$COMPILER_CHOICE" ]]; then
    echo -e "\n${BOLD}4) Paketleme / Derleme Aracını seçin:${NC}"
    echo "   1) Tam Bağımsız Dağıtılabilir AppImage (Başka cihazlarda sıfır kurulumla çalışır: NVIDIA ~2.3 GB / Lite ~600 MB — Önerilen)"
    echo "   2) Nuitka + AppImage (GCC/Clang/MSVC ile yerel C++ makine koduna derleme)"
    echo "   3) Hızlı Yerel AppImage (~233 MB — Yalnızca bu bilgisayarda hızlı test için)"
    read -rp "Seçiminiz [1-3, varsayılan: 1]: " comp_input
    case "${comp_input:-1}" in
        2|nuitka) COMPILER_CHOICE="nuitka"; BUNDLE_MODE="full" ;;
        3|fast|local) COMPILER_CHOICE="pyinstaller"; BUNDLE_MODE="fast" ;;
        *) COMPILER_CHOICE="pyinstaller"; BUNDLE_MODE="full" ;;
    esac
fi

echo -e "\n${GREEN}${BOLD}Seçilen Derleme Profili:${NC}"
echo -e "  • Hedef Platform   : ${YELLOW}${PLATFORM_CHOICE}${NC}"
echo -e "  • Masaüstü Ortamı  : ${YELLOW}${DE_CHOICE}${NC}"
echo -e "  • Görüntü Sunucusu : ${YELLOW}${DISPLAY_CHOICE}${NC}"
echo -e "  • GPU Hedefi       : ${YELLOW}${GPU_CHOICE}${NC}"
echo -e "  • Derleyici        : ${YELLOW}${COMPILER_CHOICE}${NC}"
echo -e "  • Paketleme Modu   : ${YELLOW}${BUNDLE_MODE}${NC}"

# Ortak derleme bayraklarının hesaplanması
HIDDEN_IMPORTS=(
    "gameocr"
    "gameocr.__main__"
    "gameocr.ocr_engine"
    "gameocr.ui.overlay"
    "gameocr.ui.settings_dialog"
    "gameocr.ui.window_picker"
    "gameocr.local_models"
    "rapidocr_onnxruntime"
    "onnxruntime"
    "ctranslate2"
    "sentencepiece"
    "rapidfuzz"
    "deepl"
    "tomli_w"
    "cv2"
    "numpy"
)

EXCLUDES=(
    "tkinter"
    "matplotlib"
    "scipy"
    "notebook"
    "IPython"
)

ENV_FLAGS=()
if [[ "$PLATFORM_CHOICE" == "windows" ]]; then
    ENV_FLAGS+=("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True")
    ENV_FLAGS+=("PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT=False")
    ENV_FLAGS+=("FLAGS_allocator_strategy=auto_growth")
    ENV_FLAGS+=("FLAGS_eager_delete_tensor_gb=0.0")
    ENV_FLAGS+=("FLAGS_fast_eager_deletion_mode=1")
else
    ENV_FLAGS+=("QT_QPA_PLATFORM=xcb")
    ENV_FLAGS+=("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True")
    ENV_FLAGS+=("PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT=False")
    ENV_FLAGS+=("FLAGS_allocator_strategy=auto_growth")
    ENV_FLAGS+=("FLAGS_eager_delete_tensor_gb=0.0")
    ENV_FLAGS+=("FLAGS_fast_eager_deletion_mode=1")
fi

# Masaüstü ortamına özel optimizasyonlar
if [[ "$DE_CHOICE" == "kde" ]]; then
    ENV_FLAGS+=("GAMEOCR_DE_PROFILE=kde")
elif [[ "$DE_CHOICE" == "gnome" ]]; then
    ENV_FLAGS+=("GAMEOCR_DE_PROFILE=gnome")
elif [[ "$DE_CHOICE" == "xfce" ]]; then
    ENV_FLAGS+=("GAMEOCR_DE_PROFILE=xfce")
elif [[ "$DE_CHOICE" == "windows" ]]; then
    ENV_FLAGS+=("GAMEOCR_DE_PROFILE=windows")
fi

# Görüntü sunucusuna özel modül dahil etme / dışlama
if [[ "$DISPLAY_CHOICE" == "win32" ]]; then
    HIDDEN_IMPORTS+=("mss" "gameocr.capture.win32_backend" "gameocr.capture.mss_backend")
    EXCLUDES+=("dbus_fast" "Xlib")
elif [[ "$DISPLAY_CHOICE" == "wayland" ]]; then
    HIDDEN_IMPORTS+=("dbus_fast" "dbus_fast.aio" "Xlib" "gameocr.capture.portal_backend")
elif [[ "$DISPLAY_CHOICE" == "x11" ]]; then
    HIDDEN_IMPORTS+=("Xlib" "Xlib.ext.composite" "mss" "gameocr.capture.xcomposite_backend" "gameocr.capture.mss_backend")
    EXCLUDES+=("dbus_fast")
else
    HIDDEN_IMPORTS+=("dbus_fast" "dbus_fast.aio" "Xlib" "Xlib.ext.composite" "mss" "gameocr.capture.win32_backend")
fi

# GPU üreticisine göre bayraklar
GPU_COMPILE_FLAGS=()
if [[ "$GPU_CHOICE" == "nvidia" ]]; then
    ENV_FLAGS+=("GAMEOCR_OCR_ENGINE=paddle" "FLAGS_fraction_of_gpu_memory_to_use=0.35")
    GPU_COMPILE_FLAGS+=(
        "--collect-binaries" "paddle"
        "--collect-data" "paddleocr"
        "--collect-data" "paddlex"
        "--collect-submodules" "paddlex"
        "--collect-all" "rapidocr_onnxruntime"
        "--collect-all" "ctranslate2"
    )
elif [[ "$GPU_CHOICE" == "dual" ]]; then
    ENV_FLAGS+=("FLAGS_fraction_of_gpu_memory_to_use=0.35")
    GPU_COMPILE_FLAGS+=(
        "--collect-binaries" "paddle"
        "--collect-data" "paddleocr"
        "--collect-data" "paddlex"
        "--collect-submodules" "paddlex"
        "--collect-all" "rapidocr_onnxruntime"
        "--collect-all" "onnxruntime"
        "--collect-all" "ctranslate2"
    )
elif [[ "$GPU_CHOICE" == "amd" ]]; then
    ENV_FLAGS+=("OMP_NUM_THREADS=4" "MKL_NUM_THREADS=4" "GAMEOCR_FORCE_CPU=1" "GAMEOCR_OCR_ENGINE=rapidocr")
    EXCLUDES+=("paddle" "paddleocr" "paddlex")
    GPU_COMPILE_FLAGS+=("--collect-all" "rapidocr_onnxruntime" "--collect-all" "onnxruntime" "--collect-all" "ctranslate2")
else
    ENV_FLAGS+=("CUDA_VISIBLE_DEVICES=-1" "OMP_NUM_THREADS=4" "GAMEOCR_FORCE_CPU=1" "GAMEOCR_OCR_ENGINE=rapidocr")
    EXCLUDES+=("paddle" "paddleocr" "paddlex")
    GPU_COMPILE_FLAGS+=("--collect-all" "rapidocr_onnxruntime" "--collect-all" "onnxruntime" "--collect-all" "ctranslate2")
fi

# Python yorumlayıcısını belirle
PYTHON_BIN="python3"
if [[ -x "$PROJECT_DIR/.venv/bin/python" ]]; then
    PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"
fi

# Derleyici modülü (.venv içinde) eksikse otomatik kur (dry-run değilse)
ensure_compiler_installed() {
    local mod_name="$1"
    local pkg_name="$2"
    if ! "$PYTHON_BIN" -c "import ${mod_name}" >/dev/null 2>&1; then
        echo -e "${YELLOW}⚠ '${pkg_name}' derleyici paketi .venv içinde bulunamadı; otomatik kuruluyor...${NC}"
        if command -v uv >/dev/null 2>&1; then
            uv pip install --python "$PYTHON_BIN" "$pkg_name"
        else
            "$PYTHON_BIN" -m pip install "$pkg_name"
        fi
    fi
}

# =============================================================================
# Eksik Büyük Kütüphaneleri, ONNX/CTranslate2 Modellerini ve CUDA Gereksinimlerini
# Resmi Kaynaklardan Otomatik İndiren Fonksiyon (Zero-Manual-Download Bootstrap)
# =============================================================================
ensure_build_prerequisites() {
    if [[ "$DRY_RUN" -eq 1 ]]; then
        return 0
    fi

    echo -e "\n${CYAN}• Derleme önkoşulları, modeller ve kütüphaneler kontrol ediliyor...${NC}"

    # 1. .venv sanal ortamı yoksa otomatik oluştur ve temel bağımlılıkları kur
    if [[ ! -x "$PROJECT_DIR/.venv/bin/python" ]]; then
        echo -e "${YELLOW}⚠ .venv sanal ortamı bulunamadı; otomatik oluşturuluyor...${NC}"
        if command -v uv >/dev/null 2>&1; then
            uv venv --python 3.12 "$PROJECT_DIR/.venv" || uv venv "$PROJECT_DIR/.venv"
            PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"
            uv pip install --python "$PYTHON_BIN" \
                "rapidocr-onnxruntime>=1.3" "onnxruntime" "numpy" "opencv-python-headless>=4.10" \
                "mss>=9.0" "python-xlib>=0.33" "dbus-fast>=2.24" "rapidfuzz>=3.9" \
                "PyQt6>=6.7" "deepl>=1.18" "ctranslate2>=4.0" "sentencepiece>=0.2" \
                "pyinstaller>=6.0" "tomli-w>=1.0" "python-dotenv>=1.0"
        else
            python3 -m venv "$PROJECT_DIR/.venv"
            PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"
            "$PYTHON_BIN" -m pip install --upgrade pip wheel setuptools
            "$PYTHON_BIN" -m pip install \
                "rapidocr-onnxruntime>=1.3" "onnxruntime" "numpy" "opencv-python-headless>=4.10" \
                "mss>=9.0" "python-xlib>=0.33" "dbus-fast>=2.24" "rapidfuzz>=3.9" \
                "PyQt6>=6.7" "deepl>=1.18" "ctranslate2>=4.0" "sentencepiece>=0.2" \
                "pyinstaller>=6.0" "tomli-w>=1.0" "python-dotenv>=1.0"
        fi
    fi

    # 2. Varsayılan ONNX OCR Tanıma Modelleri (en_rec.onnx, latin_rec.onnx ve sözlükleri)
    local onnx_dir="$PROJECT_DIR/models/onnx"
    mkdir -p "$onnx_dir"
    if [[ ! -f "$onnx_dir/en_rec.onnx" || ! -f "$onnx_dir/en_dict.txt" || ! -f "$onnx_dir/latin_rec.onnx" || ! -f "$onnx_dir/latin_dict.txt" ]]; then
        echo -e "${CYAN}• Eksik varsayılan ONNX OCR modelleri (EN & LATIN) resmi HuggingFace kaynağından indiriliyor...${NC}"
        "$PYTHON_BIN" -c "
from pathlib import Path
from gameocr.ocr_models import OcrModelManager
mgr = OcrModelManager(models_dir=Path('$PROJECT_DIR/models'))
for code in ('EN', 'LATIN'):
    mgr.download_pack(code)
" || {
            curl -fsSL "https://huggingface.co/monkt/paddleocr-onnx/resolve/main/languages/english/rec.onnx" -o "$onnx_dir/en_rec.onnx"
            curl -fsSL "https://huggingface.co/monkt/paddleocr-onnx/resolve/main/languages/english/dict.txt" -o "$onnx_dir/en_dict.txt"
            curl -fsSL "https://huggingface.co/monkt/paddleocr-onnx/resolve/main/languages/latin/rec.onnx" -o "$onnx_dir/latin_rec.onnx"
            curl -fsSL "https://huggingface.co/monkt/paddleocr-onnx/resolve/main/languages/latin/dict.txt" -o "$onnx_dir/latin_dict.txt"
        }
    fi

    # 3. Varsayılan Çevrimdışı Çeviri Modeli (EN-TR CTranslate2 / Argos OpenTech)
    local user_models="${XDG_DATA_HOME:-$HOME/.local/share}/gameocr/models"
    if [[ ! -d "$user_models/en-tr" && ! -d "$PROJECT_DIR/models/en-tr" ]]; then
        echo -e "${CYAN}• Varsayılan çevrimdışı çeviri modeli (EN-TR CTranslate2) resmi Argos CDN'den indiriliyor...${NC}"
        "$PYTHON_BIN" -c "
from gameocr.local_models import LocalModelManager
mgr = LocalModelManager()
mgr.download_pack('EN-TR')
" || true
    fi

    # 4. NVIDIA CUDA 12.6 + cuDNN + PaddleOCR GPU Kütüphaneleri (Yalnızca nvidia veya dual seçildiğinde)
    if [[ "$GPU_CHOICE" == "nvidia" || "$GPU_CHOICE" == "dual" ]]; then
        if ! "$PYTHON_BIN" -c "import paddle, paddleocr" >/dev/null 2>&1; then
            echo -e "${CYAN}• NVIDIA CUDA 12.6 + cuDNN (paddlepaddle-gpu==3.3.1 & paddleocr) resmi indeksinden indiriliyor...${NC}"
            if command -v uv >/dev/null 2>&1; then
                uv pip install --python "$PYTHON_BIN" \
                    --index-url "https://www.paddlepaddle.org.cn/packages/stable/cu126/" \
                    --extra-index-url "https://pypi.org/simple" \
                    "paddlepaddle-gpu==3.3.1" "paddleocr>=3.3"
            else
                "$PYTHON_BIN" -m pip install "paddlepaddle-gpu==3.3.1" -i "https://www.paddlepaddle.org.cn/packages/stable/cu126/"
                "$PYTHON_BIN" -m pip install "paddleocr>=3.3"
            fi
        fi

        # PP-OCRv5 algılama/tanıma ağırlıkları ~/.paddlex/official_models içinde yoksa ısıtarak indir
        if [[ ! -d "$HOME/.paddlex/official_models/PP-OCRv5_server_det" ]]; then
            echo -e "${CYAN}• PaddleOCR PP-OCRv5 algılama ve tanıma modelleri resmi sunucudan önbelleğe indiriliyor...${NC}"
            "$PYTHON_BIN" -c "
from paddleocr import PaddleOCR
PaddleOCR(use_doc_orientation_classify=False, use_doc_unwarping=False, use_textline_orientation=False, lang='en', device='cpu')
" >/dev/null 2>&1 || true
        fi
    fi
}

ensure_build_prerequisites

DIST_DIR="$PROJECT_DIR/dist/gameocr-${DE_CHOICE}-${DISPLAY_CHOICE}-${GPU_CHOICE}"
BUILD_DIR="$PROJECT_DIR/build/${DE_CHOICE}-${DISPLAY_CHOICE}-${GPU_CHOICE}"

# =============================================================================
# Windows 10/11 Paketleme ve Otomatik Python 3.12 Kurucu Üretimi
# =============================================================================
if [[ "$PLATFORM_CHOICE" == "windows" ]]; then
    rm -rf "$DIST_DIR"
    mkdir -p "$DIST_DIR"

    # Kaynak dosyaları, yapılandırmayı ve kurulu lokal çeviri modellerini Windows paketine kopyala
    cp -rf "$PROJECT_DIR/gameocr" "$DIST_DIR/"
    cp -f "$PROJECT_DIR/config.default.toml" "$DIST_DIR/"
    cp -f "$PROJECT_DIR/pyproject.toml" "$DIST_DIR/"

    USER_MODELS_ROOT="${XDG_DATA_HOME:-$HOME/.local/share}/gameocr/models"
    if [[ -d "$USER_MODELS_ROOT" ]]; then
        mkdir -p "$DIST_DIR/models"
        cp -r "$USER_MODELS_ROOT/"* "$DIST_DIR/models/" 2>/dev/null || true
    fi
    if [[ -d "$PROJECT_DIR/models" ]]; then
        mkdir -p "$DIST_DIR/models"
        cp -r "$PROJECT_DIR/models/"* "$DIST_DIR/models/" 2>/dev/null || true
    fi

    if [[ "$GPU_CHOICE" == "nvidia" || "$GPU_CHOICE" == "dual" ]]; then
        WIN_OCR_INSTALL="pip install paddlepaddle-gpu==3.3.1 -i https://www.paddlepaddle.org.cn/packages/stable/cu126/ && python -m pip install \"paddleocr>=3.3\" \"rapidocr-onnxruntime>=1.3\" onnxruntime"
        WIN_FORCE_CPU="0"
        WIN_OCR_ENGINE="paddle"
        WIN_EXE_NAME="GameOCR_nvidia-x64"
        WIN_PYI_MODE="--onedir"
        WIN_PYI_OCR_FLAGS="--collect-all paddleocr --collect-all paddlex --collect-all rapidocr_onnxruntime --collect-all onnxruntime"
    else
        WIN_OCR_INSTALL="pip install \"rapidocr-onnxruntime>=1.3\" onnxruntime"
        WIN_FORCE_CPU="1"
        WIN_OCR_ENGINE="rapidocr"
        WIN_EXE_NAME="GameOCR-Universal-x64"
        WIN_PYI_MODE="--onefile"
        WIN_PYI_OCR_FLAGS="--collect-all rapidocr_onnxruntime --collect-all onnxruntime --exclude-module paddle --exclude-module paddleocr --exclude-module paddlex"
    fi

    WIN_PS1="$DIST_DIR/setup-windows.ps1"
    cat > "$WIN_PS1" <<EOF
# =============================================================================
# GameOCR Windows 10/11 - Otomatik Python 3.12 Kurulum ve TEK EXE Derleyici
# Not: Windows PowerShell 5.1 uyumlulugu icin yalnizca saf ASCII karakterler kullanilmistir.
# =============================================================================
\$ErrorActionPreference = "Stop"
Set-Location -Path \$PSScriptRoot

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host " GameOCR Windows 10/11 - Otomatik Kurulum ve Tek .EXE Derleyici" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan

function Find-Python312 {
    try {
        \$ver = & py -3.12 --version 2>&1
        if (\$LASTEXITCODE -eq 0 -and \$ver -match "3\.12\.") {
            return @{ Exe = "py"; Args = @("-3.12") }
        }
    } catch {}
    try {
        \$ver = & python --version 2>&1
        if (\$LASTEXITCODE -eq 0 -and \$ver -match "3\.12\.") {
            return @{ Exe = "python"; Args = @() }
        }
    } catch {}
    \$localPy = Join-Path \$env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
    if (Test-Path \$localPy) {
        return @{ Exe = \$localPy; Args = @() }
    }
    return \$null
}

\$pyInfo = Find-Python312
if (-not \$pyInfo) {
    Write-Host "[1/4] Python 3.12 bulunamadi. Python 3.12 otomatik olarak kuruluyor..." -ForegroundColor Yellow
    \$installed = \$false
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host " -> winget ile Python.Python.3.12 kuruluyor..." -ForegroundColor Cyan
        & winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
        if (\$LASTEXITCODE -eq 0) { \$installed = \$true }
    }
    if (-not \$installed) {
        Write-Host " -> Resmi Python 3.12.8 x64 kurucusu indiriliyor..." -ForegroundColor Cyan
        \$installerUrl = "https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe"
        \$installerPath = Join-Path \$env:TEMP "python-3.12.8-amd64.exe"
        Invoke-WebRequest -Uri \$installerUrl -OutFile \$installerPath -UseBasicParsing
        Write-Host " -> Python 3.12.8 sessiz kurulumu baslatiliyor..." -ForegroundColor Cyan
        Start-Process -FilePath \$installerPath -ArgumentList "/quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_launcher=1" -Wait
    }
    \$pyInfo = Find-Python312
    if (-not \$pyInfo) {
        Write-Error "Python 3.12 otomatik kurulumu tamamlanamadi. Lutfen https://www.python.org/downloads/ adresinden Python 3.12 kurun."
        exit 1
    }
}

Write-Host "[2/4] Python 3.12 hazir: \$(\$pyInfo.Exe)" -ForegroundColor Green
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host " -> .venv sanal ortami olusturuluyor (Python 3.12)..." -ForegroundColor Cyan
    \$venvArgs = @(\$pyInfo.Args) + @("-m", "venv", ".venv")
    & \$pyInfo.Exe @venvArgs
}

\$venvPy = Join-Path \$PSScriptRoot ".venv\Scripts\python.exe"
Write-Host "[3/4] Bagimliliklar ve OCR motoru kuruluyor (${GPU_CHOICE})..." -ForegroundColor Cyan
& \$venvPy -m pip install --upgrade pip wheel setuptools
if ("${GPU_CHOICE}" -eq "nvidia" -or "${GPU_CHOICE}" -eq "dual") {
    & \$venvPy -m pip install paddlepaddle-gpu==3.3.1 -i https://www.paddlepaddle.org.cn/packages/stable/cu126/
    & \$venvPy -m pip install "paddleocr>=3.3" "rapidocr-onnxruntime>=1.3" onnxruntime
} else {
    & \$venvPy -m pip install "rapidocr-onnxruntime>=1.3" onnxruntime
}
& \$venvPy -m pip install pyinstaller ctranslate2 sentencepiece mss opencv-python-headless numpy rapidfuzz PyQt6 deepl tomli-w python-dotenv
\$prevEap = \$ErrorActionPreference
\$ErrorActionPreference = "Continue"
& \$venvPy -m pip install dxcam *> \$null
if (\$LASTEXITCODE -ne 0) {
    Write-Host "[BILGI] Opsiyonel dxcam paketi kurulamadi; MSS yakalama motoru kullanilacak." -ForegroundColor Yellow
}
\$ErrorActionPreference = \$prevEap

Write-Host "[4/4] Tek dosyalik ${WIN_EXE_NAME}.exe derleniyor..." -ForegroundColor Cyan
\$env:PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK = "True"
\$env:GAMEOCR_FORCE_CPU = "${WIN_FORCE_CPU}"
\$env:GAMEOCR_OCR_ENGINE = "${WIN_OCR_ENGINE}"

\$pyiArgs = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "${WIN_PYI_MODE}",
    "--windowed",
    "--name", "${WIN_EXE_NAME}",
    "--add-data", "config.default.toml;.",
    "--collect-submodules", "gameocr",
    "--collect-all", "rapidocr_onnxruntime",
    "--collect-all", "onnxruntime",
    "--collect-all", "ctranslate2",
    "--collect-all", "sentencepiece",
    "--hidden-import", "gameocr.capture.win32_backend",
    "--hidden-import", "mss"
)
if (Test-Path "models") {
    \$pyiArgs += @("--add-data", "models;models")
}
if (Test-Path "gameocr\assets\icons") {
    \$pyiArgs += @("--add-data", "gameocr/assets/icons;gameocr/assets/icons")
}
if (Test-Path "gameocr\assets\icons\gameocr.ico") {
    \$pyiArgs += @("--icon", "gameocr/assets/icons/gameocr.ico")
}
if ("${GPU_CHOICE}" -eq "nvidia" -or "${GPU_CHOICE}" -eq "dual") {
    \$pyiArgs += @("--collect-all", "paddleocr", "--collect-all", "paddlex")
} else {
    \$pyiArgs += @("--exclude-module", "paddle", "--exclude-module", "paddleocr", "--exclude-module", "paddlex")
}
\$pyiArgs += "gameocr/__main__.py"

& \$venvPy @pyiArgs

if (Test-Path "dist\\${WIN_EXE_NAME}.exe") {
    Copy-Item -Path "dist\\${WIN_EXE_NAME}.exe" -Destination "${WIN_EXE_NAME}.exe" -Force
    Copy-Item -Path "dist\\${WIN_EXE_NAME}.exe" -Destination "GameOCR.exe" -Force
}
if ((Test-Path "models") -and (Test-Path "dist\\${WIN_EXE_NAME}")) {
    Copy-Item -Path "models" -Destination "dist\\${WIN_EXE_NAME}\\models" -Recurse -Force
}

Write-Host ""
Write-Host "[BASARILI] Tek dosyalik GameOCR Windows .EXE hazir: ${WIN_EXE_NAME}.exe" -ForegroundColor Green
EOF

    WIN_BAT="$DIST_DIR/build-windows.bat"
    cat > "$WIN_BAT" <<EOF
@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
REM ============================================================================
REM GameOCR Windows 10/11 Tek Dosya .EXE Derleme Betigi (${COMPILER_CHOICE} - ${GPU_CHOICE})
REM Python 3.12 kurulu degilse otomatik olarak indirir ve kurar.
REM ============================================================================
echo ============================================================================
echo  GameOCR Windows 10/11 - Otomatik Python 3.12 ve Tek .EXE Derleme
echo ============================================================================

set PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True
set GAMEOCR_FORCE_CPU=${WIN_FORCE_CPU}
set GAMEOCR_OCR_ENGINE=${WIN_OCR_ENGINE}

REM 1. Python 3.12 kontrolu ve otomatik kurulumu
py -3.12 --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [BILGI] Python 3.12 sistemde bulunamadi. Otomatik Python 3.12 kurulumu baslatiliyor...
    where winget >nul 2>&1
    if !ERRORLEVEL! EQU 0 (
        echo  -^> winget ile Python 3.12 kuruluyor...
        winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
    ) else (
        echo  -^> Resmi Python 3.12.8 kurucusu indiriliyor ve sessizce kuruluyor...
        powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe' -OutFile '%TEMP%\python-3.12.8-amd64.exe'; Start-Process -FilePath '%TEMP%\python-3.12.8-amd64.exe' -ArgumentList '/quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_launcher=1' -Wait"
    )
)

REM 2. PowerShell derleme betigini calistir (veya dogrudan PyInstaller calistir)
if exist "%~dp0setup-windows.ps1" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup-windows.ps1"
    if !ERRORLEVEL! EQU 0 goto :done
)

REM Yedek dogrudan kurulum ve Tek Dosya (--onefile) PyInstaller komutu
if not exist ".venv\Scripts\python.exe" (
    py -3.12 -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip wheel setuptools
python -m ${WIN_OCR_INSTALL}
python -m pip install pyinstaller ctranslate2 sentencepiece mss opencv-python-headless numpy rapidfuzz PyQt6 deepl tomli-w python-dotenv
python -m pip install dxcam >nul 2>&1 || echo [BILGI] Opsiyonel dxcam paketi kurulamadi; MSS yakalama kullanilacak.

set MODEL_DATA_ARG=
if exist "models" (
    set MODEL_DATA_ARG=--add-data "models;models"
)
set ICON_DATA_ARG=
if exist "gameocr\assets\icons" (
    set ICON_DATA_ARG=--add-data "gameocr/assets/icons;gameocr/assets/icons"
)
set ICON_EXE_ARG=
if exist "gameocr\assets\icons\gameocr.ico" (
    set ICON_EXE_ARG=--icon "gameocr/assets/icons/gameocr.ico"
)

python -m PyInstaller --noconfirm --clean ${WIN_PYI_MODE} --windowed --name ${WIN_EXE_NAME} ^
    --add-data "config.default.toml;." ^
    %MODEL_DATA_ARG% ^
    %ICON_DATA_ARG% ^
    %ICON_EXE_ARG% ^
    --collect-submodules gameocr ^
    ${WIN_PYI_OCR_FLAGS} ^
    --collect-all ctranslate2 ^
    --collect-all sentencepiece ^
    --hidden-import gameocr.capture.win32_backend ^
    --hidden-import mss ^
    gameocr/__main__.py

if exist "dist\\${WIN_EXE_NAME}.exe" (
    copy /Y "dist\\${WIN_EXE_NAME}.exe" "${WIN_EXE_NAME}.exe" >nul
    copy /Y "dist\\${WIN_EXE_NAME}.exe" "GameOCR.exe" >nul
)

:done
echo.
echo [GameOCR Windows] Tek dosyalik EXE derlemesi tamamlandi: ${WIN_EXE_NAME}.exe
pause
EOF

    WIN_RUN_BAT="$DIST_DIR/run-windows.bat"
    cat > "$WIN_RUN_BAT" <<EOF
@echo off
cd /d "%~dp0"
set GAMEOCR_FORCE_CPU=${WIN_FORCE_CPU}
set GAMEOCR_OCR_ENGINE=${WIN_OCR_ENGINE}
if exist "${WIN_EXE_NAME}.exe" (
    start "" "${WIN_EXE_NAME}.exe"
    exit /b 0
)
if exist "GameOCR.exe" (
    start "" "GameOCR.exe"
    exit /b 0
)
if exist "dist\\${WIN_EXE_NAME}.exe" (
    start "" "dist\\${WIN_EXE_NAME}.exe"
    exit /b 0
)
if exist "dist\\${WIN_EXE_NAME}\\${WIN_EXE_NAME}.exe" (
    start "" "dist\\${WIN_EXE_NAME}\\${WIN_EXE_NAME}.exe"
    exit /b 0
)
if not exist ".venv\Scripts\python.exe" (
    call "%~dp0build-windows.bat"
)
".venv\Scripts\python.exe" -m gameocr
EOF

    echo -e "\n${CYAN}• Windows 10/11 otomatik Python 3.12 kuruculu derleme betikleri oluşturuldu:${NC}"
    echo -e "  - $WIN_BAT"
    echo -e "  - $WIN_PS1"
    echo -e "  - $WIN_RUN_BAT"

    echo -e "\n${BLUE}[PyInstaller Komutu]:${NC}"
    echo "  py -3.12 -m PyInstaller --noconfirm --clean --windowed --name GameOCR --icon gameocr/assets/icons/gameocr.ico --add-data config.default.toml;. --add-data gameocr/assets/icons;gameocr/assets/icons --collect-submodules gameocr --collect-all ctranslate2 --hidden-import gameocr.capture.win32_backend --hidden-import mss gameocr/__main__.py"

    if [[ "$DRY_RUN" -eq 1 ]]; then
        echo -e "\n${GREEN}[DRY-RUN] Windows 10/11 derleme komutu ve otomatik Python 3.12 kurulum paketi doğrulandı (çalıştırılmadı).${NC}"
        exit 0
    fi

    WIN_ZIP="$PROJECT_DIR/GameOCR-Windows-${GPU_CHOICE}.zip"
    "$PYTHON_BIN" -c "
import shutil
shutil.make_archive('$PROJECT_DIR/GameOCR-Windows-${GPU_CHOICE}', 'zip', '$DIST_DIR')
"
    echo -e "\n${GREEN}${BOLD}✓ Windows 10/11 Taşınabilir Kurulum & Derleme Paketi Hazır:${NC}"
    echo -e "  • Klasör : ${YELLOW}$DIST_DIR${NC}"
    echo -e "  • Arşiv  : ${YELLOW}$WIN_ZIP${NC}"
    echo -e "  • Bilgi  : Windows üzerinde ${BOLD}build-windows.bat${NC} dosyasına çift tıkladığınızda Python 3.12 kurulu değilse otomatik indirip kurar ve ${BOLD}GameOCR.exe${NC} üretir."
    exit 0
fi

# =============================================================================
# AŞAMA 10: Çift Sürüm (NVIDIA-GPU ~2.3GB ve Universal-Lite ~600MB) .AppImage Üretimi
# =============================================================================
ensure_appimage_runtime() {
    local rt_path="$PROJECT_DIR/build/runtime-x86_64"
    mkdir -p "$PROJECT_DIR/build"
    if [[ ! -x "$rt_path" ]]; then
        echo -e "${CYAN}• Resmi AppImage Type-2 statik FUSE runtime indiriliyor...${NC}"
        curl -fsSL -o "$rt_path" "https://github.com/AppImage/type2-runtime/releases/download/continuous/runtime-x86_64" || true
        chmod +x "$rt_path" 2>/dev/null || true
    fi
}

ensure_cpu_paddle_cache() {
    local cpu_pkg_dir="$PROJECT_DIR/build/cpu_paddle_pkg"
    if [[ ! -d "$cpu_pkg_dir/paddle" ]]; then
        echo -e "${CYAN}• Universal-Lite sürümü için CPU-only paddlepaddle==3.3.1 çalışma zamanı hazırlanıyor...${NC}"
        mkdir -p "$cpu_pkg_dir"
        if command -v uv >/dev/null 2>&1; then
            uv pip install --target "$cpu_pkg_dir" --no-deps "paddlepaddle==3.3.1"
        else
            "$PYTHON_BIN" -m pip install --target "$cpu_pkg_dir" --no-deps "paddlepaddle==3.3.1"
        fi
    fi
}

build_linux_appimage_edition() {
    local edition_gpu="$1"
    local edition_label=""
    local appimage_filename=""
    local compat_filename=""
    local ocr_engine_env=""
    local force_cpu_val="0"

    if [[ "$edition_gpu" == "nvidia" ]]; then
        edition_label="NVIDIA-GPU (CUDA 12.6 + cuDNN + PaddleOCR Tam Bağımsız)"
        appimage_filename="GameOCR_nvidia-x86_64.AppImage"
        compat_filename="GameOCR-NVIDIA-GPU-x86_64.AppImage"
        ocr_engine_env="paddle"
        force_cpu_val="0"
    else
        edition_label="Universal-Lite (ONNX-CPU RapidOCR Tam Bağımsız)"
        appimage_filename="GameOCR-Universal-x86_64.AppImage"
        compat_filename="GameOCR-Universal-Lite-x86_64.AppImage"
        ocr_engine_env="rapidocr"
        force_cpu_val="1"
    fi

    echo -e "\n${CYAN}• [${edition_label}] (${BUNDLE_MODE}) ${appimage_filename} paketi oluşturuluyor...${NC}"

    local edition_launcher="$BUILD_DIR/gameocr_launcher_${edition_gpu}"
    if command -v gcc >/dev/null 2>&1; then
        local launcher_c="$BUILD_DIR/gameocr_launcher_${edition_gpu}.c"
        cat > "$launcher_c" <<EOF
#define _GNU_SOURCE
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

/* AppImage Type-2 ELF Magic Signature ("AI\x02") */
__attribute__((section(".note.appimage"), used))
static const unsigned char appimage_magic[4] = {'A', 'I', 0x02, 0x00};

int main(int argc, char *argv[]) {
    if (argc > 1 && strcmp(argv[1], "--appimage-help") == 0) {
        printf("GameOCR AppImage (${edition_label}) - Double-click or run directly.\n");
        return 0;
    }
    setenv("QT_QPA_PLATFORM", "xcb", 0);
    setenv("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True", 1);
    setenv("PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT", "False", 1);
    setenv("FLAGS_allocator_strategy", "auto_growth", 0);
    setenv("FLAGS_eager_delete_tensor_gb", "0.0", 0);
    setenv("FLAGS_fast_eager_deletion_mode", "1", 0);
    setenv("FLAGS_fraction_of_gpu_memory_to_use", "0.35", 0);
    setenv("GAMEOCR_DE_PROFILE", "${DE_CHOICE}", 0);
    setenv("GAMEOCR_OCR_ENGINE", "${ocr_engine_env}", 0);
    if (${force_cpu_val}) {
        setenv("GAMEOCR_FORCE_CPU", "1", 0);
        setenv("OMP_NUM_THREADS", "4", 0);
    }

    char exe_dir[PATH_MAX];
    ssize_t len = readlink("/proc/self/exe", exe_dir, sizeof(exe_dir) - 1);
    if (len > 0) {
        exe_dir[len] = '\0';
        char *slash = strrchr(exe_dir, '/');
        if (slash) *slash = '\0';
    } else {
        strcpy(exe_dir, "${PROJECT_DIR}");
    }

    char internal_dir[PATH_MAX];
    snprintf(internal_dir, sizeof(internal_dir), "%s/_internal", exe_dir);
    if (access(internal_dir, F_OK) == 0) {
        setenv("PYTHONPATH", internal_dir, 1);
    } else {
        setenv("PYTHONPATH", "${PROJECT_DIR}", 1);
    }

    char models_dir[PATH_MAX];
    snprintf(models_dir, sizeof(models_dir), "%s/models", exe_dir);
    if (access(models_dir, F_OK) == 0) {
        setenv("GAMEOCR_BUNDLED_MODELS_DIR", models_dir, 0);
    }

    const char *py_candidates[] = {
        "${PYTHON_BIN}",
        "${PROJECT_DIR}/.venv/bin/python",
        "/usr/bin/python3.12",
        "/usr/bin/python3",
        NULL
    };
    const char *chosen_py = "python3";
    for (int i = 0; py_candidates[i] != NULL; ++i) {
        if (access(py_candidates[i], X_OK) == 0) {
            chosen_py = py_candidates[i];
            break;
        }
    }

    char **new_argv = calloc((size_t)argc + 4, sizeof(char *));
    new_argv[0] = (char *)chosen_py;
    new_argv[1] = "-m";
    new_argv[2] = "gameocr";
    for (int i = 1; i < argc; ++i) {
        new_argv[i + 2] = argv[i];
    }
    new_argv[argc + 2] = NULL;

    execvp(chosen_py, new_argv);
    perror("GameOCR baslatilamadi");
    return 1;
}
EOF
        gcc -O2 "$launcher_c" -o "$edition_launcher"
        "$PYTHON_BIN" -c "
with open('$edition_launcher', 'r+b') as f:
    f.seek(8)
    f.write(b'AI\x02\x00')
"
        chmod +x "$edition_launcher"
        cp -f "$edition_launcher" "$DIST_DIR/gameocr/gameocr"
    fi

    if command -v mksquashfs >/dev/null 2>&1; then
        local appdir="$BUILD_DIR/GameOCR-${edition_gpu}.AppDir"
        rm -rf "$appdir"
        mkdir -p "$appdir/usr/bin" "$appdir/usr/app" "$appdir/usr/models"
        cp -f "$DIST_DIR/gameocr/gameocr" "$appdir/usr/bin/gameocr"
        cp -rf "$PROJECT_DIR/gameocr" "$appdir/usr/app/"
        cp -f "$PROJECT_DIR/config.default.toml" "$appdir/usr/app/"

        local user_models="${XDG_DATA_HOME:-$HOME/.local/share}/gameocr/models"
        if [[ -d "$user_models" ]]; then
            cp -rl "$user_models/"* "$appdir/usr/models/" 2>/dev/null || cp -r "$user_models/"* "$appdir/usr/models/" 2>/dev/null || true
        fi
        if [[ -d "$PROJECT_DIR/models" ]]; then
            cp -rl "$PROJECT_DIR/models/"* "$appdir/usr/models/" 2>/dev/null || cp -r "$PROJECT_DIR/models/"* "$appdir/usr/models/" 2>/dev/null || true
        fi

        if [[ "$BUNDLE_MODE" == "full" ]]; then
            ensure_appimage_runtime
            local base_py_prefix
            base_py_prefix="$("$PYTHON_BIN" -c 'import sys; print(sys.base_prefix)')"
            local site_pkgs
            site_pkgs="$("$PYTHON_BIN" -c 'import site; print(site.getsitepackages()[0])')"

            echo -e "  -> Taşınabilir Python 3.12 çalışma zamanı gömülüyor ($base_py_prefix)..."
            mkdir -p "$appdir/usr/python" "$appdir/usr/site-packages"
            cp -rlf "$base_py_prefix/"* "$appdir/usr/python/"

            if [[ "$edition_gpu" == "nvidia" ]]; then
                echo -e "  -> NVIDIA CUDA 12.6 + cuDNN + PaddleOCR GPU kütüphaneleri gömülüyor..."
                cp -rlf "$site_pkgs/"* "$appdir/usr/site-packages/"
                # OCR tarafından kullanılmayan LLM Flash-Attention kütüphanelerini çıkar (~880 MB tasarruf)
                # NOT: libcinnapi.so libpaddle.so tarafından doğrudan dinamik bağlandığı için silinmemelidir!
                rm -f "$appdir/usr/site-packages/paddle/libs/libflashattn"* \
                      "$appdir/usr/site-packages/paddle/libs/libflashmask"* 2>/dev/null || true
                if [[ -d "$HOME/.paddlex/official_models" ]]; then
                    echo -e "  -> Çevrimdışı PP-OCRv5 algılama ve okuma modelleri gömülüyor..."
                    mkdir -p "$appdir/usr/paddlex_models"
                    cp -rlf "$HOME/.paddlex/official_models/"* "$appdir/usr/paddlex_models/"
                fi
            else
                echo -e "  -> Universal-Lite (ONNX-CPU RapidOCR + ONNXRuntime, ağır CUDA/Paddle hariç) kütüphaneleri gömülüyor..."
                for pkg_item in "$site_pkgs/"*; do
                    local pkg_base
                    pkg_base="$(basename "$pkg_item")"
                    case "$pkg_base" in
                        paddle|paddlepaddle*|paddleocr*|paddlex*|nvidia|nvidia_*|cusparselt|cusparselt*|opencv_python-*)
                            continue
                            ;;
                        *)
                            cp -rlf "$pkg_item" "$appdir/usr/site-packages/"
                            ;;
                    esac
                done
            fi

            # cv2 (opencv-python) içindeki Qt eklentileri PyQt6 ile çakıştığı için temizle
            rm -rf "$appdir/usr/site-packages/cv2/qt" 2>/dev/null || true

            # Temiz Linux dağıtımlarında (örn. Linux Mint / Ubuntu) eksik olabilen Qt xcb
            # sistem bağımlılıklarını (özellikle libxcb-cursor.so.0) fallback olarak göm.
            # NOT: libxkbcommon-x11.so.0, hosttaki libxkbcommon.so.0 ile birebir aynı sürümden
            # gelmek zorunda olduğu için (aksi halde xkb_state_key_get_layout SIGSEGV verir) gömülmez.
            mkdir -p "$appdir/usr/lib"
            local xcb_fallback_libs=(
                "libxcb-cursor.so.0"
                "libxcb-icccm.so.4"
                "libxcb-image.so.0"
                "libxcb-keysyms.so.1"
                "libxcb-render-util.so.0"
                "libxcb-util.so.1"
            )
            for xlib_name in "${xcb_fallback_libs[@]}"; do
                local xlib_path=""
                xlib_path="$(ldconfig -p 2>/dev/null | awk -v n="$xlib_name" '!found && $1 == n && $0 ~ /x86-64/ {print $NF; found=1}')"
                if [[ -z "$xlib_path" ]]; then
                    for d in /lib64 /usr/lib64 /lib/x86_64-linux-gnu /usr/lib/x86_64-linux-gnu; do
                        if [[ -e "$d/$xlib_name" ]]; then
                            xlib_path="$d/$xlib_name"
                            break
                        fi
                    done
                fi
                if [[ -n "$xlib_path" && -e "$xlib_path" ]]; then
                    cp -Lf "$xlib_path" "$appdir/usr/lib/$xlib_name"
                fi
            done

            cat > "$appdir/AppRun" <<APPRUN_EOF
#!/usr/bin/env bash
HERE="\$(dirname "\$(readlink -f "\${0}")")"
export QT_QPA_PLATFORM=xcb
export PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True
export PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT=False
export FLAGS_allocator_strategy=auto_growth
export FLAGS_eager_delete_tensor_gb=0.0
export FLAGS_fast_eager_deletion_mode=1
export GAMEOCR_BUNDLED_MODELS_DIR="\$HERE/usr/models"
export GAMEOCR_DE_PROFILE="${DE_CHOICE}"
export GAMEOCR_OCR_ENGINE="${ocr_engine_env}"

# İlk çalışmada gömülü PaddleOCR modellerini kullanıcı önbelleğine bağla (NVIDIA çevrimdışı çalışma)
if [[ -d "\$HERE/usr/paddlex_models" ]]; then
    mkdir -p "\$HOME/.paddlex/official_models"
    for mdir in "\$HERE/usr/paddlex_models/"*; do
        [[ -e "\$mdir" ]] || continue
        mname="\$(basename "\$mdir")"
        if [[ ! -e "\$HOME/.paddlex/official_models/\$mname" ]]; then
            cp -rn "\$mdir" "\$HOME/.paddlex/official_models/" 2>/dev/null || ln -sf "\$mdir" "\$HOME/.paddlex/official_models/\$mname" 2>/dev/null || true
        fi
    done
fi

if [[ "${force_cpu_val}" == "1" ]]; then
    export GAMEOCR_FORCE_CPU=1
    export CUDA_VISIBLE_DEVICES=-1
    export OMP_NUM_THREADS=4
    export LD_LIBRARY_PATH="\$HERE/usr/python/lib\${LD_LIBRARY_PATH:+:\$LD_LIBRARY_PATH}:\$HERE/usr/lib"
else
    export FLAGS_fraction_of_gpu_memory_to_use=0.35
    NVIDIA_LIBS=""
    if [[ -d "\$HERE/usr/site-packages/nvidia" ]]; then
        for nlib in "\$HERE/usr/site-packages/nvidia"/*/lib; do
            [[ -d "\$nlib" ]] && NVIDIA_LIBS="\${NVIDIA_LIBS:+\$NVIDIA_LIBS:}\$nlib"
        done
    fi
    if [[ -d "\$HERE/usr/site-packages/cusparselt/lib" ]]; then
        NVIDIA_LIBS="\${NVIDIA_LIBS:+\$NVIDIA_LIBS:}\$HERE/usr/site-packages/cusparselt/lib"
    fi
    export LD_LIBRARY_PATH="\${NVIDIA_LIBS:+\$NVIDIA_LIBS:}\$HERE/usr/site-packages/paddle/libs:\$HERE/usr/python/lib\${LD_LIBRARY_PATH:+:\$LD_LIBRARY_PATH}:\$HERE/usr/lib"
fi

if [[ -d "\$HERE/usr/site-packages/PyQt6/Qt6/plugins/platforms" ]]; then
    export QT_PLUGIN_PATH="\$HERE/usr/site-packages/PyQt6/Qt6/plugins"
    export QT_QPA_PLATFORM_PLUGIN_PATH="\$HERE/usr/site-packages/PyQt6/Qt6/plugins/platforms"
fi

export PYTHONHOME="\$HERE/usr/python"
export PYTHONPATH="\$HERE/usr/app:\$HERE/usr/site-packages:\$HERE/usr/python/lib/python3.12"
exec "\$HERE/usr/python/bin/python3.12" -m gameocr "\$@"
APPRUN_EOF
            chmod +x "$appdir/AppRun"
        else
            cat > "$appdir/AppRun" <<APPRUN_EOF
#!/usr/bin/env bash
HERE="\$(dirname "\$(readlink -f "\${0}")")"
export QT_QPA_PLATFORM=xcb
export PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True
export PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT=False
export FLAGS_allocator_strategy=auto_growth
export FLAGS_eager_delete_tensor_gb=0.0
export FLAGS_fast_eager_deletion_mode=1
export GAMEOCR_BUNDLED_MODELS_DIR="\$HERE/usr/models"
export GAMEOCR_OCR_ENGINE="${ocr_engine_env}"
if [[ "${force_cpu_val}" == "1" ]]; then
    export GAMEOCR_FORCE_CPU=1
    export OMP_NUM_THREADS=4
fi
export PYTHONPATH="\$HERE/usr/app:\${PYTHONPATH:-}"
exec "\$HERE/usr/bin/gameocr" "\$@"
APPRUN_EOF
            chmod +x "$appdir/AppRun"
        fi

        cat > "$appdir/gameocr.desktop" <<DESKTOP_EOF
[Desktop Entry]
Type=Application
Name=GameOCR (${edition_gpu^^})
GenericName=Game Subtitle Translator
Comment=Gerçek Zamanlı Oyun Altyazı OCR ve Çeviri Katmanı (${edition_label})
Exec=AppRun
Icon=gameocr
Categories=Utility;Game;
Terminal=false
StartupNotify=false
X-KDE-StartupNotify=false
StartupWMClass=gameocr
DESKTOP_EOF

        mkdir -p "$appdir/usr/share/applications"
        cp -f "$appdir/gameocr.desktop" "$appdir/usr/share/applications/gameocr.desktop"

        if [[ -f "$PROJECT_DIR/gameocr/assets/icons/logo_256.png" ]]; then
            cp -f "$PROJECT_DIR/gameocr/assets/icons/logo_256.png" "$appdir/gameocr.png"
            cp -f "$PROJECT_DIR/gameocr/assets/icons/logo_256.png" "$appdir/.DirIcon"
        fi
        for isz in 24 32 64 128 256 512; do
            if [[ -f "$PROJECT_DIR/gameocr/assets/icons/logo_${isz}.png" ]]; then
                mkdir -p "$appdir/usr/share/icons/hicolor/${isz}x${isz}/apps"
                cp -f "$PROJECT_DIR/gameocr/assets/icons/logo_${isz}.png" "$appdir/usr/share/icons/hicolor/${isz}x${isz}/apps/gameocr.png"
            fi
        done

        local squashfs_img="$BUILD_DIR/gameocr_${edition_gpu}.squashfs"
        rm -f "$squashfs_img"
        echo -e "  -> SquashFS sıkıştırması yapılıyor (zstd, $(nproc) çekirdek)..."
        mksquashfs "$appdir" "$squashfs_img" -root-owned -noappend -comp zstd -Xcompression-level 1 -processors "$(nproc)" >/dev/null

        local appimage_out="$PROJECT_DIR/${appimage_filename}"
        local rt_bin="$PROJECT_DIR/build/runtime-x86_64"
        if [[ "$BUNDLE_MODE" == "full" && -x "$rt_bin" ]]; then
            cat "$rt_bin" "$squashfs_img" > "$appimage_out"
        else
            cat "$edition_launcher" "$squashfs_img" > "$appimage_out"
        fi
        chmod +x "$appimage_out"
        if [[ -n "$compat_filename" && "$compat_filename" != "$appimage_filename" ]]; then
            ln -f "$appimage_out" "$PROJECT_DIR/${compat_filename}" 2>/dev/null || cp -f "$appimage_out" "$PROJECT_DIR/${compat_filename}"
        fi
        cp -f "$appimage_out" "$PROJECT_DIR/GameOCR-x86_64.AppImage"
        rm -rf "$squashfs_img" "$appdir"
        local final_size
        final_size="$(du -sh "$appimage_out" | cut -f1)"
        echo -e "${GREEN}${BOLD}✓ Çift Tıklanabilir Tam Bağımsız AppImage Hazır (${edition_label} — Boyut: ${final_size}):${NC} $appimage_out"
    fi
}

if [[ "$COMPILER_CHOICE" == "pyinstaller" ]]; then
    PYI_ARGS=(
        "$PYTHON_BIN" "-m" "PyInstaller"
        "--noconfirm"
        "--name" "gameocr"
        "--distpath" "$DIST_DIR"
        "--workpath" "$BUILD_DIR"
        "--add-data" "$PROJECT_DIR/config.default.toml:."
        "--add-data" "$PROJECT_DIR/gameocr/assets/icons:gameocr/assets/icons"
        "--collect-submodules" "gameocr"
    )
    for hi in "${HIDDEN_IMPORTS[@]}"; do
        PYI_ARGS+=("--hidden-import" "$hi")
    done
    for ex in "${EXCLUDES[@]}"; do
        PYI_ARGS+=("--exclude-module" "$ex")
    done
    PYI_ARGS+=("${GPU_COMPILE_FLAGS[@]}")
    PYI_ARGS+=("$PROJECT_DIR/gameocr/__main__.py")

    echo -e "\n${BLUE}[PyInstaller Komutu]:${NC}"
    echo "  ${PYI_ARGS[*]}"

    if [[ "$DRY_RUN" -eq 1 ]]; then
        echo -e "\n${GREEN}[DRY-RUN] Derleme komutu başarıyla doğrulandı (çalıştırılmadı).${NC}"
        exit 0
    fi

    ensure_compiler_installed "PyInstaller" "pyinstaller>=6.0"

    export PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True
    mkdir -p "$DIST_DIR/gameocr" "$BUILD_DIR"
    EXISTING_INTERNAL=""
    for cand_internal in "$DIST_DIR/gameocr/_internal" "$PROJECT_DIR"/dist/gameocr-*/gameocr/_internal; do
        if [[ -d "$cand_internal/paddlex" || -f "$cand_internal/base_library.zip" ]]; then
            EXISTING_INTERNAL="$cand_internal"
            break
        fi
    done

    if [[ -n "$EXISTING_INTERNAL" && "$EXISTING_INTERNAL" != "$DIST_DIR/gameocr/_internal" ]]; then
        echo -e "${CYAN}• Mevcut PyInstaller runtime önbelleği bağlanıyor ($EXISTING_INTERNAL)...${NC}"
        mkdir -p "$DIST_DIR/gameocr/_internal"
        cp -rs "$EXISTING_INTERNAL/"* "$DIST_DIR/gameocr/_internal/" 2>/dev/null || true
    elif [[ -z "$EXISTING_INTERNAL" ]]; then
        "${PYI_ARGS[@]}"
    else
        echo -e "${CYAN}• Mevcut PyInstaller runtime önbelleği ($DIST_DIR/gameocr/_internal) güncelleniyor...${NC}"
    fi

    # Varsayılan kurulu lokal modelleri (örn. EN-TR, TR-EN) dağıtım klasörüne kopyala
    USER_MODELS_ROOT="${XDG_DATA_HOME:-$HOME/.local/share}/gameocr/models"
    if [[ -d "$USER_MODELS_ROOT" ]]; then
        mkdir -p "$DIST_DIR/gameocr/models" "$DIST_DIR/gameocr/_internal/models"
        cp -r "$USER_MODELS_ROOT/"* "$DIST_DIR/gameocr/models/" 2>/dev/null || true
        cp -r "$USER_MODELS_ROOT/"* "$DIST_DIR/gameocr/_internal/models/" 2>/dev/null || true
    fi

    # Güncel gameocr kaynak paketini doğrudan _internal içine de kopyala
    mkdir -p "$DIST_DIR/gameocr/_internal"
    cp -rf "$PROJECT_DIR/gameocr" "$DIST_DIR/gameocr/_internal/"
    cp -f "$PROJECT_DIR/config.default.toml" "$DIST_DIR/gameocr/_internal/"
    cp -f "$PROJECT_DIR/config.default.toml" "$DIST_DIR/gameocr/"

    # Başlatıcı sarmalayıcı (wrapper) oluştur (geriye dönük uyumluluk için)
    WRAPPER="$DIST_DIR/gameocr/run-gameocr.sh"
    cat > "$WRAPPER" <<EOF
#!/usr/bin/env bash
DIR="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
exec "\$DIR/gameocr" "\$@"
EOF
    chmod +x "$WRAPPER"

    if [[ "$GPU_CHOICE" == "dual" ]]; then
        build_linux_appimage_edition "lite"
        build_linux_appimage_edition "nvidia"
    elif [[ "$GPU_CHOICE" == "nvidia" ]]; then
        build_linux_appimage_edition "nvidia"
    else
        build_linux_appimage_edition "lite"
    fi

    echo -e "\n${GREEN}${BOLD}✓ PyInstaller + AppImage derlemesi tamamlandı:${NC} $DIST_DIR/gameocr/gameocr"

elif [[ "$COMPILER_CHOICE" == "nuitka" ]]; then
    NUITKA_ARGS=(
        "$PYTHON_BIN" "-m" "nuitka"
        "--standalone"
        "--assume-yes-for-downloads"
        "--enable-plugin=pyqt6"
        "--enable-plugin=numpy"
        "--include-package=gameocr"
        "--include-data-files=$PROJECT_DIR/config.default.toml=config.default.toml"
        "--include-data-dir=$PROJECT_DIR/gameocr/assets/icons=gameocr/assets/icons"
        "--output-dir=$DIST_DIR"
        "--output-filename=gameocr"
    )
    if [[ "$GPU_CHOICE" == "amd" || "$GPU_CHOICE" == "cpu" ]]; then
        NUITKA_ARGS+=("--lto=yes")
    fi
    for ex in "${EXCLUDES[@]}"; do
        NUITKA_ARGS+=("--nofollow-import-to=$ex")
    done
    NUITKA_ARGS+=("$PROJECT_DIR/gameocr/__main__.py")

    echo -e "\n${BLUE}[Nuitka Komutu]:${NC}"
    echo "  ${NUITKA_ARGS[*]}"

    if [[ "$DRY_RUN" -eq 1 ]]; then
        echo -e "\n${GREEN}[DRY-RUN] Nuitka derleme komutu başarıyla doğrulandı (çalıştırılmadı).${NC}"
        exit 0
    fi

    ensure_compiler_installed "nuitka" "nuitka>=2.0"

    mkdir -p "$DIST_DIR"
    "${NUITKA_ARGS[@]}"
    echo -e "\n${GREEN}${BOLD}✓ Nuitka derlemesi tamamlandı:${NC} $DIST_DIR/__main__.dist/gameocr"
fi
