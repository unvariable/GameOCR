# 4. Akıllı Derleme Scripti (`build.sh`) ve Çift Sürüm Paketleme Kılavuzu

`build.sh`, GameOCR'yi hedef sistemde harici kütüphane kurulumu gerektirmeden çalışacak **çift tıklanabilir Linux `.AppImage` paketlerine** veya **otomatik Python 3.12 kuruculu Windows 10/11** paketine dönüştürür.

## 4.1. Çift Sürüm `.AppImage` Mimarisi (NVIDIA-GPU ve Universal-Lite)

Farklı donanım profillerine sahip kullanıcılar için `build.sh` iki ayrı taşınabilir `.AppImage` sürümü üretebilir:

1. **`GameOCR-NVIDIA-GPU-x86_64.AppImage` (NVIDIA GPU Sürümü):**
   - NVIDIA ekran kartına sahip sistemlerde CUDA 12.6 + cuDNN hızlandırmasıyla 15–25 ms OCR çıkarımı sağlar.
   - Kullanıcı dilerse **Ayarlar → Algılama ve OCR → Donanım Hızlandırma** menüsünden istediği an `Yalnızca CPU` moduna geçebilir.
2. **`GameOCR-Universal-Lite-x86_64.AppImage` (AMD / Intel / Düşük Sistem Sürümü):**
   - Ağır NVIDIA CUDA kütüphanelerini içermez; `GAMEOCR_FORCE_CPU=1` ve `OMP_NUM_THREADS=4` ile AMD ekran kartlı, Intel dahili grafikli veya harici ekran kartı olmayan düşük donanımlı (low-end) cihazlarda doğrudan CPU üzerinde çalışır.
   - **Ayarlar → Algılama ve OCR → Düşük Sistem (Low-End) Optimizasyonu** seçeneği ile kare yakalama hızı (`<= 5 FPS`), görüntü ölçekleme (`<= 1.5x`) ve algılama boyutu (`640px`) otomatik optimize edilir.

## 4.2. İnteraktif Kullanım

```bash
./build.sh
```

Sihirbaz kullanıcıya şu 4 soruyu yöneltir:
1. **Masaüstü Ortamı / Platform:** `KDE Plasma`, `GNOME`, `XFCE`, `Diğer Linux` veya `5) Windows 10/11`
2. **Görüntü Sunucusu:** `Wayland`, `X11`, `Hibrit (Her İkisi)` veya `Win32 / DWM`
3. **GPU Hedefi / Sürüm:**
   - `1) NVIDIA GPU Sürümü` (`GameOCR-NVIDIA-GPU-x86_64.AppImage`)
   - `2) AMD GPU / Universal Lite` (`GameOCR-Universal-Lite-x86_64.AppImage`)
   - `3) Intel iGPU / Yalnızca CPU / Low-End` (`GameOCR-Universal-Lite-x86_64.AppImage`)
   - `4) Çift Sürüm (Her İkisi Birden)` (`--gpu dual`)
4. **Derleyici Aracı:** `PyInstaller + AppImage` veya `Nuitka + AppImage`

## 4.3. Komut Satırı (CLI) Örnekleri

```bash
# Hem NVIDIA-GPU (~2.3 GB) hem Universal-Lite (~600 MB) tam bağımsız .AppImage paketlerini üret
./build.sh --de kde --display hybrid --gpu dual --compiler pyinstaller --bundle-mode full

# Yalnızca bu bilgisayarda hızlı test için yerel AppImage (~233 MB) üret
./build.sh --de kde --display hybrid --gpu nvidia --compiler pyinstaller --bundle-mode fast

# Otomatik Python 3.12 kuruculu Windows 10/11 paketini (.zip + .bat + .ps1) üret
./build.sh --platform windows --gpu nvidia --compiler pyinstaller

# Komutları çalıştırmadan doğrula (Dry-Run)
./build.sh --de kde --display wayland --gpu dual --compiler pyinstaller --dry-run
```

## 4.4. Windows 10/11 Otomatik Python 3.12 Kurulumu ve `.EXE` Derleme

`--platform windows` (veya menüden `5`) seçildiğinde `dist/gameocr-windows-win32-<gpu>/` klasörü ve `GameOCR-Windows-<gpu>.zip` arşivi oluşturulur.
Windows üzerinde `build-windows.bat` dosyasına çift tıklandığında:
1. Sistemde **Python 3.12** kurulu olup olmadığı (`py -3.12` veya `python 3.12.x`) otomatik denetlenir.
2. Kurulu değilse önce `winget install -e --id Python.Python.3.12` ile, `winget` yoksa resmi `python-3.12.8-amd64.exe` kurucusunu indirip sessiz modda (`/quiet PrependPath=1`) otomatik kurar.
3. `.venv` sanal ortamını oluşturur, bağımlılıkları yükler ve PE `RT_GROUP_ICON` (`gameocr.ico`) gömülü tek dosyalık `GameOCR-Universal-x64.exe` / `dist\GameOCR\GameOCR.exe` çıktısını üretir.

## 4.5. İkon Üretimi ve Linux `.desktop` Entegrasyonu

- **Çoklu Çözünürlüklü İkon Seti:** `tools/generate_icons.py` betiği `logo/` altındaki kaynak PNG dosyalarından `gameocr/assets/icons/` (`24..1024` PNG ve 5 katmanlı `gameocr.ico`) varlıklarını üretir; `./build.sh` bunları Linux AppImage içinde `.DirIcon` + Hicolor tema simgesi, Windows'ta ise `RT_GROUP_ICON` + `_MEIPASS` kaynağı olarak gömer.
- **Linux Uygulama Menüsü Kurulumu / Kaldırma:**
  ```bash
  ./packaging/linux/install-desktop.sh --exec /tam/yol/GameOCR-Universal-x86_64.AppImage
  ./packaging/linux/uninstall-desktop.sh
  ```

## 4.6. Otomatik Kütüphane İndirici (`ensure_build_prerequisites`) ve GitHub Yayınlama (`publish_github.sh`)

- **Otomatik Kütüphane ve Model İndirici:** Depoyu klonlayan bir kullanıcı `./build.sh` çalıştırdığında betik klasörde `.venv`, varsayılan ONNX OCR modelleri (`en_rec.onnx`, `latin_rec.onnx`), çevrimdışı `EN-TR` CTranslate2 modeli veya (`--gpu nvidia` seçildiğinde) `paddlepaddle-gpu==3.3.1` (CUDA 12.6) + `PP-OCRv5` ağırlıkları mevcut değilse bunları resmi sunuculardan otomatik olarak indirip kurar.
- **Tek Komutla GitHub Yayınlama ve Releases (`publish_github.sh`):**
  ```bash
  # Gizlilik ve dosya boyutu denetimi
  ./publish_github.sh --check-only

  # GitHub hesabında depoyu oluşturup kodu yayınla ve v0.3.0 Universal Release paketlerini yükle
  ./publish_github.sh --repo GameOCR --release v0.3.0
  ```
  NVIDIA'nın ikili dağıtım (redistribution) lisans kısıtlamalarından kaçınmak ve 4+ GB dosya yüklememek için GitHub Releases'a yalnızca telif/boyut dostu `GameOCR-Universal-x86_64.AppImage`, `GameOCR-Universal-x64.exe` ve `GameOCR-Windows-cpu.zip` paketleri yüklenir.

