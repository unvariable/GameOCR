# 1. Mimari Çalışma Mantığı ve Dinamik Görsel Metin Hizalama

## 1.1. Çok İş Parçacıklı (Multi-Threaded) Boru Hattı

GameOCR, grafik arayüzde (PyQt6 ana thread) hiçbir kare düşüşü veya donma yaşanmaması için kuyruk tabanlı 4 bağımsız arka plan iş parçacığı (`daemon thread`) kullanır:

1. **`CaptureWorker` (`frame_q`, `maxsize=1`):**
   - Seçilen yakalama kaynağından (`PortalBackend`, `XCompositeBackend`, `MssBackend` veya `Win32Backend`) hedef FPS hızında (varsayılan 8 FPS) yalnızca seçilen altyazı bölgesini (`ROI`) yakalar.
   - Kuyruk boyutu `1` olduğu için OCR meşgulse eski kare otomatik düşürülür (`_put_drop_oldest`); böylece ekranda asla gecikmiş altyazı işlenmez.
2. **`OcrWorker` (`text_q`, `maxsize=4`):**
   - **`ChangeGate`:** Kareyi `64px` genişliğe küçülterek bir önceki kareyle ortalama piksel farkını ölçer. Fark `change_threshold` (%0.4) altındaysa pahalı GPU OCR çağrısını tamamen atlar ve metnin durağanlaştığını (`is_stable=True`) bildirir.
   - **PaddleOCR Çıkarımı ve `TextStyleMeta`:** Kare değiştiğinde `OcrEngine.recognize_with_meta()` hem metni okur hem de orijinal BGR kareden görsel stil metaverisini (`TextStyleMeta`) üretir.
3. **`FilterWorker` (`translate_q`, `maxsize=8`):**
   - Oyun arayüzü etiketlerini (`AUTO`, `SKIP`, `LOG`, `SPEAKING`) temizler.
   - **Daktilo (Typewriter) Koruması:** Harf harf akan altyazılarda yazım durulana (`settle_time`) veya cümle sonu noktalama işareti (`.`, `!`, `?`, `…`, `」`) görülene kadar çeviri isteği göndermez.
   - **SQLite + RapidFuzz Önbelleği (`CacheStore`):** Daha önce çevrilmiş veya `%90` üzeri benzerlik gösteren cümleleri 0 ms ağ gecikmesi ve 0 API kotasıyla doğrudan `ui_q` kuyruğuna iletir.
4. **`TranslatorWorker` (`ui_q`):**
   - Kuyrukta birikmiş ara daktilo adımlarını `_drain_superseded()` ile eler.
   - Seçili çeviri motorunu (`deepl`, `local` veya `auto_fallback`) çağırır, sonucu önbelleğe yazar ve `TextStyleMeta` ile birlikte `OverlayWindow`'a gönderir.

---

## 1.2. Dinamik Görsel Metin Hizalama (`exact_alignment`)

`config.toml` içindeki `[overlay]` bölümünde `exact_alignment = true` (varsayılan) olduğunda GameOCR sabit bir ortalı kutu yerine çeviriyi doğrudan oyundaki orijinal altyazının üzerine yerleştirir:

### A. Orijinal Koordinat Hizalaması (`bbox_rel`)
- OCR motorundan dönen kelime kutularının birleşik zarfı `(xmin, ymin, xmax, ymax)` hesaplanır ve ROI boyutuna bölünerek `0.0 .. 1.0` aralığında normalize `(x_rel, y_rel, w_rel, h_rel)` olarak saklanır.
- Ön işlemedeki büyütme (`preprocess.scale = 2.0`) veya oyun penceresinin yeniden boyutlandırılması normalize oranı bozmaz.

### B. Orijinal Yazı Tipi Boyutu (`match_font_size`)
- Tespit edilen kelime kutularının medyan piksel yüksekliği, ön işleme ölçek çarpanına (`scale_y`) bölünerek oyunun gerçek piksel satır yüksekliği (`line_height_px`) elde edilir.
- `OverlayWindow`, `QFont.setPixelSize(line_height_px)` ile çeviriyi orijinal metinle birebir aynı boyutta çizer.

### C. Vektörize Numpy/OpenCV Metin Rengi Örnekleme (`match_text_color`)
- Ön işleme (`preprocess`) görüntüyü ikili (siyah-beyaz) hale getirdiği için renk örneklemesi **ön işleme öncesindeki ham BGR kare (`raw_img`)** üzerinde yapılır:
  1. Metin sınır kutusu sıfır kopya (`numpy slice`) ile kesilir.
  2. `cv2.threshold(..., cv2.THRESH_OTSU)` ile pikseller iki kümeye ayrılır.
  3. Sınır kutusunun dış çerçeve (`border`) piksellerinde çoğunlukta olan küme **arka plan**, iç küme ise **metin (ön plan)** olarak belirlenir.
  4. Anti-aliasing (kenar yumuşatma) piksellerinin rengi soluklaştırmasını önlemek için arka plan parlaklığından kontrastça en uzak `%50` çekirdek piksellerin BGR medyanı (`np.median`) alınır (~0.2 ms).

---

## 1.3. Gelişmiş Loglama ve Aşamalı Traceback (`logging_utils.py`)

- `log_level = "DEBUG"` seçildiğinde:
  - Tüm kritik aşamalar (`color_sampling`, `bbox_alignment`, `ocr_predict`, `local_translate`, `paint_exact_overlay`) `timed_stage` ile milisaniye (`ms`) cinsinden ölçülür.
  - Thread kuyrukları (`frame_q`, `text_q`, `translate_q`) arasındaki mesaj gecikmeleri (`[IPC]`) loglanır.
  - Herhangi bir aşamada hata oluşursa `StageError` ve `log_stage_exception` hatanın tam olarak hangi aşamada ve hangi parametrelerle (`bbox_rel`, `shape` vb.) gerçekleştiğini `~/.local/share/gameocr/logs/gameocr.log` dosyasına kaydeder ve güvenli geri dönüş (standart panel) uygular.

