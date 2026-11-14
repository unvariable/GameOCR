# 3. Çevrimdışı (Lokal) Çeviri Motoru ve Bellek Yönetimi

GameOCR, DeepL API anahtarı olmayan, internet bağlantısı bulunmayan veya API kotasını korumak isteyen kullanıcılar için `gameocr/local_models.py` modülünde tamamen çevrimdışı çalışan bir çeviri altyapısı sunar.

## 3.1. Desteklenen Çeviri Modları (`translation_engine`)

Ayarlar → Çevirmen sekmesinden veya `config.toml` içinden 3 mod seçilebilir:
1. **`deepl` (Varsayılan):** DeepL Bulut API'sini kullanır.
2. **`local`:** Yalnızca yerel CTranslate2 / Argos Translate sinirsel makine çevirisi modellerini kullanır (0 internet kullanımı).
3. **`auto_fallback` (Hibrit):** Önce DeepL API'sini dener; API anahtarı girilmemişse, aylık 500.000 karakter kotası dolmuşsa veya geçici ağ kesintisi varsa kesintisiz olarak lokal çevrimdışı motora düşer.

## 3.2. Varsayılan Dil Paketi ve İndirme Yöneticisi

- **Varsayılan Kurulum (`EN-TR`):** Disk ve bellek alanını şişirmemek için ilk kurulumda **yalnızca İngilizce → Türkçe (`EN-TR`)** dil paketi kurulu gelir.
- **Lokal Dil Paketleri Yöneticisi:** Ayarlar → Çevirmen sekmesinin alt kısmındaki tablodan diğer dil çiftleri (`JA-TR`, `EN-DE`, `DE-TR`, `FR-TR`, `ES-TR`, `RU-TR`, `ZH-TR`, `KO-TR`, `IT-TR`) tek tıkla indirilebilir veya kaldırılabilir.
- **Asenkron İndirme (`ModelDownloadWorker`):** İndirme işlemleri `QThread` üzerinde yürütülür; ilerleme durumu `QProgressBar` ile canlı gösterilir ve arayüz veya oyun içi altyazı akışı asla donmaz.
- **Pivot (Köprü) Çeviri Desteği:** Doğrudan model bulunmayan dil çiftlerinde (ör. `JA -> TR`), sistem otomatik olarak `JA -> EN -> TR` şeklinde iki aşamalı CTranslate2/Argos köprü çevirisi uygular.

## 3.3. Bellek (RAM / VRAM) Yönetimi

Oyun oynarken sistem kaynakları (özellikle GPU VRAM ve RAM) oyun için kritiktir. `LocalModelManager` bu nedenle **Lazy Loading (Tembel Yükleme)** ve **Tekil Aktif Model** stratejisi uygular:
- Uygulama `deepl` modundayken hiçbir lokal çeviri modeli belleğe yüklenmez (`0 MB` ek RAM/VRAM kullanımı).
- `local` modda çeviri istendiğinde yalnızca aktif dil çiftinin (`_loaded_pair`) `int8` nicemlenmiş (quantized) ağırlıkları belleğe yüklenir.
- Kullanıcı kaynak/hedef dili değiştirdiğinde veya `deepl` moduna döndüğünde `unload_model()` çağrılarak önceki model derhal bellekten boşaltılır.

## 3.4. Çok Dilli OCR Paketi İndirme Yöneticisi (`gameocr/ocr_models.py`)

Çeviri paketlerine ek olarak, farklı alfabelerdeki oyun altyazılarını yüksek doğrulukla okuyabilmek için **Ayarlar → Algılama ve OCR** sekmesinde **OCR Dil Paketleri Yöneticisi (`OcrModelManager`)** yer alır:
- **Varsayılan Kurulu OCR Paketleri:** `EN` (İngilizce — `en_rec.onnx`) ve `LATIN` (Türkçe, Almanca, Fransızca, İspanyolca, İtalyanca, Portekizce, Lehçe, Felemenkçe, İsveççe — `latin_rec.onnx`).
- **İndirilebilir OCR Paketleri:** `JA` (Japonca), `KO` (Korece), `ZH` (Çince), `RU` (Rusça / Ukraynaca / Kiril), `AR` (Arapça) ve `EL` (Yunanca).
- İndirme işlemi `OcrModelDownloadWorker(QThread)` ile arka planda yürütülür, sözlük satır sayısı ONNX çıkış katmanıyla otomatik hizalanır (`_normalize_dict_for_onnx`) ve tamamlandığında aktif OCR motoru canlı olarak yeni modelle güncellenir.


