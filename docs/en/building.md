# 🛠️ Smart Interactive Build Script (`build.sh`) & Dual-Edition Packaging

`build.sh` packages GameOCR into double-clickable **Linux `.AppImage` bundles** or a **Windows 10/11 distribution kit** with automatic Python 3.12 installation.

---

## 1. Dual-Edition `.AppImage` Architecture (`NVIDIA-GPU` & `Universal-Lite`)

To support both high-end NVIDIA gaming rigs and AMD / Intel / low-end laptops, `build.sh` can produce two tailored `.AppImage` editions:

1. **`GameOCR-NVIDIA-GPU-x86_64.AppImage` (NVIDIA GPU Edition):**
   - Uses CUDA 12.6 + cuDNN acceleration for 15–25 ms OCR inference.
   - Users can still switch between `Automatic (GPU if available, else CPU)`, `GPU (CUDA)`, and `CPU Only` at any time from **Settings → Capture & OCR → Hardware Acceleration**.
2. **`GameOCR-Universal-Lite-x86_64.AppImage` (AMD / Intel / Low-End Edition):**
   - Excludes heavy NVIDIA CUDA binaries and defaults to `GAMEOCR_FORCE_CPU=1` (`OMP_NUM_THREADS=4`), running smoothly on AMD Radeon GPUs, Intel iGPUs, and low-end CPU-only systems.
   - Includes **Low-End Hardware Optimization** in Settings (`low_end_mode`), which automatically caps capture FPS (`<= 5.0`), upscale factor (`<= 1.5x`), and detection side length (`640px`).

---

## 2. CLI & Interactive Usage

```bash
# Launch interactive wizard
./build.sh

# Build BOTH NVIDIA-GPU and Universal-Lite .AppImage editions at once
./build.sh --de kde --display hybrid --gpu dual --compiler pyinstaller

# Build Windows 10/11 portable kit with automatic Python 3.12 installer
./build.sh --platform windows --gpu nvidia --compiler pyinstaller

# Dry-run verification
./build.sh --de kde --display wayland --gpu dual --compiler pyinstaller --dry-run
```

---

## 3. Windows 10/11 Automatic Python 3.12 Setup

Selecting `5) Windows 10/11` or `--platform windows` generates `dist/gameocr-windows-win32-<gpu>/` and `GameOCR-Windows-<gpu>.zip` containing `build-windows.bat` and `setup-windows.ps1`.
When run on Windows, `build-windows.bat` automatically checks for **Python 3.12**, installs it silently via `winget` or the official `python-3.12.8-amd64.exe` installer if missing, sets up `.venv`, and builds `GameOCR-Universal-x64.exe` / `GameOCR.exe`.

---

## 4. Icon Asset Generation & Linux `.desktop` Integration

- **Multi-Resolution Brand Assets (`tools/generate_icons.py`):** Generates `gameocr/assets/icons/` (`24..1024` PNGs + 5-layer `gameocr.ico`) from `logo/`. `./build.sh` embeds these into Linux AppImages (`.DirIcon` + Hicolor icon theme) and Windows builds (PE `RT_GROUP_ICON` + `_MEIPASS`).
- **Linux Desktop Menu Entry:**
  ```bash
  ./packaging/linux/install-desktop.sh --exec /full/path/to/GameOCR-Universal-x86_64.AppImage
  ./packaging/linux/uninstall-desktop.sh
  ```

---

## 5. Automatic Dependency Bootstrapper & One-Command GitHub Publishing (`publish_github.sh`)

- **Zero-Manual-Download Bootstrapper (`ensure_build_prerequisites`):** When `./build.sh` runs on a fresh clone, it automatically checks for `.venv`, default ONNX OCR models (`en_rec.onnx`, `latin_rec.onnx`), the default `EN-TR` CTranslate2 model, and (when `--gpu nvidia` is selected) `paddlepaddle-gpu==3.3.1` (CUDA 12.6) + `PP-OCRv5` weights, downloading any missing components from their official repositories.
- **One-Command GitHub Release (`publish_github.sh`):**
  ```bash
  # Run privacy, PII, and file-size check
  ./publish_github.sh --check-only

  # Create GitHub repo, push source code, and upload Universal Release assets
  ./publish_github.sh --repo GameOCR --release v0.3.0
  ```
  To respect NVIDIA CUDA redistribution licensing and GitHub's 2 GB file limit, only the lightweight, license-clean Universal packages (`GameOCR-Universal-x86_64.AppImage`, `GameOCR-Universal-x64.exe`, and `GameOCR-Windows-cpu.zip`) are uploaded to GitHub Releases.

