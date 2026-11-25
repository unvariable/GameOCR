# GameOCR – Gerçek Zamanlı Oyun Altyazı OCR ve Çeviri Katmanı

**GameOCR**, Linux (KDE Plasma Wayland, GNOME, X11) ve Windows 10/11 masaüstlerinde tam ekran/çerçevesiz oyun oynarken altyazıları belirlenen alandan (**ROI**) gerçek zamanlı yakalayan, **Çift Motorlu OCR (RapidOCR ONNX-CPU / PaddleOCR CUDA GPU)** ile okuyan, **DeepL API** veya **Çevrimdışı (Lokal CTranslate2)** motorla çeviren ve çeviriyi orijinal altyazının tam koordinat, boyut ve rengine hizalı (`exact_alignment`), tıklama geçirgen ve buzlu cam (`blur-behind`) efektli bir HUD olarak yansıtan açık kaynaklı bir araçtır.

---

## 🌟 Öne Çıkan Özellikler

- **Dinamik Görsel Metin Hizalama (`exact_alignment`):**
  - Orijinal altyazının ROI içindeki koordinatlarını (`bbox_rel`), yazı tipi boyutunu (`line_height_px`), arka plan rengini (`bg_color_hex`) ve kelime bazlı vurgu renklerini (`word_colors`) örnekleyerek çeviriyi doğrudan orijinal metnin üzerine, aynı boyut ve renkte çizer.
  - Uzun çevirileri taşmadan sığdıran **Zero-Clip Auto-Fit** algoritması ve tek tıkla klasik ortalı panele dönüş desteği.
- **Çift Motorlu (Dual-Engine) OCR Mimarisi:**
  - **Ana Sürüm (`RapidOcrEngine` — ONNX Runtime CPU):** Ağır NVIDIA/CUDA kütüphanelerine ihtiyaç duymadan AMD, Intel ve düşük donanımlı sistemlerde ~20–25 ms içinde yüksek doğruluklu OCR çıkarımı yapar.
  - **Özel GPU Sürümü (`PaddleCudaEngine` — NVIDIA CUDA / TensorRT):** NVIDIA GPU bulunan sistemlerde CUDA 12.6 ve `%35` VRAM tavanıyla çalışır.
- **İndirilebilir Çok Dilli OCR Paketleri (`OcrModelManager`):**
  - Varsayılan olarak **İngilizce (`EN`)** ve **Latin / Türkçe & Avrupa Dilleri (`LATIN`: TR, DE, FR, ES, IT, PT, PL, NL, SV)** paketleri hazır gelir.
  - **Ayarlar → Algılama ve OCR** sekmesinden **Japonca (`JA`)**, **Korece (`KO`)**, **Çince (`ZH`)**, **Rusça / Kiril (`RU`/`UK`)**, **Arapça (`AR`)** ve **Yunanca (`EL`)** OCR tanıma paketleri arayüzü dondurmadan tek tıkla indirilebilir veya kaldırılabilir.
- **Çift Motorlu Çeviri (DeepL Bulut + Tamamen Çevrimdışı CTranslate2):**
  - **Hibrit (`auto_fallback`)**, **DeepL API** veya **Tamamen Çevrimdışı (`local`)** çalışma modları.
  - `CTranslate2` + `SentencePiece` (`int8`) tabanlı çevrimdışı motor herhangi bir API anahtarı veya internet bağlantısı olmadan 30–60 ms içinde çeviri yapar.
  - **Ayarlar → Çevirmen** sekmesinden ek çevrimdışı dil paketleri (`TR-EN`, `JA-TR`, `EN-DE`, `DE-TR`, `FR-TR`, `ES-TR`, `RU-TR`, `ZH-TR`, `KO-TR`, `IT-TR`) indirilebilir.
- **Daktilo (Typewriter) ve Öz-Yakalama (Self-Capture) Koruması:**
  - Harf harf akan diyaloglarda yazım tamamlanana (`settle_time`) kadar bekler; oyun arayüzü etiketlerini (`AUTO`, `SKIP`, `LOG`, `SPEAKING`) temizler ve overlay'in kendi çevirisini tekrar okumasını engeller.
- **Çoklu Masaüstü ve Platform Desteği:**
  - **Evrensel Kontrol Merkezi (`ControlWindow`) & Tek Örnek IPC:** Sistem tepsisi bulunmayan masaüstleri dahil tüm ortamlarda (`Ctrl+Alt+G` ile öne getirilen) kompakt kontrol penceresi ve ikinci açılışta mevcut pencereyi odaklayan tek-örnek IPC mekanizması.
  - **Çoklu Çözünürlüklü Marka Logosu & Masaüstü Entegrasyonu:** Linux'ta `.DirIcon` / Hicolor tema ikonu ve `packaging/linux/install-desktop.sh` uygulama menüsü kurulumu; Windows'ta PE `RT_GROUP_ICON` ve `AppUserModelID` görev çubuğu kimliği.
  - **Wayland:** `xdg-desktop-portal` ScreenCast + PipeWire (`restore_token` ile pencere seçimini hatırlar) ve KWin kompozitör kısayolları.
  - **X11:** `XComposite` doğrudan pencere pixmap yakalama, dinamik Pencere Seçici (`WindowPickerDialog`) ve `_KDE_NET_WM_BLUR_BEHIND_REGION` buzlu cam efekti.
  - **Windows 10/11 (Tam Sürüm):** `Win32Backend` (`PrintWindow` izole pencere yakalama, Z-order örtülme koruması, pencere-göreli ROI, birincil ekranda `DXcam` + `MSS` otomatik yedek), `WDA_EXCLUDEFROMCAPTURE` öz-yakalama koruması, standart şeffaf mod için `LWA_COLORKEY`, yüksek DPI & çoklu monitör desteği, DWM Blur ve `RegisterHotKey` (`MOD_NOREPEAT`).
- **Kalıcı SQLite LRU Önbelleği & Çeviri Geçmişi:**
  - Tekrarlayan veya `%90+` benzer replikleri `0 ms` gecikme ve `0 API kotası` ile anında yanıtlar; geçmiş penceresinden arama ve kopyalama imkanı sunar.

---

## 📦 Hazır Sürümler (Releases) ve Hızlı Kurulum

### Seçenek A: Hazır Paket ile Kurulumsuz Çalıştırma (Önerilen)
GitHub **Releases** sayfasından işletim sisteminize uygun evrensel paketi indirin:
- **Linux (`GameOCR-Universal-x86_64.AppImage`):**
  ```bash
  chmod +x GameOCR-Universal-x86_64.AppImage
  ./GameOCR-Universal-x86_64.AppImage
  ```
  *(Opsiyonel: Uygulama menüsüne ve simge temasına eklemek için `./packaging/linux/install-desktop.sh --exec /tam/yol/GameOCR-Universal-x86_64.AppImage` çalıştırabilirsiniz.)*
- **Windows 10/11 (`GameOCR-Universal-x64.exe` veya `GameOCR-Windows-cpu.zip`):**
  Doğrudan tek dosyalık `GameOCR-Universal-x64.exe` uygulamasını çalıştırın (veya kaynak/derleme arşivini çıkartıp `build-windows.bat` dosyasına çift tıklayarak Python 3.12 kurulumuyla yerel derleme yapın).

### Seçenek B: Kaynak Koddan Çalıştırma
```bash
# 1. Sanal ortamı ve bağımlılıkları kurun (Python 3.12)
uv sync

# 2. (Opsiyonel) DeepL API anahtarınızı tanımlayın (veya çevrimdışı modda doğrudan kullanın)
cp .env.example .env

# 3. Uygulamayı başlatın
uv run gameocr
```

---

## 🛠️ Kendi Paketini Derleme (`build.sh` — Otomatik Kütüphane İndiricili)

`build.sh` betiği, klasörde eksik olan büyük kütüphaneleri (ONNX modelleri, CTranslate2 ağırlıkları, AppImage runtime ve seçilmişse NVIDIA CUDA 12.6 `paddlepaddle-gpu` paketleri) resmi adreslerinden **otomatik olarak indirir**:

```bash
# İnteraktif derleme sihirbazını başlat
./build.sh

# Linux için telif/boyut dostu Universal (ONNX-CPU) AppImage üret
./build.sh --de kde --display hybrid --gpu cpu --compiler pyinstaller

# NVIDIA GPU (CUDA 12.6 + cuDNN) hızlandırmalı AppImage üret (eksik CUDA kütüphanelerini otomatik indirir)
./build.sh --de kde --display hybrid --gpu nvidia --compiler pyinstaller

# Windows 10/11 taşınabilir paketini üret
./build.sh --platform windows --gpu cpu --compiler pyinstaller
```

---

## 🚀 GitHub'da Tek Komutla Yayınlama ve Release Oluşturma (`publish_github.sh`)

Projeyi kendi GitHub hesabınızda yayınlamak ve sürüm (`Releases`) dosyalarını eklemek için `publish_github.sh` betiğini kullanabilirsiniz:

```bash
# 1. Yayınlama öncesi gizlilik, kişisel dizin yolu ve dosya boyutu denetimi yapın:
./publish_github.sh --check-only

# 2. Tek komutla GitHub hesabınızda depoyu oluşturup kaynak kodunu yayınlayın:
./publish_github.sh --repo GameOCR --visibility public

# 3. Kaynak kodunu yayınlayın VE derlenmiş Universal paketleri GitHub Releases'a yükleyin:
./publish_github.sh --repo GameOCR --release v0.3.0
```

> **Not:** `publish_github.sh --release v0.3.0` komutu, NVIDIA'nın ikili dağıtım kısıtlamalarına takılmamak ve 4+ GB yükleme yapmamak için yalnızca hafif ve açık lisanslı `GameOCR-Universal-x86_64.AppImage`, `GameOCR-Universal-x64.exe` ve `GameOCR-Windows-cpu.zip` dosyalarını (`SHA256SUMS.txt` ile birlikte) GitHub Releases'a yükler.

---

## ⌨️ Varsayılan Kısayollar

| Kısayol | İşlev | Açıklama |
|---|---|---|
| `Ctrl + Alt + P` | Duraklat / Devam Et | Yakalama ve OCR boru hattını geçici olarak durdurur veya devam ettirir. |
| `Ctrl + Alt + S` | Altyazı Alanı Seç | Tam ekran interaktif ROI (Region of Interest) seçiciyi açar. |
| `Ctrl + Alt + O` | Overlay Göster / Gizle | Altyazı katmanının görünürlüğünü açıp kapatır. |
| `Ctrl + Alt + H` | Çeviri Geçmişi | Çevrilen repliklerin arama ve kopyalama penceresini açar. |
| `Ctrl + Alt + G` | Kontrol Merkezi | Kontrol Merkezi penceresini öne getirir / açar. |

---

## 🧪 Testler

GameOCR kapsamlı otomatik birim testi paketine sahiptir. Tüm testleri çalıştırmak için:

```bash
uv run pytest -v
```

---

## 📚 Teknik Dokümantasyon

Ayrıntılı mimari ve platform belgelerine `docs/` dizininden ulaşabilirsiniz:
- **Türkçe Dokümantasyon:** [docs/tr/README.md](./docs/tr/README.md)
  - [Mimari ve Dinamik Görsel Metin Hizalama](./docs/tr/architecture.md)
  - [Wayland ve X11 Görüntü Sunucuları](./docs/tr/display_servers.md)
  - [Çevrimdışı Çeviri ve Çok Dilli OCR Paketleri](./docs/tr/local_translation.md)
  - [Derleme (`build.sh`) ve GitHub Yayınlama Kılavuzu](./docs/tr/building.md)
  - [Windows 10/11 Mimarisi ve Özellikleri](./docs/tr/windows_port.md)
- **English Documentation:** [docs/en/README.md](./docs/en/README.md)

---

## 📄 Lisans ve Üçüncü Parti Bildirimleri

- Bu proje **MIT Lisansı** ([LICENSE](./LICENSE)) altında lisanslanmıştır.
- Kullanılan açık kaynak kütüphaneler ve isteğe bağlı indirilen OCR/çeviri modelleri hakkında ayrıntılı telif ve lisans bilgileri için [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md) dosyasına bakın.
