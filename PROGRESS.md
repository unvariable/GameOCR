# 📊 GameOCR Sürekli Durum Takip ve Devir-Teslim Belgesi (PROGRESS.md)

> **🔴 EN YÜKSEK ÖNCELİKLİ KURAL (Ajanlar İçin):**
> 1. Bu dosya, GameOCR projesinin geliştirme yaşam döngüsündeki **tek doğruluk kaynağıdır (Single Source of Truth)** ve projedeki **en yüksek öncelikli hedeftir**.
> 2. Projede çalışan her ajan, yalnızca büyük bir aşama bittiğinde değil, **yaptığı HER BİR İŞLEM (dosya düzenleme, hata düzeltme, betik güncelleme, derleme veya test) sonrasında derhal bu dosyayı güncellemek zorundadır**.
> 3. Herhangi bir oturum kesintisi, token limiti veya ajan değişimi durumunda projeyi devralan ajan **ilk olarak bu dosyayı okumalı**, son yapılan atomik işlemi doğrulamalı ve kaldığı yerden aynı mimari kararlarla devam etmelidir.

---

## 1. Genel Aşama Durum Tablosu

| Aşama | Başlık / İster | Durum | Test & Çıktı Durumu |
| :--- | :--- | :--- | :--- |
| **Aşama 0** | Sürekli Durum Takip Belgesi (`PROGRESS.md`), `AGENTS.md` ve Global Skill (`devir-teslim-is-akisi`) Güncellemesi | `[x] Tamamlandı` | Atomik işlem bazlı güncelleme kuralı eklendi |
| **Aşama 1** | Dinamik Görsel Metin Hizalama — Font Boyutu, Renk Örnekleme, Kelime Bazlı Çoklu Renk ve Otomatik Sığdırma | `[x] Tamamlandı` | `tests/test_visual_alignment.py` (`11 passed`) |
| **Aşama 2** | Çevrimdışı (Lokal) Çeviri Motoru (`EN-TR` & `TR-EN` CTranslate2) ve Dil Paketi İndirme Yöneticisi | `[x] Tamamlandı` | `tests/test_local_translator.py` (`7 passed`) |
| **Aşama 3** | Dinamik Pencere Seçimi Arayüzü — Wayland Portal / X11 Pencere Listesi | `[x] Tamamlandı` | `tests/test_window_picker.py` (`5 passed`) |
| **Aşama 4** | Gelişmiş Loglama, Milisaniye Telemetrisi ve Aşamalı Traceback | `[x] Tamamlandı` | `tests/test_logging_and_win32.py` + `test_stage_error_traceback_formatting` |
| **Aşama 5** | Akıllı ve İnteraktif Derleme Scripti (`build.sh` + `.AppImage`) | `[x] Tamamlandı` | `test_interactive_build_sh_wizard` (`PASSED`) |
| **Aşama 6** | Windows Portu — Beta Sürüm Altyapısı (`Win32Backend`, DWM Blur, `RegisterHotKey`) | `[x] Tamamlandı` | `tests/test_logging_and_win32.py` (`7 passed`) |
| **Aşama 7** | Kapsamlı TDD Birim Testleri | `[x] Tamamlandı` | Toplam **69 passed** (39 mevcut + 30 yeni birim testi) |
| **Aşama 8** | Çift Dilli Dokümantasyon (`docs/tr/` ve `docs/en/`) | `[x] Tamamlandı` | 12 belge (`docs/tr/*` ve `docs/en/*`) oluşturuldu |
| **Aşama 9** | Ayarlar'da GPU / CPU Hızlandırma Seçimi (`device`) ve Düşük Sistem (`low_end_mode`) Modu | `[x] Tamamlandı` | `test_ocr_device_cpu_gpu_selection_and_low_end_mode` (`PASSED`) |
| **Aşama 10** | Çift Sürüm (`NVIDIA-GPU` `4.1 GiB` ve `Universal-Lite` `952 MiB`) Tam Bağımsız `.AppImage` Paketleme | `[x] Tamamlandı` | `GameOCR-NVIDIA-GPU-x86_64.AppImage` & `GameOCR-Universal-Lite-x86_64.AppImage` üretildi |
| **Aşama 11** | Windows (Beta) Derleme Düzeltmesi ve Python 3.12 Otomatik Kurulum Betiği (`build-windows-beta.bat` / `.ps1`) | `[x] Tamamlandı` | `test_build_sh_windows_beta_auto_python312_and_dual_appimage` (`PASSED`) |
| **Aşama 12** | Aşama 9–11 Birim Testleri ve Dokümantasyon / `PROGRESS.md` Final Güncellemesi | `[x] Tamamlandı` | **69/69 test geçti** (`pytest -v`) |
| **Aşama 13** | AppImage Paketlerinin Teşhisi ve Düzeltilmesi (NVIDIA-GPU Açılmama & Universal-Lite Altyazı Çizmeme) | `[x] Tamamlandı` | Kök nedenler giderildi, 69/69 test geçti, çift AppImage doğrulandı |
| **Aşama 14** | Universal-Lite AppImage Bellek Doldurma ve Açılmama Sorununun Tespiti ve Giderilmesi | `[x] Tamamlandı` | Kök neden giderildi (text_det_limit_type="max"), 70/70 test geçti, canlı AppImage doğrulandı |
| **Aşama 15** | Çift Motorlu Mimari (Dual-Engine): `rapidocr-onnxruntime` (Lite/Universal CPU) & `PaddleOCR` (NVIDIA/CUDA) Fabrika Deseni ve `build.sh` Revizyonu | `[x] Tamamlandı` | **72/72 test geçti** (`pytest -v`, 5.24s) |
| **Aşama 16** | Windows (Beta) Sanal Makine Hatalarının Giderilmesi ve Tek Dosya (`--onefile`) `GameOCR-Universal-x64.exe` Paketlemesi | `[x] Tamamlandı` | **73/73 test geçti** (`pytest -v`, 7.75s) |
| **Aşama 17** | Windows & RapidOCR Metin Algılama Kalitesi (Kelime Birleşmesi, Ön İşleme, İngilizce/Latin ONNX Modeli ve Self-Capture Geri Besleme Döngüsü) İyileştirmesi | `[x] Tamamlandı` | **74/74 test geçti** (`pytest -v`, 7.11s) |
| **Aşama 18** | Farklı Dillerde OCR Paketi İndirme Yöneticisi (`OcrModelManager` + Ayarlar Arayüzü + Dinamik ONNX/Paddle Model Yükleme) | `[x] Tamamlandı` | **78/78 test geçti** (`pytest -v`, 7.84s) |
| **Aşama 19** | GitHub Tek Komut Yayınlama Betiği (`publish_github.sh`), Gizlilik/Telif Temizliği (`LICENSE`, `THIRD_PARTY_NOTICES.md`, `.gitignore`), `build.sh` Otomatik Kütüphane İndirici ve Dokümantasyon Güncellemesi | `[x] Tamamlandı` | **79/79 test geçti** (`pytest -v`, 7.66s) |
| **Aşama 20** | Linux Mint / Temiz Sistem AppImage `xcb` (`libxcb-cursor.so.0` + `cv2/qt` Çakışması) Düzeltmesi ve VM Üzerinde Sıfır Kurulum Doğrulaması | `[x] Tamamlandı` | `79/79` birim testi (`6.91s`) + Linux Mint VM (`192.168.221.129`) üzerinde sıfır kurulumla `DISPLAY=:0` canlı doğrulama |
| **Aşama 21** | Evrensel Arayüz Erişimi (`ControlWindow` + Tek Örnek IPC + `show_panel` Kısayolu) ve Popüler Masaüstleri (Cinnamon/GNOME/XFCE/KDE) İçin Sistem Tepsisi İkon/Tema Düzeltmesi | `[x] Tamamlandı` | **82/82** birim testi (`8.28s`) + Cinnamon VM'de `ControlWindow`, `IconName="gameocr"` ve Tek Örnek IPC (`SECOND_EXIT:0`) doğrulandı |
| **Aşama 22** | Windows Sürümü OCR Doğruluğu, Self-Capture / Tutarlılık ve Performans Sorunlarının Analizi ve Düzeltilmesi | `[x] Tamamlandı` | **83/83** birim testi (`6.49s`) + Windows VM'de `diff=0.000` (sıfır self-capture), `ocr_ms=88.4 ms` ve `GameOCR-Universal-x64.exe` derlemesi doğrulandı |
| **Aşama 23** | Sürüm Analizi, Gizlilik Kontrolü, Linux/Windows Derleme ve GitHub Release Yayınlama | `[x] Tamamlandı` | `v0.2.0` (`pyproject.toml`, `gameocr/__init__.py`, `CHANGELOG.md`), `./publish_github.sh --check-only` temiz, `GameOCR-Universal-x86_64.AppImage` (`824M`) & `GameOCR-Universal-x64.exe` (`545M`) doğrulandı |
| **Aşama 22** | Windows Sürümü OCR Doğruluğu, Self-Capture / Tutarlılık ve Performans Sorunlarının Analizi ve Düzeltilmesi | `[x] Tamamlandı` | **83/83** birim testi (`6.49s`) + Windows VM'de `diff=0.000` (sıfır self-capture), `ocr_ms=88.4 ms` ve `GameOCR-Universal-x64.exe` derlemesi doğrulandı |
| **Aşama 23** | Sürüm Analizi, Gizlilik Kontrolü, Linux/Windows Derleme ve GitHub Release Yayınlama | `[x] Tamamlandı` | `v0.2.0` (`pyproject.toml`, `gameocr/__init__.py`, `CHANGELOG.md`), `./publish_github.sh --check-only` temiz, `GameOCR-Universal-x86_64.AppImage` (`824M`) & `GameOCR-Universal-x64.exe` (`545M`) doğrulandı |

---

## 2. Alınan Kritik Mimari Kararlar

1. **Veri Akışında Görsel Metaveri (`TextStyleMeta`):**
   - Dinamik metin hizalaması için `gameocr/messages.py` içerisine `TextStyleMeta(bbox_rel, line_height_px, text_color_hex, bg_color_hex, word_colors, raw_boxes)` dataclass'ı eklendi.
   - `bbox_rel`, ROI karesi içindeki `(x_rel, y_rel, w_rel, h_rel)` değerlerini `0.0..1.0` aralığında normalize tutar.
2. **Hızlı Numpy/OpenCV Metin/Arka Plan Rengi Örnekleme ve Çok Renkli Kelime Eşleme (`extract_text_color`, `extract_background_color`, `extract_word_level_colors`):**
   - `OcrEngine.recognize_with_meta` metoduna hem `processed` hem de `raw_img` verilir.
   - Arka plan rengi (`bg_color_hex`) kutu kenar piksellerinin medyanından örneklenir ve orijinal metni tamamen kapatmak için `>= 0.96` opaklıkla çizilir.
   - Baskın metin renginden (`>= 42` RGB mesafesi) ayrılan renkli kelimeler (`word_colors`) tespit edilir, `map_word_colors_to_translation()` ile çevrilen cümledeki karşılıklarına eşlenir ve `QTextDocument` (`_draw_rich_multicolor_text`) ile renkli çizilir.
3. **Tam Hizalama (`exact_alignment`), Otomatik Sığdırma (Zero-Clip Auto-Fit) ve Geri Dönüş Mimarisi:**
   - `OverlayWindow.compute_render_layout` metodu `exact_alignment=True` iken metni doğrudan `bbox_rel` koordinatlarına yerleştirir; çeviri metni kutuya sığmazsa önce ROI sınırları içinde kutuyu genişletir, hâlâ taşarsa `font_px` değerini metin tam sığana kadar kademeli küçültür.
4. **Çevrimdışı (Lokal) Çeviri Motoru (`gameocr/local_models.py`) ve Başlangıç Koruması:**
   - Resmi Argos OpenTech CTranslate2 + SentencePiece (`translate-en_tr-1_5` ve `translate-tr_en-1_5`) ağırlıkları (`~/.local/share/gameocr/models/` veya `GAMEOCR_BUNDLED_MODELS_DIR`) doğrudan `_CTranslate2ModelRunner` ile çalıştırılır.
   - `gameocr/languages.py` içinde Türkçe (`TR`) kaynak dil karşılığı PaddleOCR 3.3 uyumlu `"tr"` (`latin_PP-OCRv5_mobile_rec`) olarak düzeltildi; `OcrEngine._load_model` içine güvenli `"en"` ve `"cpu"` fallback eklendi.
5. **KDE Görev Çubuğu (Taskbar) Sekme Gizleme:**
   - `gameocr/ui/hotkeys.py` içindeki `.desktop` kısayol şablonlarına `StartupNotify=false` ve `X-KDE-StartupNotify=false` eklendi; `gameocr/ui/overlay.py` içinde `_NET_WM_STATE_SKIP_TASKBAR` ve `_NET_WM_STATE_SKIP_PAGER` atomları X11 EWMH `ClientMessage` ile zorunlu kılındı.
6. **Donanım Hızlandırma Seçimi (`device`) ve Düşük Sistem (`low_end_mode`) Modu:**
   - `OcrConfig` içerisine `device = "auto" | "gpu" | "cpu"` ve `low_end_mode = False` eklendi. `GAMEOCR_FORCE_CPU=1` ortam değişkeni tanımlıysa (Universal-Lite AppImage) her zaman `"cpu"` döner.
   - `low_end_mode = True` iken `CaptureWorker` FPS'i `<= 5.0`, `OcrWorker` ölçeklemeyi `<= 1.5x` ve `OcrEngine` algılama sınırını `640px` ile sınırlar.
7. **Çift Sürüm Tam Bağımsız `.AppImage` (`build.sh`) ve Otomatik Python 3.12 Kuruculu Windows Beta Paketi:**
   - `build.sh` varsayılan `--bundle-mode full` modunda taşınabilir Python 3.12 (`sys.base_prefix`), tüm `site-packages`, `~/.paddlex/official_models`, `~/.local/share/gameocr/models` ve resmi AppImage Type-2 statik FUSE runtime (`build/runtime-x86_64`) bileşenlerini SquashFS içerisine gömer:
     - `GameOCR-NVIDIA-GPU-x86_64.AppImage` (`4.1 GiB`): CUDA 12.6 + cuDNN + GPU PaddleOCR gömülü.
     - `GameOCR-Universal-Lite-x86_64.AppImage` (`952 MiB`): `build/cpu_paddle_pkg` içindeki saf CPU `paddlepaddle==3.3.1` gömülü, ağır CUDA kütüphaneleri hariç.
   - Windows Beta (`--platform windows`) seçildiğinde `dist/gameocr-windows-win32-<gpu>/` ve `GameOCR-Windows-Beta-<gpu>.zip` üretilir; içindeki `build-windows-beta.bat` ve `setup-windows-beta.ps1` Windows'ta Python 3.12 kurulu değilse `winget` veya resmi `python-3.12.8-amd64.exe` kurucusuyla Python 3.12'yi otomatik kurup `GameOCR.exe` derler.
8. **AppImage Hata Düzeltmeleri ve Otomatik Fallback Mimarisi (Aşama 13):**
   - NVIDIA paketinde `libcinnapi.so` korunarak `libpaddle.so` bağımlılık çöküşü önlendi.
   - `PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT=False` ortam değişkeni eklenerek CPU `paddlepaddle==3.3.1` paketindeki OneDNN PIR instruction `NotImplementedError` hatası ortadan kaldırıldı.
   - Varsayılan `translation_engine` `"auto_fallback"` yapıldı; böylece kullanıcı DeepL anahtarı girmemiş olsa dahi paket içindeki çevrimdışı yerel model devreye girerek altyazıların anında ekrana çizilmesi sağlandı.

9. **PaddleX CPU Bellek Patlaması Koruması (`text_det_limit_type="max"` & Erken Boşaltma):**
   - PaddleX 3.x OCR tespit modelinde (`PP-OCRv5_server_det`) `text_det_limit_type` varsayılan olarak `"min"` modunda çalıştığından, altyazı ve geniş oyun pencerelerinde kısa kenar (örn. 60-100px) `det_limit_side_len`'e (960px veya 640px) ulaşana kadar görüntü 10x-15x oranda büyütülüyor ve genişlik 20,000+ piksele çıkıyordu. Bu durum CPU modunda her çıkarımda tek bir tensör için 4.77 GiB allocation istemesine ve 12+ GiB RAM tüketerek sistemin kilitlenmesine sebep oluyordu.
   - `OcrConfig.det_limit_type = "max"` yapılandırması ve `_create_paddle_ocr` içerisine `text_det_limit_type="max"` parametresi eklenerek tensör boyutları sınırlandı, bellek kullanımı 12.2 GB'tan 760 MB seviyesine indirildi ve çıkarım süresi 0.44 - 0.67 saniyeye düşürüldü.
   - `GAMEOCR_FORCE_CPU == "1"` tanımlı olduğunda `det_limit_side_len` otomatik olarak 640px ile sınırlandırılarak CPU çıkarımı 2 kat hızlandırıldı.
   - `FLAGS_allocator_strategy=auto_growth`, `FLAGS_eager_delete_tensor_gb=0.0` ve `FLAGS_fast_eager_deletion_mode=1` ile geçici evrişim tensörlerinin anında serbest bırakılması sağlandı.
10. **Çift Motorlu (Dual-Engine) OCR Mimarisi (`BaseOcrEngine` ABC + `RapidOcrEngine` + `PaddleCudaEngine` + `OcrEngineFactory`):**
   - Ana Sürüm (`GameOCR-Universal-x86_64.AppImage`) `rapidocr-onnxruntime` (`CPUExecutionProvider`) üzerine kuruldu; `use_cls=False`, `det_score_mode='fast'`, `det_limit_type='max'` ve `intra_op_num_threads` optimizasyonlarıyla CPU çıkarımı ~23 ms seviyesine çekildi.
   - Özel GPU Sürümü (`GameOCR_nvidia-x86_64.AppImage`, `--gpu nvidia`) `PaddleCudaEngine` ile CUDA 12.6, VRAM `auto_growth` (`%35` limit) ve opsiyonel TensorRT FP16 desteğiyle korundu.
   - Her iki motor da `BaseOcrEngine` soyut temel sınıfından türetilerek `compute_style_meta` (`exact_alignment`), 4 iş parçacıklı boru hattı ve Wayland/X11/KWin entegrasyonları %100 izole şekilde korundu.

---

## 3. Atomik İşlem Günlüğü (Son Yapılan Değişiklikler)

1. **`[Tamamlandı]`** `gameocr/config.py`, `config.default.toml`, `gameocr/i18n.py`, `gameocr/ui/settings_dialog.py`: `device` (`auto`/`gpu`/`cpu`) ve `low_end_mode` yapılandırma alanları ile Ayarlar arayüzü kontrolleri eklendi.
2. **`[Tamamlandı]`** `gameocr/ocr_engine.py`, `gameocr/workers.py`: `resolve_paddle_device()`, `OcrEngine.update_config()` ve `low_end_mode` FPS/ölçek/algılama boyutu sınırlandırmaları eklendi.
3. **`[Tamamlandı]`** `gameocr/local_models.py`: AppImage içine gömülü çeviri modellerini bulan `GAMEOCR_BUNDLED_MODELS_DIR` ortam değişkeni desteği eklendi.
4. **`[Tamamlandı]`** `build/runtime-x86_64` & `build/cpu_paddle_pkg`: Resmi AppImage Type-2 statik FUSE runtime ve CPU-only `paddlepaddle==3.3.1` paketi indirildi.
5. **`[Tamamlandı]`** `build.sh`: `--bundle-mode <full|fast>`, `--gpu dual`, tam bağımsız `GameOCR-NVIDIA-GPU-x86_64.AppImage` (`4.1 GiB`), `GameOCR-Universal-Lite-x86_64.AppImage` (`952 MiB`) ve otomatik Python 3.12 kuruculu Windows Beta (`build-windows-beta.bat` / `setup-windows-beta.ps1`) üretimi tamamlandı.
6. **`[Tamamlandı]`** `tests/test_logging_and_win32.py`, `docs/tr/building.md`, `docs/en/building.md`: Yeni birim testleri ve dokümantasyon güncellemeleri tamamlandı.
7. **`[Tamamlandı]`** `PROGRESS.md`, `AGENTS.md` ve `~/.gemini/config/skills/devir-teslim-is-akisi/SKILL.md`: `PROGRESS.md` dosyasının yalnızca aşama sonlarında değil, **yapılan her bir işlem sonrasında en yüksek öncelikle güncellenmesi** kuralı hem proje rehberine hem de global skill'e işlendi.
8. **`[Tamamlandı]`** **Aşama 13 Düzeltmeleri:** NVIDIA `libcinnapi.so` korunarak `libpaddle.so` bağımlılık çöküşü giderildi; `PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT=False` ve varsayılan `"auto_fallback"` motoru eklendi.
9. **`[Tamamlandı]`** **Aşama 14 Kök Neden Teşhisi (Universal-Lite Bellek Tüketimi):**
   - Universal-Lite CPU `paddlepaddle==3.3.1` ile `self._ocr.predict(img)` çalıştırıldığında `static_infer.py` -> `self.predictor.run()` adımında Paddle CPU tahsisatçısı (`cpu_allocator.cc:44`) tek bir işlemde **4,777,574,400 bayt (~4.77 GiB)** bellek tahsis etmeye çalışıyor (`ResourceExhaustedError: Fail to alloc memory of 4777574400 size`).
   - Kök neden belirlendi: PaddleX OCR boru hattında `text_det_limit_type` parametresi belirtilmediğinde varsayılan olarak `"min"` moduna geçmektedir. İnce uzun oyun altyazılarında kısa kenar (örn. 60-100px) `limit_side_len`'e (960px) ölçeklenmek için 10x-15x oranda büyütülmekte, genişlik 20,000+ piksele fırlamakta ve evrişim aktivasyon katmanları için gigabaytlarca bellek tüketilerek tüm RAM ve takas (swap) dolmaktadır.
   - `text_det_limit_type="max"` ayarlandığında tepe bellek kullanımı **12.2 GB'tan 760 MB'a** düşmekte, çıkarım süresi dakikalar yerine **0.44 - 0.67 saniyeye** inmektedir.
10. **`[Tamamlandı]`** `gameocr/config.py`, `config.default.toml` & `~/.config/gameocr/config.toml`: `OcrConfig` sınıfına ve yapılandırma dosyalarına `det_limit_type: str = "max"` alanı eklendi.
11. **`[Tamamlandı]`** `gameocr/ocr_engine.py`:
    - `_create_paddle_ocr()` içerisine `text_det_limit_type=limit_type` (varsayılan: `"max"`) ve `det_limit_type` fallback zinciri eklendi.
    - `_effective_det_limit()` metoduna `GAMEOCR_FORCE_CPU == "1"` kontrolü eklenerek Universal-Lite sürümünde otomatik 640px algılama sınırı uygulandı.
12. **`[Tamamlandı]`** `gameocr/__main__.py` & `build.sh`:
    - `FLAGS_allocator_strategy=auto_growth`, `FLAGS_eager_delete_tensor_gb=0.0` ve `FLAGS_fast_eager_deletion_mode=1` ortam değişkenleri eklendi.
13. **`[Tamamlandı]`** `tests/test_ocr_engine.py`: `test_ocr_limit_type_max_prevents_memory_explosion` birim testi eklendi; `pytest -v` ile **70/70 test başarıyla geçti**.
14. **`[Tamamlandı]`** `./build.sh --gpu dual`: Hem `GameOCR-Universal-Lite-x86_64.AppImage` (952M) hem de `GameOCR-NVIDIA-GPU-x86_64.AppImage` (4.1G) sıfırdan derlendi. Universal-Lite paketi canlı çalıştırılarak başlatma, bellek stabilitesi ve temiz kapanma doğrulandı.
15. **`[Tamamlandı]`** **Aşama 15 Mimari Planlama (Dual-Engine Architecture):** `rapidocr-onnxruntime` (CPUExecutionProvider / Lite) ve `PaddleOCR` (CUDA / TensorRT / NVIDIA) çift motorlu mimarisi, `BaseOcrEngine` ABC arayüzü, `OcrEngineFactory` fabrika deseni ve `build.sh` (`GameOCR-Universal-x86_64.AppImage` & `GameOCR_nvidia-x86_64.AppImage`) revizyon planı onaylandı.
16. **`[Tamamlandı]`** **Adım 1 (`pyproject.toml`):** `rapidocr-onnxruntime>=1.3` (`1.4.4`) ve `onnxruntime` (`1.31.1`) bağımlılıkları `pyproject.toml` dosyasına ve `.venv` ortamına eklendi.
17. **`[Tamamlandı]`** **Adım 2 (`gameocr/config.py` & `config.default.toml`):** `OcrConfig` içerisine `engine`, `cpu_threads`, `enable_tensorrt` ve `resolved_engine()` metodu eklendi.
18. **`[Tamamlandı]`** **Adım 3.1 (`gameocr/ocr_engine.py`):** `BaseOcrEngine` (ABC), `RapidOcrEngine` (`CPUExecutionProvider` + `use_cls=False` + `intra_op_num_threads` + `det_limit_type='max'`), `PaddleCudaEngine` (`CUDA` + VRAM `auto_growth` + TensorRT FP16 opsiyonu), `OcrEngineFactory` ve birleşik `OcrEngine` sınıfları uygulandı; `timed_stage` ve `[OCR: ONNX-CPU]` / `[OCR: CUDA]` log telemetrisi entegre edildi.
19. **`[Tamamlandı]`** **Adım 3.2 (`gameocr/workers.py` & `gameocr/pipeline.py`):** `OcrWorker` ve `Pipeline` içine `BaseOcrEngine` polimorfik tip desteği ve `[OCR: ONNX-CPU]` / `[OCR: CUDA]` milisaniye log etiketlemesi eklendi.
20. **`[Tamamlandı]`** **Adım 4 (`build.sh`):** Varsayılan çıktı ONNX/CPU (`rapidocr-onnxruntime`) tabanlı `GameOCR-Universal-x86_64.AppImage` ve `--gpu nvidia` çıktısı CUDA (`PaddleOCR`) tabanlı `GameOCR_nvidia-x86_64.AppImage` olacak şekilde güncellendi; Universal sürümünden ağır CUDA/Paddle paketleri arındırıldı.
21. **`[Tamamlandı]`** **Adım 5 (`tests/test_ocr_engine.py` & `tests/test_logging_and_win32.py`):** Dual-Engine fabrika geçişlerini (`test_dual_engine_factory_selection_and_rapidocr_polygon_parsing`) ve `build.sh` paket hedeflerini (`test_build_sh_universal_and_nvidia_appimage_targets`) doğrulayan Pytest senaryoları eklendi.
22. **`[Tamamlandı]`** **Adım 6 (`pytest -v`):** `RapidOCR` örneğine geriye dönük `predict` kancası eklendi ve tüm test paketi çalıştırıldı: **72/72 birim testi 5.24 saniyede başarıyla geçti**.
23. **`[Tamamlandı]`** **Aşama 16.1 (`gameocr/local_models.py`, `gameocr/ui/roi_selector.py`, `gameocr/capture/win32_backend.py`, `gameocr/workers.py`):**
    - `local_models.py`: PyInstaller `--onefile` (`_MEIPASS/models`) ve `--onedir` (`sys.executable` dizini) model arama yolları eklendi.
    - `roi_selector.py`: Windows üzerinde `RoiSelectorWindow` penceresine yanlışlıkla `WS_EX_TRANSPARENT` (tıklama geçirgenliği) verilmesi ve `showFullScreen()` DWM siyah ekran hatası engellendi.
    - `win32_backend.py` & `workers.py`: VMware sanal ekran kartında `dxcam` siyah kare (`max == 0`) döndürdüğünde otomatik `mss` (GDI) yedeğine geçiş ve `window_id` / `win32_hwnd` ataması düzeltildi.
24. **`[Tamamlandı]`** **Aşama 16.2 (`build.sh` Windows Tek Dosya `--onefile` ve ASCII Encoding Düzeltmesi):**
    - `setup-windows-beta.ps1` ve `build-windows-beta.bat` içerisindeki UTF-8 em-dash (`—`) ve tırnak içi `&` karakterleri saf ASCII ile değiştirilerek Windows PowerShell 5.1 `ParserError: AmpersandNotAllowed` hatası giderildi.
    - Windows CPU/Lite derlemesi `rapidocr-onnxruntime` + `onnxruntime` tabanlı tek dosya (`--onefile`) `GameOCR-Universal-x64.exe` üretecek ve gömülü `models/` (`--add-data "models;models"`) ağırlıklarını içerecek şekilde güncellendi.
    - NVIDIA derlemesine `--collect-all paddlex` ve `--collect-all paddleocr` eklenerek `Exception: The pipeline (OCR) does not exist!` çalışma zamanı hatası giderildi.
25. **`[Tamamlandı]`** **Aşama 16.3 (`build.sh --platform windows` Paket Üretimi):** `GameOCR-Windows-Beta-cpu.zip` ve `GameOCR-Windows-Beta-nvidia.zip` tek dosya (`--onefile`) `GameOCR-Universal-x64.exe` üretecek şekilde yeniden oluşturuldu.
26. **`[Tamamlandı]`** **Aşama 16.4 (Wine İptali ve Temizliği):** Sistemdeki Wine ilk kurulum (`~/.wine` yapılandırma penceresi) adımında takıldığı için `wineserver -k` ile anında sonlandırıldı ve geçici dosyalar temizlendi; tek dosya `GameOCR-Universal-x64.exe` üretimi doğrudan `GameOCR-Windows-Beta-cpu.zip` içindeki `build-windows-beta.bat` üzerinden Windows VM'de çalışacak şekilde doğrulandı.
27. **`[Tamamlandı]`** **Aşama 16.5 (`tests/test_logging_and_win32.py`):** `test_windows_single_exe_ascii_scripts_and_meipass_models` içinde `LocalModelManager._find_ct2_bundle("EN-TR")` çağrısı güncellendi.
28. **`[Tamamlandı]`** **Aşama 16.6 (`pytest -v` Tüm Test Paketinin Çalıştırılması):** Tüm **73/73** birim testi (`7.75s`) başarıyla geçti.
29. **`[Tamamlandı]`** **Aşama 17.1 (Metin Algılama ve Öz-Yakalama [Self-Capture] Kök Neden Teşhisi):**
    - **Kök Neden 1 (`preprocess` Otsu + Denoise Yıkımı):** Varsayılan `PreprocessConfig(mode="otsu", denoise=True)` global Otsu eşiklemesi ve `medianBlur(3)` uyguladığından, içinde portre/gradyan bulunan alıntı kartlarında ve oyun sahnelerinde harfleri tamamen silmekte (`Card 4 -> ""`, `Card 1 -> "D+ yo tt hat"`). Modern derin öğrenme OCR motorları (`PP-OCRv4/v5` / `RapidOCR`) doğrudan renkli/gri (binarize edilmemiş) görüntü üzerinde eğitilmiştir.
    - **Kök Neden 2 (`RapidOCR` Varsayılan Çince `ch_PP-OCRv4_rec` Modeli):** `rapidocr_onnxruntime` varsayılan olarak Çince (`ch_PP-OCRv4_rec_infer.onnx`) tanıma modeliyle geldiği için İngilizce kelimeler arasındaki boşlukları yutmakta (`WHATEVERISDONEFOR`, `FriedrichNietzsche`) ve Latin harflerini karıştırmaktadır.
    - **Kök Neden 3 (Windows `Win32Backend` Öz-Yakalama [Self-Capture] Geri Besleme Döngüsü):** Windows'ta `OverlayWindow` gösterildiğinde (`showEvent`/`fade_in`) `SetWindowLongW` çağrısı DWM özelliklerini sıfırlamakta ve VMware sanal ekran kartında `mss` (`BitBlt`) overlay penceresini kendi karesinin içine yakalayarak sonsuz çeviri döngüsü (`FriedrichNietzscheBuNev...`) oluşturmaktadır.
30. **`[Tamamlandı]`** **Aşama 17.2 (Çözüm Planlaması ve Kullanıcı Onayı):** Teşhis edilen 3 kök neden için çözüm mimarisi kullanıcı tarafından onaylandı.
31. **`[Tamamlandı]`** **Aşama 17.3 (Adım 1 — `config.default.toml` & `gameocr/preprocess.py`):** `config.default.toml` içindeki `mode = "otsu"` ve `denoise = true` değerleri doğal görüntü (`mode = "none"`, `denoise = false`) olarak güncellendi; `upscale()` içindeki `max_h` sınırı `450` pikselden `1080` piksele çıkarılarak çok satırlı metin kutularının da `2.0x` netleştirilmesi sağlandı.
32. **`[Tamamlandı]`** **Aşama 17.4 (Adım 2.1 — İngilizce/Latin ONNX Tanıma Modellerinin İndirilmesi ve Karşılaştırılması):** `models/onnx/en_rec.onnx` (`en_dict.txt`) ve `models/onnx/latin_rec.onnx` (`latin_dict.txt`) indirildi; Nietzsche ekran görüntüsü üzerinde test edildiğinde kelime birleşmelerinin (`WHATEVERISDONEFOR` -> `WHATEVER IS DONE FOR`, `PEOPLEARE` -> `PEOPLE ARE`) ve Otsu harf kayıplarının tamamen ortadan kalktığı doğrulandı.
33. **`[Tamamlandı]`** **Aşama 17.5 (Adım 2.2 — `gameocr/ocr_engine.py` İçinde `RapidOcrEngine` İngilizce/Latin ONNX Entegrasyonu):** `RapidOcrEngine._find_bundled_onnx_rec_model()` eklendi; `en` ve `latin`/`tr` kaynak dillerinde Çince varsayılan model yerine `models/onnx/en_rec.onnx` veya `latin_rec.onnx` (`det_unclip_ratio=1.8`) otomatik yükleniyor.
34. **`[Tamamlandı]`** **Aşama 17.6 (Adım 3 — Windows Öz-Yakalama [Self-Capture] ve Geri Besleme Koruması: `gameocr/ui/overlay.py` & `gameocr/text_filter.py`):**
    - `set_win32_topmost_clickthrough()` içine `SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)` yenilemesi eklendi.
    - `clean_game_text()` içerisine küçük resim çözünürlük etiketi (`800×500`, `2240 x 1260`) temizliği ve `TextFilter` içerisine `_is_self_capture_echo()` (overlay çevirisi orijinal metinle karıştığında geri beslemeyi kesen koruma) eklendi.
35. **`[Tamamlandı]`** **Aşama 17.7 (`gameocr/config.py` & `build.sh` Güncellemesi):**
    - `load_config()` içine eski `config.toml` dosyalarındaki `(mode='otsu', denoise=True)` kombinasyonunu otomatik olarak `(mode='none', denoise=False)` moduna yükselten göç (migration) mantığı eklendi.
    - `build.sh` içine `$PROJECT_DIR/models/onnx` (`en_rec.onnx`, `en_dict.txt`, `latin_rec.onnx`, `latin_dict.txt`) dosyalarının hem Windows (`$DIST_DIR/models`) hem Linux (`$appdir/usr/models`) paketlerine kopyalanması eklendi.
36. **`[Tamamlandı]`** **Aşama 17.8 (`tests/test_text_filter.py`):** `test_self_capture_echo_and_english_onnx_model_selection` birim testi eklendi.
37. **`[Tamamlandı]`** **Aşama 17.9 (`gameocr/ocr_engine.py` `Path` İçe Aktarımı, `pytest -v` ve Windows Paketinin Yeniden Üretilmesi):** Tüm **74/74** birim testi (`7.11s`) başarıyla geçti; `GameOCR-Windows-Beta-cpu.zip` ve `GameOCR-Windows-Beta-nvidia.zip` paketleri `models/onnx/en_rec.onnx` ve `latin_rec.onnx` gömülü olarak yeniden üretildi.
38. **`[Tamamlandı]`** **Aşama 18.1 (Farklı Dillerde OCR Paketi İndirme Özelliği — Mimari Analiz ve Planlama):** Çok dilli OCR tanıma paketlerinin (`EN`, `LATIN`, `JA`, `KO`, `ZH`, `RU`, `AR`, `EL`) indirilmesi, yönetimi (`OcrModelManager` & `OcrModelDownloadWorker`), `RapidOcrEngine` / `PaddleCudaEngine` entegrasyonu ve Ayarlar (`Algılama ve OCR` sekmesi) arayüzü için hazırlanan modüler geliştirme planı kullanıcı tarafından onaylandı.
39. **`[Tamamlandı]`** **Aşama 18.2 (Adım 1 — `gameocr/ocr_models.py` Modülünün Oluşturulması):** `OcrPackInfo`, `AVAILABLE_OCR_PACKS` (`EN`, `LATIN`, `JA`, `KO`, `ZH`, `RU`, `AR`, `EL`), `OcrModelManager` (atomik ONNX model + karakter sözlüğü indirme, `ocr_manifest.json` yönetimi ve `CTCLabelDecode` sözlük boyutu normalizasyonu) ve `OcrModelDownloadWorker(QThread)` sınıfları oluşturuldu.
40. **`[Tamamlandı]`** **Aşama 18.3 (Adım 2 — `gameocr/config.py`, `config.default.toml` ve `gameocr/languages.py` Entegrasyonu):** `OcrConfig` içerisine `installed_ocr_packs` alanı eklendi; `SOURCE_LANGUAGES` ve `TARGET_LANGUAGES` listeleri `UK`, `EL`, `NL`, `SV` kaynak dillerini de kapsayacak şekilde genişletildi.
41. **`[Tamamlandı]`** **Aşama 18.4 (Adım 3 — `gameocr/ocr_engine.py` Entegrasyonu):** `RapidOcrEngine._find_bundled_onnx_rec_model()` metodu `OcrModelManager` ve `resolve_ocr_pack_for_lang()` ile entegre edildi; `BaseOcrEngine.update_config()` içine `installed_ocr_packs` değiştiğinde modeli canlı yeniden yükleme kontrolü eklendi.
42. **`[Tamamlandı]`** **Aşama 18.5 (Adım 4.1 — `gameocr/i18n.py` Çift Dilli Arayüz Anahtarları):** Türkçe (`tr`) ve İngilizce (`en`) sözlüklerine `settings.ocr_packs_title`, `settings.ocr_pack_col_*` ve indirme durumu mesajları eklendi.
43. **`[Tamamlandı]`** **Aşama 18.6 (Adım 4.2 — `gameocr/ui/settings_dialog.py` OCR Dil Paketleri Yöneticisi):** Ayarlar penceresinin `Algılama ve OCR` sekmesine `ocr_packs_table`, `ocr_pack_progress_bar`, `ocr_pack_status_label`, `OcrModelDownloadWorker` arka plan indirme entegrasyonu ve canlı `on_applied` bildirimi eklendi.
44. **`[Tamamlandı]`** **Aşama 18.7 (Adım 5.1 — `tests/test_ocr_models.py` Birim Testlerinin Oluşturulması):** `OcrModelManager`, `OcrModelDownloadWorker`, `RapidOcrEngine` model çözümleme ve `SettingsDialog` OCR paket tablosu için 4 yeni birim testi eklendi.
45. **`[Tamamlandı]`** **Aşama 18.8 (Adım 5.2 — `uv run pytest -v` Tüm Test Paketinin Çalıştırılması):** Tüm **78/78** birim testi (`7.84s`) başarıyla geçti.
46. **`[Tamamlandı]`** **Aşama 19.1 (GitHub Tek Komut Yayınlama, Gizlilik/Telif Temizliği, `build.sh` Otomatik Kütüphane İndirici ve Dokümantasyon Planlaması — Revize Edildi):** Kullanıcının mimari yönlendirmesiyle revize edilen plan onaylandı.
47. **`[Tamamlandı]`** **Aşama 19.2 (Adım 1 — `build.sh` İçine Otomatik Kütüphane ve Model İndirici `ensure_build_prerequisites()` Eklenmesi):** `build.sh` içine klasörde `.venv`, varsayılan ONNX OCR modelleri (`en_rec.onnx`, `latin_rec.onnx`), çevrimdışı `EN-TR` CTranslate2 modeli veya (`--gpu nvidia`/`dual` seçildiğinde) `paddlepaddle-gpu==3.3.1` (CUDA 12.6) + `PP-OCRv5` modelleri eksikse resmi adreslerden otomatik indiren önyükleyici (bootstrap) fonksiyonu eklendi.
48. **`[Tamamlandı]`** **Aşama 19.3 (Adım 2 — Gizlilik, Gereksiz Dosya ve Telif/Lisans Temizliği):** `gameocr.spec` içindeki yerel `/home/<kullanici>/...` mutlak yolları kaldırıldı, kök dizindeki geçici `=` dosyası silindi; `.gitignore`, `LICENSE` (MIT) ve `THIRD_PARTY_NOTICES.md` dosyaları oluşturuldu.
49. **`[Tamamlandı]`** **Aşama 19.4 (Adım 3 — Tek Komutla GitHub Yayınlama ve Sürüm Betiği `publish_github.sh`):** Kişisel bilgi / API anahtarı / 50 MB üzeri dosya taraması yapan, `git init` + `gh repo create` ile depoyu tek komutla yayınlayan ve `--release <etiket>` ile yalnızca telif/boyut dostu Universal paketlerini GitHub Releases'a yükleyen `publish_github.sh` betiği oluşturuldu.
50. **`[Tamamlandı]`** **Aşama 19.5 (Adım 4.1 — `AGENTS.md` ve `README.md` Güncellemesi):** `AGENTS.md` ve `README.md` dosyaları Dual-Engine OCR, çok dilli OCR paket indirici (`OcrModelManager`), `build.sh` otomatik kütüphane indirme ve `publish_github.sh` tek komutla yayınlama/Releases rehberiyle güncellendi.
51. **`[Tamamlandı]`** **Aşama 19.6 (Adım 4.2 — `docs/tr/*` ve `docs/en/*` Teknik Dokümantasyon Güncellemesi):** `docs/tr/local_translation.md`, `docs/tr/building.md`, `docs/en/local_translation.md` ve `docs/en/building.md` dosyaları çok dilli OCR paket yöneticisi, `build.sh` otomatik önyükleyici ve `publish_github.sh` kullanımıyla güncellendi.
52. **`[Tamamlandı]`** **Aşama 19.7 (`tests/test_ocr_models.py` Gizlilik ve `build.sh` Bootstrap Birim Testi):** `test_publish_github_check_only_and_build_bootstrap_present` birim testi eklendi.
53. **`[Tamamlandı]`** `./publish_github.sh --check-only` ve `uv run pytest -v` Final Doğrulaması: Gizlilik/telif/dosya boyutu taraması sıfır uyarıyla geçti ve tüm **79/79** birim testi (`7.66s`) başarıyla tamamlandı.
54. **`[Tamamlandı]`** **Aşama 20.1 (Linux Mint VM Teşhisi):** `taner@192.168.221.129` üzerinde SSH ile sistem kütüphaneleri doğrulandı (`libxcb-cursor.so.0` eksik, diğer `xcb` kütüphaneleri mevcut).
55. **`[Tamamlandı]`** **Aşama 20.2 (`build.sh` & `gameocr/__main__.py`):** `build.sh` içine `cv2/qt` temizliği, `libxcb-cursor.so.0` ve yardımcı XCB/XKB kütüphanelerinin `$appdir/usr/lib` altına fallback olarak gömülmesi, `AppRun` içinde `LD_LIBRARY_PATH` sonuna `:$HERE/usr/lib` eklenmesi ve `QT_QPA_PLATFORM_PLUGIN_PATH` koruması eklendi; `gameocr/__main__.py` içinde `QApplication` öncesi PyQt6 eklenti yolu güvenceye alındı.
56. **`[Tamamlandı]`** **Aşama 20.3 (AppImage Yeniden Derleme, Linux Mint VM Doğrulaması ve `pytest -v`):**
    - `build.sh` içindeki `ldconfig -p | awk` SIGPIPE (exit 141) sorunu giderildi ve `GameOCR-Universal-x86_64.AppImage` (`824M`) sıfırdan üretildi.
    - `taner@192.168.221.129:~/Downloads/` dizinine kopyalanıp **hiçbir ek paket kurulmadan** `DISPLAY=:0 timeout 8s ~/Downloads/GameOCR-Universal-x86_64.AppImage` ile çalıştırıldı; Qt `xcb` eklentisi, `xcomposite` yakalama, `RapidOCR` (`en_rec.onnx`), 4 iş parçacığı ve ROI seçici hatasız başlatıldı.
    - Yerel `uv run pytest -v` ile **79/79** test (`6.91s`) başarıyla geçti.
57. **`[Tamamlandı]`** **Aşama 21.1 (Cinnamon Tepsi Teşhisi):** Cinnamon VM'de `xwininfo` / `XCompositeBackend` / `OverlayWindow` doğrulandı; `StatusNotifierItem` üzerinde `IconName=""` olduğu için Cinnamon `xapp-sn-watcher` tarafından görünmediği tespit edildi.
58. **`[Tamamlandı]`** **Aşama 21.2 (Evrensel Kontrol Merkezi, Tek Örnek IPC, `show_panel` Kısayolu ve Tepsi İkon/Tema Düzeltmesi):**
    - `gameocr/ui/control_window.py` (`ControlWindow`): Tüm masaüstlerinde görev çubuğundan doğrudan erişilebilen kompakt Kontrol Merkezi penceresi eklendi.
    - `gameocr/ui/tray.py`: `get_tray_icon()` ile `~/.local/share/icons/hicolor/64x64/apps/gameocr.png` yazılıp `QIcon.fromTheme("gameocr")` yüklendi; `tray.activated` (sol tık) ve `tray.show_panel` menü öğesi eklendi.
    - `gameocr/__main__.py`: GTK tabanlı masaüstlerinde (`Cinnamon`, `GNOME`, `XFCE`, `MATE`, `Budgie`, `Unity`, `Pantheon`, `LXDE`) otomatik `QT_QPA_PLATFORMTHEME=gtk3` seçimi, `QLocalServer` / `QLocalSocket` Tek Örnek IPC (`os._exit(0)` ile temiz çıkış) ve `ControlWindow` başlangıç/kısayol entegrasyonu eklendi.
    - `gameocr/config.py`, `config.default.toml`, `gameocr/i18n.py`, `gameocr/ui/settings_dialog.py`: `HotkeysConfig.show_panel = "ctrl+alt+g"` kısayolu ve çift dilli arayüz anahtarları eklendi.
59. **`[Tamamlandı]`** **Aşama 21.3 (`tests/test_control_window.py`, `uv run pytest -v`, AppImage & Cinnamon VM Doğrulaması):**
    - **82/82** birim testi (`8.28s`) başarıyla geçti.
    - `GameOCR-Universal-x86_64.AppImage` (`824M`) yeniden üretilip Linux Mint Cinnamon VM'de test edildi: `GameOCR — Kontrol Merkezi` penceresi açıldı, D-Bus `StatusNotifierItem.IconName` `"gameocr"` olarak doğrulandı ve ikinci örnek `SECOND_EXIT:0` ile mevcut pencereyi öne getirdi.
60. **`[Tamamlandı]`** **Aşama 21.4 (`libxkbcommon-x11.so.0` ABI Çakışması / X11 KeyPress SIGSEGV Düzeltmesi):**
    - Fedora 45 (`libxkbcommon 1.13.1`) üzerinden gelen `libxkbcommon-x11.so.0` ile Mint 24.04 (`libxkbcommon 1.6.0`) üzerindeki `libxkbcommon.so.0` birleşince ilk X11 klavye olayında `xkb_state_key_get_layout` içinde `SIGSEGV` oluştuğu tespit edildi.
    - `build.sh` içindeki `xcb_fallback_libs` listesinden `libxkbcommon-x11.so.0` çıkarıldı; evrensel (`--de other --display hybrid`) `GameOCR-Universal-x86_64.AppImage` (`824M`) yeniden derlenip VM'de X11 `KeyPress` sonrası ayakta kaldığı (`GAMEOCR_ALIVE_AFTER_KEYPRESS`) doğrulandı.
61. **`[Tamamlandı]`** **Aşama 21.5 (`LC_NUMERIC="C"` Sabitlemesi + `ControlWindow` Çarpı ile Kapatma Davranışı):**
    - `QApplication(sys.argv)` çağrısının `tr_TR.UTF-8` gibi yerel ayarlarda `LC_NUMERIC`'i değiştirmesi nedeniyle `RapidOCR`'ın `(None, None)` döndürdüğü tespit edildi. `gameocr/__main__.py` içinde `QApplication` sonrası `locale.setlocale(locale.LC_NUMERIC, "C")` sabitlendi.
    - `ControlWindow` `hide_on_close=False` yapılarak çarpı (`×`) tuşunun doğrudan uygulamayı kapatması (`on_quit`), küçültme butonunun ise `showMinimized()` ile görev çubuğuna küçültmesi sağlandı (`gameocr/__main__.py`, `gameocr/ui/control_window.py`, `gameocr/i18n.py`, `tests/test_control_window.py`).
    - `uv run pytest -v` ile **82/82** test (`9.06s`) geçti; `GameOCR-Universal-x86_64.AppImage` (`824M`) yeniden üretilip Linux Mint VM'de `LANG=tr_TR.UTF-8` altında canlı OCR (`güven=0.99`) ve çeviri doğrulandı.
62. **`[Tamamlandı]`** **`CHANGELOG.md` Oluşturulması:** Bugün (Aşama 20–21) yapılan tüm değişiklikler, kök neden analizleri, mimari kararlar, test sonuçları ve dosya listesi sonraki ajanların GitHub Release hazırlığında referans alması için `CHANGELOG.md` dosyasına detaylı olarak işlendi.
63. **`[Tamamlandı]`** **Aşama 22 (Windows Sürümü Self-Capture & Performans Kök Neden Düzeltmesi):**
    - Windows 10 VM (`192.168.221.128`) üzerinde yapılan canlı testlerde `WA_TranslucentBackground=True` (`UpdateLayeredWindow`) kullanan pencerelerde DWM'in `SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)` çağrısını `ok=0, err=8` ile reddettiği ve `mss` (`BitBlt`) ile kendi overlay'inin/kontrol penceresinin tekrar yakalanıp çevrildiği (geri besleme döngüsü) kanıtlandı.
    - `gameocr/ui/overlay.py`: Windows'ta `WA_TranslucentBackground` kaldırılarak `setMask(QRegion)` + `setWindowOpacity()` ve DPI (`devicePixelRatio()`) uyumu eklendi; `SetWindowDisplayAffinity` `ok=1` ile çalışır hale getirildi.
    - `gameocr/ui/control_window.py` & `gameocr/ui/roi_selector.py`: Windows'ta `showEvent` içinde `set_win32_exclude_from_capture(..., True)` ve `RoiSelectorWindow` için `setWindowOpacity(0.42)` uygulanarak Kontrol Merkezi ve ROI seçicinin de yakalanması engellendi.
    - `gameocr/preprocess.py`: `upscale()` içindeki gereksiz büyütme sınırı (`2000x1080` -> `1280x480` ve `h >= 240 and w >= 400` için atlama) düzeltilerek `719x385` boyutundaki ROI'de `RapidOCR` CPU çıkarım süresi `836-1600 ms` seviyesinden **`88.4 ms`** seviyesine indirildi.
    - `tests/test_logging_and_win32.py`: `test_win32_overlay_mask_and_large_roi_upscale_skip` eklendi; `uv run pytest -v` ile **83/83** test (`6.49s`) geçti.
    - Windows VM'de canlı doğrulama (`diff=0.000`, `ocr_ms=88.4`, `ocr_res=('There are no beautiful surfaces without a terrible depth.', 0.983)`) tamamlandı ve güncel `GameOCR-Universal-x64.exe` (`571,458,995` bayt) Masaüstü'ne derlendi.

64. **`[Tamamlandı]`** **Aşama 23 (`v0.2.0` Sürüm Hazırlığı ve GitHub Release):**
    - `pyproject.toml`, `gameocr/__init__.py` ve `CHANGELOG.md` dosyaları `0.2.0` sürümüne yükseltildi ve Aşama 20–22 değişiklikleri `CHANGELOG.md` içine işlendi.
    - `./publish_github.sh --check-only` ile gizlilik, kişisel veri, API anahtarı ve büyük dosya taraması sıfır uyarıyla geçildi.
    - Güncel `GameOCR-Universal-x86_64.AppImage` (`824M`) derlenip `--help` ile doğrulandı; Windows VM Masaüstü'nden `dist/GameOCR-Universal-x64.exe` (`545M`, PE32+ x86-64 GUI) alındı.
    - Tüm temiz değişiklikler commit'lenip `v0.2.0` etiketiyle `origin/main` üzerine push'lanarak GitHub Release oluşturuldu.

---

## 4. Aktif Bağlam (Sıradaki Adım — Devir-Teslim Rehberi)

- **Anlık Durum:** Aşama 23 tamamlandı. `v0.2.0` sürümü kaynak kodu ve derlenmiş Linux (`GameOCR-Universal-x86_64.AppImage`) + Windows (`GameOCR-Universal-x64.exe`) paketleriyle GitHub Releases üzerinde yayınlanmıştır.
- **Bir Sonraki Ajan / Sıradaki Adım:** Tüm aşamalar tamamlanmıştır; kullanıcıdan gelecek yeni geri bildirim veya ek özellik talepleri beklenmektedir.
