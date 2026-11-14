# AGENTS.md — GameOCR Geliştirici ve Yapay Zeka Ajan Rehberi

Bu belge, GameOCR projesinde çalışan yapay zeka ajanları (ve insan katkıcılar) için mimari prensipleri, bileşen etkileşimlerini, kodlama kurallarını, devir-teslim (handoff) standartlarını ve geliştirme kurallarını tanımlar.

---

## 0. 🔴 EN YÜKSEK ÖNCELİKLİ ZORUNLU İŞ AKIŞI: Her İşlem Sonrası `PROGRESS.md` Güncellemesi

> [!CAUTION]
> **EN YÜKSEK ÖNCELİKLİ HEDEF:** Projede çalışan **her yapay zeka ajanı** için kök dizindeki `PROGRESS.md` dosyasını güncel tutmak **diğer tüm görevlerden daha yüksek önceliklidir**. Oturum veya token sınırı kesintilerinin hangi saniyede gerçekleşeceği bilinemeyeceğinden, `PROGRESS.md` **yalnızca aşama sonlarında değil, yapılan HER BİR İŞLEM (dosya düzenleme, hata düzeltme, derleme, komut çalıştırma veya test) sonrasında derhal** güncellenmek zorundadır.

### Devir-Teslim (Handoff) ve Atomik Durum Güncelleme Kuralları:
1. **Göreve Başlarken (İlk İşlem):** Herhangi bir kod değişikliği yapmadan önce kök dizindeki `PROGRESS.md` dosyasını okuyun ve üzerinde çalışacağınız adımı `PROGRESS.md` içinde `[~] Devam Ediyor` olarak işaretleyin.
2. **Her Bir İşlem Sonrasında (Zorunlu Atomik Güncelleme):**
   - Bir dosyada değişiklik yaptığınızda, bir hatayı düzelttiğinizde, bir derleme veya test komutu çalıştırdığınızda **sıradaki işleme geçmeden hemen önce** `PROGRESS.md` dosyasını güncelleyin.
   - Güncellemede: değiştirilen dosyayı, yapılan işlemi, alınan mimari kararı ve bir sonraki atomik adımı ("Aktif Bağlam" ve "Atomik İşlem Günlüğü" altında) kaydedin.
3. **Aşama Tamamlandığında:** İlgili aşamayı `[x] Tamamlandı` olarak işaretleyin ve son test çıktısını `PROGRESS.md` dosyasına işleyin.
4. **Kesinti Durumunda Devralma:** İşi devralan yeni bir ajan, kullanıcıya tekrar plan sormadan veya tamamlanmış adımları baştan yazmadan doğrudan `PROGRESS.md` içindeki "Aktif Bağlam (Sıradaki Adım)" ve "Atomik İşlem Günlüğü" bölümünden geliştirmeye devam etmelidir.

---

## 1. Proje Özeti ve Temel Felsefe

**GameOCR**, Linux masaüstlerinde (özellikle KDE Plasma Wayland ve X11) ve Windows sistemlerde (Beta) tam ekran oyun oynarken altyazıları gerçek zamanlı okuyup DeepL API veya Çevrimdışı (Lokal CTranslate2/Argos) motorla çeviren ve oyunun üzerine tıklanamaz (click-through), buzlu cam (blur-behind) efektli veya doğrudan orijinal metnin koordinat/boyut/rengine hizalı (`exact_alignment`) bir HUD olarak yansıtan bir araçtır.

### Temel Tasarım İlkeleri:
1. **Ultra Düşük Gecikme:** Kare yakalama, renk örnekleme ve OCR çıkarımı GPU hızlandırmasıyla 20-30 ms aralığında kalmalıdır.
2. **Sıfır Oyun Müdahalesi:** Overlay penceresi şeffaftır, fare tıklamalarını tamamen arkasındaki oyuna geçirir (`WindowTransparentForInput`) ve sistem odağını çalmaz.
3. **Dinamik Görsel Hizalama (Exact Alignment):** OCR'dan dönen sınır kutusu (bounding box) koordinatları, piksel satır yüksekliği ve Otsu + medyan tabanlı ön plan metin rengi kullanılarak çeviri doğrudan orijinal metnin üzerine, aynı boyut ve renkte çizilebilir; istenirse klasik ortalı panel moduna dönülebilir.
4. **Çift Motorlu Çeviri & Kota Dostu Akıllı Filtreleme:** Daktilo (typewriter) efektleri, ekran gürültüleri, yankı (echo) ve yinelenen replikler filtrelenir; SQLite önbelleği ile tekrarlar anında yakalanır. DeepL API yanında tamamen çevrimdışı çalışan CTranslate2/Argos Translate lokal modelleri desteklenir.
5. **Çoklu Masaüstü ve Platform Desteği:** Wayland (`xdg-desktop-portal` ScreenCast + PipeWire), X11 (`XComposite` pixmap + pencere seçici) ve Windows Beta (`SetWindowDisplayAffinity` + `DwmEnableBlurBehindWindow` + `MSS`/`DXcam`) otomatik olarak algılanır ve yönetilir.

---

## 2. Teknoloji Yığını ve Çalışma Ortamı

- **Python Sürümü:** `>=3.12, <3.13` *(PaddlePaddle GPU CUDA 12.6 ikili tekerlekleri Python 3.12 ile tam uyumludur).*
- **Paket Yöneticisi:** `uv` (`pyproject.toml`, `uv.lock`).
- **Grafik Arayüz:** `PyQt6` (Linux'ta XCB platform eklentisi zorunludur: `QT_QPA_PLATFORM=xcb`; Windows'ta yerel `windows` QPA kullanılır).
- **Derin Öğrenme & Çift Motorlu OCR:**
  - **Ana Sürüm (ONNX-CPU Lite):** `rapidocr-onnxruntime>=1.3`, `onnxruntime` (`CPUExecutionProvider`, ~20–25 ms CPU çıkarımı) ve `gameocr/ocr_models.py` (`OcrModelManager` ile çok dilli ONNX tanıma paketleri: `EN`, `LATIN`, `JA`, `KO`, `ZH`, `RU`, `AR`, `EL`).
  - **Özel GPU Sürümü (NVIDIA CUDA):** `paddlepaddle-gpu==3.3.1` (CUDA 12.6 özel indeksi) ve `paddleocr>=3.3`.
- **Görüntü İşleme & Renk Analizi:** `opencv-python-headless>=4.10`, `numpy`.
- **Dize Eşleştirme & Arama:** `rapidfuzz>=3.9`.
- **Çeviri (Bulut & Lokal):** `deepl>=1.18`, `ctranslate2>=4.0` ve `sentencepiece>=0.2` (`gameocr/local_models.py` ile çevrimdışı sinirsel makine çevirisi).
- **Düşük Seviyeli Sistem & IPC:** `python-xlib`, `dbus-fast`, `mss` (Windows'ta `ctypes.windll` DWM/User32 API'leri).
- **Kalıcı Depolama:** Python standart kütüphanesi `sqlite3` (WAL modu) ve `tomli-w` / `tomllib`.

---

## 3. Mimari ve Veri Akışı

Uygulama, GUI donmalarını önlemek amacıyla çok iş parçacıklı (multi-threaded) boru hattı mimarisi kullanır.

```mermaid
flowchart TD
    CaptureWorker["1. CaptureWorker<br/>(Portal / XComposite / MSS / Win32)"]
    ChangeGate["ChangeGate<br/>(Piksel Delta Kontrolü)"]
    OcrWorker["2. OcrWorker<br/>(PaddleOCR GPU + BBox & Renk Örnekleme)"]
    FilterWorker["3. FilterWorker<br/>(Daktilo / Yankı / Önbellek)"]
    CacheStore[("SQLite LRU Önbellek<br/>+ RapidFuzz İndeksi")]
    TranslatorWorker["4. TranslatorWorker<br/>(DeepL API / Lokal CTranslate2)"]
    UiQueue["ui_q (Queue[UiMessage + TextStyleMeta])"]
    MainThread["Qt Ana Thread<br/>(OverlayWindow / TrayManager / WindowPicker)"]

    CaptureWorker -->|frame_q: max 1| ChangeGate
    ChangeGate -->|processed + raw frame| OcrWorker
    OcrWorker -->|text_q: max 4 (OcrResult + TextStyleMeta)| FilterWorker
    FilterWorker <-->|Hızlı Arama| CacheStore
    FilterWorker -->|Önbellekte Var + TextStyleMeta| UiQueue
    FilterWorker -->|Yeni Metin / translate_q: max 8| TranslatorWorker
    TranslatorWorker -->|Kayıt Ekle| CacheStore
    TranslatorWorker -->|Çeviri Sonucu + TextStyleMeta| UiQueue
    UiQueue --> MainThread
```

### 3.1. Thread'ler ve Kuyruklar
- **CaptureWorker:** Hedef FPS'te (varsayılan 8.0) ekran/pencere karesini yakalar. `frame_q` (maxsize=1) kullanarak her zaman en güncel kareyi tutar; kuyruk doluysa eski kareyi düşürür (`_put_drop_oldest`).
- **OcrWorker:** `ChangeGate` ile piksel farkını ölçer. Görüntü durağansa OCR çalıştırmaz; durağanlık onaylandığında `is_stable=True` sinyali üretir. Aktif OCR sırasında `ocr_busy` bayrağını set eder. Metin tespit edildiğinde `TextStyleMeta` (normalize bounding box koordinatı, orijinal satır yüksekliği ve örneklenen metin HEX rengi) üretir.
- **FilterWorker:**
  - `TextFilter` motorunu yönetir.
  - Metin akarken (`_is_typing`) çeviri isteği atmaz.
  - `settle_time` (0.35s) dolduğunda veya `is_sentence_complete()` doğrulandığında tek bir çeviri görevi oluşturur ve son okunan `TextStyleMeta` bilgisini korur.
  - Kuyruk boşsa (`queue.Empty`) `check_pending(is_ocr_busy)` çağırarak zaman aşımına uğrayan metinleri çeviriye iletir.
- **TranslatorWorker:**
  - `_drain_superseded()` metodu ile kuyrukta birikmiş daktilo ara adımlarını eler, yalnızca son cümleyi aktif çeviri motoruna (DeepL veya Lokal Model) gönderir.
  - Çeviri başarılı olunca sonucu hem `CacheStore`'a yazar hem de `TextStyleMeta` ile birlikte `ui_q` üzerinden arayüze iletir.
  - `filter_control_q` üzerinden `FilterWorker`'a gösterilen çeviriyi bildirerek yankı korumasını senkronize eder.

---

## 4. Kritik Alt Sistemler ve Kodlama Kuralları

### 4.1. Qt GUI Thread Emniyeti
> [!IMPORTANT]
> Qt nesneleri ve UI bileşenleri (`OverlayWindow`, `TrayManager`, `SettingsDialog`, `HistoryDialog`, `WindowPickerDialog`) **YALNIZCA** ana iş parçacığında çalıştırılabilir.
- Arka plan worker'ları veya dil paketi indirme iş parçacıkları doğrudan UI metodlarını çağıramaz.
- Tüm haberleşme `ui_q` (`queue.Queue[UiMessage]`) veya `pyqtSignal` üzerinden yapılmalı ve ana thread'de tüketilmelidir.

### 4.2. Platform Seçimi (`QT_QPA_PLATFORM=xcb` ve Windows Desteği)
GameOCR, `gameocr/__main__.py` içerisinde Linux üzerinde çalışırken `os.environ.setdefault("QT_QPA_PLATFORM", "xcb")` tanımlar.
- **Neden:** Wayland altında standart Wayland platform eklentisi pencerelere mutlak ekran koordinatı verme, tıklama geçirgenliği (`WindowTransparentForInput`) ve KWin blur atomu yazma yeteneklerini kısıtlar.
- **Kural:** Linux üzerinde bu ortam değişkeni asla kaldırılmamalı; Windows (`sys.platform == "win32"`) üzerinde ise yerel `windows` platform eklentisinin çalışmasına izin verilmelidir.

### 4.3. Dinamik Görsel Metin Hizalama (`exact_alignment`)
- `OverlayConfig.exact_alignment = True` olduğunda çevrilen metin:
  1. `match_font_size = True` ise OCR bounding box yüksekliğinden (`line_height_px`) hesaplanan orijinal font boyutunda,
  2. `match_text_color = True` ise orijinal BGR kareden Otsu maskeleme + medyan ile örneklenen `text_color_hex` renginde,
  3. Doğrudan orijinal metnin ROI içindeki normalize `(x, y, w, h)` koordinatlarına yerleştirilir.
- Kullanıcı Ayarlar'dan `exact_alignment` seçeneğini kapattığında overlay anında klasik ortalı panel davranışına dönmelidir.

### 4.4. Blur-Behind Entegrasyonu (`gameocr.ui.blur`)
- **Linux (KWin):** `_KDE_NET_WM_BLUR_BEHIND_REGION` atomu Xlib `window.change_property` ile 32-bit `CARDINAL` formatında `[0, 0, width, height]` olarak yazılır.
- **Windows (DWM):** `ctypes.windll.dwmapi.DwmEnableBlurBehindWindow` / Acrylic API'si ile bulanıklık uygulanır.

### 4.5. Daktilo (Typewriter) ve Metin Filtresi Kuralları (`gameocr.text_filter`)
- Oyun arayüzü butonları (`AUTO`, `SKIP`, `LOG`, `SAVE`, `SPEAKING`) `clean_game_text()` fonksiyonu ile ayıklanmalıdır.
- Karşılaştırmalarda ve önbellek aramalarında `normalize()` kullanılarak noktalama işaretleri ve büyük/küçük harf farklılıkları elenmelidir.
- Cümle sonu noktalama işaretleri (`.`, `!`, `?`, `…`, `」` vb.) repliğin bittiğini gösterir ve bekleme süresini kısaltır.

### 4.6. Global Kısayollar (`gameocr.ui.hotkeys`)
- **Wayland:** KDE Plasma 6'da kompozitör düzeyinde kısayol kaydedilip yerel `UDP_PORT = 49281` soketine sinyal gönderilir.
- **X11:** `python-xlib` kullanılarak `root.grab_key` ile dinlenir. NumLock (`Mod2`), CapsLock (`Lock`) ve AltGr (`Mod5`) maskelerinin tüm kombinasyonları taranmalıdır (`_get_lock_combos`).
- **Windows:** `user32.RegisterHotKey` ile sistem genelinde dinlenir.

### 4.7. Uluslararasılaşma ve Dil Sistemi (`gameocr.i18n`)
- Tüm arayüz dizgileri `t("key")` fonksiyonu ile çağrılır.
- Varsayılan dil Türkçe'dir (`tr`). Eksik anahtarlar otomatik olarak Türkçe karşılığına düşer.
- Yeni arayüz metinleri eklendiğinde hem `tr` hem de `en` sözlüklerine karşılıkları eklenmelidir.

### 4.8. Atomik Yapılandırma Kaydı (`gameocr.config`)
- Ayarlar kaydedilirken doğrudan hedef dosyaya yazılmaz.
- Önce geçici dosyaya (`.tmp`) yazılır ve ardından `tmp.replace(path)` ile atomik olarak taşınır. Bu sayede ani kapanmalarda `config.toml` bozulmaz.

### 4.9. Gelişmiş Loglama ve Aşamalı Traceback (`gameocr.logging_utils`)
- `DEBUG` modunda çalışan kritik fonksiyonlar milisaniye (`ms`) cinsinden yürütme sürelerini loglamalıdır.
- Renk çıkarımı, koordinat hizalama ve çeviri gibi alt aşamalarda oluşan hatalar aşama bilgisini (`stage`) içeren `StageError` / `log_stage_exception` ile detaylı traceback olarak kaydedilmeli ve güvenli fallback uygulanmalıdır.

### 4.10. Çok Dilli OCR ve Çeviri Paketi Yöneticileri (`gameocr.ocr_models` & `gameocr.local_models`)
- **OCR Paketleri (`OcrModelManager`):** Varsayılan olarak `EN` ve `LATIN` paketleri kurulu gelir; diğer diller (`JA`, `KO`, `ZH`, `RU`, `AR`, `EL`) Ayarlar → Algılama ve OCR sekmesinden `OcrModelDownloadWorker(QThread)` ile arka planda indirilir ve `CTCLabelDecode` uyumu için sözlük satır sayısı modelin çıkış katmanıyla otomatik hizalanır.
- **Lokal Çeviri Paketleri (`LocalModelManager`):** Varsayılan olarak `EN-TR` paketi kurulu gelir; diğer çiftler (`TR-EN`, `JA-TR`, `DE-TR`, vb.) Ayarlar → Çevirmen sekmesinden `ModelDownloadWorker(QThread)` ile indirilir.

### 4.11. Gizlilik, Telif ve GitHub Yayınlama Kuralları (`publish_github.sh` & `build.sh`)
- Kaynak dosyalarda asla kişisel dizin yolu (`/home/<kullanici>`), `.env` dosyası veya gerçek `DEEPL_AUTH_KEY` bulunmamalıdır.
- Tescilli ve devasa NVIDIA CUDA / cuDNN ikili dosyaları Git deposuna veya GitHub Releases'a **dahil edilmez**; `build.sh` içindeki `ensure_build_prerequisites()` fonksiyonu eksik kütüphaneleri ve modelleri derleme anında resmi kaynaklardan otomatik indirir.
- GitHub'a yayınlama ve Release yükleme işlemleri `./publish_github.sh` üzerinden yürütülür.

---

## 5. Test ve Doğrulama Rehberi

Testler `tests/` dizini altında toplanmıştır.

### 5.1. Testleri Çalıştırma
```bash
# Tüm testleri ayrıntılı çalıştır
uv run pytest -v

# Belirli bir modülü test et
uv run pytest tests/test_text_filter.py -v
uv run pytest tests/test_visual_alignment.py -v
```

### 5.2. GUI ve Donanım Mocking İlkeleri
- Test ortamlarında fiziksel bir X11 ekranı veya GPU bulunmayabilir.
- Qt testlerinde `qapp` fixture'ı kullanılır ve `QT_QPA_PLATFORM=offscreen` ortamı varsayılır.
- PaddleOCR, DeepL API ve Lokal Model testlerinde gerçek ağ veya GPU çağrısı yapılmaz; sahte (synthetic) görüntüler veya mock nesneler kullanılır.
- Yeni bir özellik geliştirirken ilgili `tests/test_*.py` dosyasına mutlaka pozitif ve sınır (edge case) testleri ekleyin.

---

## 6. Geliştirici ve Ajan Kontrol Listesi (Checklist)

Yeni bir değişiklik veya hata düzeltmesi yaparken şu adımları takip edin:

1. [ ] **`PROGRESS.md` En Yüksek Öncelik Kontrolü:** İşe başlamadan önce `PROGRESS.md` okundu mu ve **yapılan her bir işlem / dosya değişikliği sonrasında** anında güncellendi mi?
2. [ ] **Tip İpuçları (Type Annotations):** Tüm fonksiyon ve metodlarda tam tip tanımları kullanılmalıdır (`from __future__ import annotations`).
3. [ ] **Docstring & Açıklamalar:** Kod içi açıklamalar ve docstring'ler Türkçe olmalı, mevcut mimari terimlerle uyumlu kalmalıdır.
4. [ ] **Thread Sınırları:** UI çağrılarının worker thread'lerine sızmadığından emin olun.
5. [ ] **Performans:** Döngü içinde disk G/Ç veya ağır CPU işlemi yapmayın; renk örneklemede vektörize numpy operasyonlarını ve önbellek aramalarında RapidFuzz bellek indeksini tercih edin.
6. [ ] **Test Doğrulaması:** Değişiklik sonrası `uv run pytest -v` çalıştırarak regresyon olmadığını doğrulayın.
