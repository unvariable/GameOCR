# Changelog — GameOCR

Bu belge, GameOCR projesinde yapılan değişiklikleri, kök neden analizlerini, mimari kararları ve doğrulama sonuçlarını kaydeder. GitHub Release notları hazırlanırken referans olarak kullanılabilir.

---

## [0.2.1] — 2026-11-17 (Güvenlik, Bağımlılık Temizliği ve Gizlilik Sertleştirmesi)

### Öne Çıkanlar (Release Özeti)
- **Dependabot `stanza` (CWE-502) Güvenlik Açığı Giderildi:** Kullanılmayan `argostranslate` opsiyonel bağımlılığı kaldırılarak etkilenen `stanza<=1.12.1` (ve `torch`, `spacy` vb. 50+ gereksiz paket) tamamen temizlendi; `pyproject.toml` içine kalıcı `stanza>=1.12.2` güvenlik alt sınırı eklendi.
- **Arşiv ve Ağ İndirme Güvenliği (`gameocr/security.py`):**
  - Model indirmelerinde `https://` şema zorunluluğu (`validate_https_url`) ve indirme boyut üst sınırı getirildi.
  - `.argosmodel` (ZIP) arşivlerinin açılmasında Zip Slip (path traversal), sembolik link ve Zip Bomb koruması (`safe_extract_zip`) eklendi.
- **Kullanıcı Gizliliği ve Veri Koruma:**
  - DeepL API anahtarını içeren `config.toml`, çeviri önbelleği `cache.db` ve `gameocr.log` için POSIX sistemlerde `0o600` (dizinler `0o700`) erişim izinleri zorunlu kılındı.
  - Tüm log handler'larına `_SecretRedactingFilter` eklenerek API anahtarları ve `Authorization` başlıklarının loglara sızması (`[REDACTED]`) engellendi.
  - Tek-örnek IPC sunucusu (`QLocalServer`) için `UserAccessOption` ve KDE kısayol tetikleyici betiği için `0o700` izni uygulandı.
- **Topluluk Standartları:** `CODE_OF_CONDUCT.md`, `CONTRIBUTING.md` ve `SECURITY.md` standartlara uygun ve net hale getirildi.

---

## [0.2.0] — 2026-11-16 (Linux Masaüstü Taşınabilirliği, Evrensel Kontrol Merkezi ve Windows Self-Capture / Performans Düzeltmeleri)

### Öne Çıkanlar (Release Özeti)
- **Sıfır Kurulumla Temiz Linux Sistemlerde Çalışma:** `GameOCR-Universal-x86_64.AppImage` artık `libxcb-cursor0` paketi kurulu olmayan temiz Linux Mint / Ubuntu / Debian sistemlerde ek paket kurulumu gerektirmeden doğrudan çalışır.
- **Evrensel Kontrol Merkezi (`ControlWindow`):** Sistem tepsisi ikonunun görünmediği veya desteklenmediği tüm Linux masaüstü ortamlarında (Cinnamon, GNOME, XFCE, tiling WM'ler vb.) ve Windows'ta arayüze %100 erişim sağlayan kompakt kontrol penceresi eklendi.
- **Popüler Masaüstleri İçin Sistem Tepsisi Düzeltmesi:** Cinnamon (`xapp-sn-watcher`) ve GNOME AppIndicator gibi StatusNotifierHost bileşenlerinde ikonsuz kalma sorunu `QIcon.fromTheme("gameocr")` + `QT_QPA_PLATFORMTHEME=gtk3` ile giderildi.
- **Türkçe / Virgüllü Yerel Ayar (`tr_TR.UTF-8`) OCR Hatası Giderildi:** `QApplication` sonrası `LC_NUMERIC` değerinin `"C"` olarak sabitlenmesiyle Türkçe ve diğer virgüllü ondalık sistemlerde `RapidOCR`'ın boş (`None`) dönmesi düzeltildi.
- **Windows Self-Capture Geri Besleme Döngüsü ve DPI/Hız Düzeltmesi:** Windows'ta `OverlayWindow`, `ControlWindow` ve `RoiSelectorWindow` artık `SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)` ile %100 görünmez (`diff=0.000`) hale getirildi; büyük ROI'lerde gereksiz 2x büyütme kaldırılarak OCR süresi ~836–1600 ms'den **~88 ms**'ye düşürüldü.
- **Tek Evrensel Hibrit Paket:** Tek bir `GameOCR-Universal-x86_64.AppImage` (`--de other --display hybrid`) tüm Linux masaüstü ortamlarını ve Wayland/X11 oturumlarını çalışma anında otomatik algılar.

---

### 1. AppImage Taşınabilirlik ve Qt6 `xcb` / OpenCV Çakışma Düzeltmeleri

#### Kök Nedenler
1. **Eksik `libxcb-cursor.so.0`:** Qt 6.5.0+ sürümlerinde `xcb` platform eklentisi (`libqxcb.so`) sistemde `libxcb-cursor.so.0` (`libxcb-cursor0`) kütüphanesini gerektirir. Temiz Linux Mint 24.04 / Ubuntu kurulumlarında bu paket varsayılan olarak bulunmadığı için `Could not load the Qt platform plugin "xcb"` ve `Aborted (core dumped)` hatası oluşuyordu.
2. **`cv2/qt/plugins` Çakışması:** `.venv` içinde `opencv-python` / `opencv-contrib-python` paketlerinden gelen `cv2/qt/plugins` dizini AppImage'a dahil oluyor ve `cv2` import edildiğinde `QT_QPA_PLATFORM_PLUGIN_PATH` değişkenini `PyQt6/Qt6/plugins` yerine kendi dizinine yönlendiriyordu.
3. **`build.sh` SIGPIPE (`141`) Hatası:** `set -euo pipefail` aktifken `ldconfig -p | awk '... exit'` kullanımı erken çıkış nedeniyle `SIGPIPE` (`141`) üreterek derlemeyi durduruyordu.
4. **`libxkbcommon-x11.so.0` ABI Uyumsuzluğu (`SIGSEGV`):** Başlangıçta fallback listesine eklenen Fedora 45 (`libxkbcommon 1.13.1`) kaynaklı `libxkbcommon-x11.so.0`, hedef sistemdeki `libxkbcommon.so.0` (`1.6.0`) ile birleşince ilk X11 klavye olayında `xkb_state_key_get_layout` içinde `SIGSEGV` (`0x100000007e0`) oluşturuyordu.

#### Yapılan Değişiklikler
- **`build.sh`:**
  - `BUNDLE_MODE == "full"` aşamasında `$appdir/usr/site-packages/cv2/qt` dizini paketleme sırasında silindi (`rm -rf`).
  - `xcb_fallback_libs` listesi ile `libxcb-cursor.so.0`, `libxcb-icccm.so.4`, `libxcb-image.so.0`, `libxcb-keysyms.so.1`, `libxcb-render-util.so.0` ve `libxcb-util.so.1` kütüphaneleri `$appdir/usr/lib/` altına kopyalandı.
  - `libxkbcommon-x11.so.0` ABI uyumsuzluğu nedeniyle fallback listesinden özellikle hariç tutuldu (hedef sistemin kendi `libxkbcommon.so.0` sürümüyle eşleşmesi gerekir).
  - `ldconfig -p` araması `awk` içinde `exit` kullanmadan (`!found && ... {found=1}`) yazıldı; böylece `SIGPIPE` (`141`) engellendi.
  - `AppRun` içinde `$HERE/usr/lib` yolu `LD_LIBRARY_PATH` **sonuna** fallback olarak eklendi (sistemde varsa sistem kütüphanesi, yoksa AppImage içindeki kütüphane kullanılır; boş `::` yolu oluşmaması için `${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}` kullanıldı).
  - `AppRun` içinde `PyQt6/Qt6/plugins` mevcutsa `QT_PLUGIN_PATH` ve `QT_QPA_PLATFORM_PLUGIN_PATH` değişkenleri açıkça ayarlandı.
- **`gameocr/__main__.py`:**
  - Linux'ta (`sys.platform != "win32"`) `QApplication(sys.argv)` çağrılmadan hemen önce `PyQt6/Qt6/plugins/platforms` yolu `QT_PLUGIN_PATH` ve `QT_QPA_PLATFORM_PLUGIN_PATH` içine tekrar atanarak `cv2` importunun yolu ezmesi engellendi.

---

### 2. Evrensel Arayüz Erişimi (`ControlWindow`), Tek Örnek IPC ve `show_panel` Kısayolu

#### Kök Neden
- Önceden GameOCR arayüzüne (Ayarlar, Pencere Seçici, ROI Seçici, Geçmiş) erişim yalnızca sistem tepsisine (`QSystemTrayIcon`) ve sınırlı kısayollara bağlıydı.
- GNOME (varsayılan tepsi yok), Linux Mint Cinnamon (XEmbed tepsisi yok, SNI `IconName` gerektiriyor) veya tiling WM'ler (i3, Sway, Hyprland) gibi ortamlarda tepsi ikonu görünmediğinde kullanıcı arayüze hiçbir şekilde ulaşamıyordu.

#### Yapılan Değişiklikler
- **`gameocr/ui/control_window.py` (Yeni Dosya):**
  - Görev çubuğunda/panelde ve `Alt+Tab` listesinde standart pencere olarak görünen kompakt `ControlWindow` (`GameOCR — Kontrol Merkezi`) sınıfı oluşturuldu.
  - Üst durum kartı: aktif durum (`Aktif` / `Duraklatıldı`), dil çifti (`EN → TR`) ve aktif yakalama backend'i (`xcomposite`, `portal`, `win32` vb.).
  - 2 sütunlu hızlı erişim butonları: `Başlat / Duraklat`, `Program İzle / Pencere Seç`, `Altyazı Alanı (ROI) Seç`, `Altyazıyı Göster / Gizle`, `Ayarlar`, `Çeviri Geçmişi`.
  - Alt çubuk ve kapatma davranışı: `hide_on_close=False` ile pencerenin **çarpı (`×`) tuşu doğrudan programı kapatır** (`on_quit`); **"Simge Durumuna Küçült"** butonu ise `showMinimized()` ile pencereyi görev çubuğuna küçültür. Böylece tepsisi olmayan masaüstlerinde arka planda kontrolsüz kalan süreç oluşmaz.
- **`gameocr/__main__.py`:**
  - `QLocalServer` / `QLocalSocket` tabanlı Tek Örnek (Single-Instance) IPC eklendi (`_ipc_server_name`, `_try_notify_running_instance`).
  - GameOCR zaten çalışırken ikinci bir örnek başlatıldığında (`--allow-multiple` verilmedikçe) çalışan örneğe `"SHOW"` komutu göndererek mevcut `ControlWindow` penceresini öne getirir ve ikinci örnek `os._exit(0)` ile (`QApplication` yıkım `SIGSEGV`'si olmadan) temizce sonlanır.
  - `--minimized` ve `--allow-multiple` CLI argümanları eklendi; varsayılan açılışta `control_window.bring_to_front()` çağrılır.
- **`gameocr/config.py`, `config.default.toml`, `gameocr/i18n.py`, `gameocr/ui/settings_dialog.py`:**
  - `HotkeysConfig` içine `show_panel: str = "ctrl+alt+g"` kısayolu eklendi.
  - Ayarlar → Kısayollar sekmesine `hotkey_show_panel_btn` eklendi ve `apply()` içine bağlandı.
  - `i18n.py` Türkçe (`tr`) ve İngilizce (`en`) sözlüklerine `tray.show_panel`, `control.*` ve `settings.hotkey_show_panel` anahtarları eklendi.

---

### 3. Popüler Masaüstü Ortamları İçin Sistem Tepsisi İkon ve Tema Düzeltmesi

#### Kök Neden
- Cinnamon VM üzerinde D-Bus incelemesinde `xapp-sn-watcher` (`org.kde.StatusNotifierWatcher`) üzerinde `QSystemTrayIcon` kaydı görünse bile `StatusNotifierItem.IconName` değerinin boş (`""`) kaldığı tespit edildi; çünkü `create_default_tray_icon()` yalnızca bellek içi `QPixmap` üretiyordu.
- Ayrıca Linux'ta `QT_QPA_PLATFORMTHEME` tanımlanmadığı için GTK tabanlı masaüstlerinde (`Cinnamon`, `GNOME`, `XFCE`, `MATE` vb.) Qt6'nın `libqgtk3.so` entegrasyonu devreye girmiyordu.

#### Yapılan Değişiklikler
- **`gameocr/ui/tray.py`:**
  - `get_tray_icon()` eklendi: `~/.local/share/icons/hicolor/64x64/apps/gameocr.png` dosyasını oluşturup `QIcon.fromTheme("gameocr")` üzerinden yükler (yoksa dosya yolu veya bellek içi ikona düşer). Bu sayede `StatusNotifierItem.IconName` değeri `"gameocr"` olur.
  - `TrayManager` menüsünün en üstüne `tray.show_panel` (`🎛️ Kontrol Merkezi`) öğesi eklendi.
  - `self.tray.activated` sinyali (`Trigger` / `DoubleClick`) `on_show_control` geri çağrısına bağlandı; tepsi ikonuna sol tıklamak Kontrol Merkezini öne getirir.
- **`gameocr/__main__.py`:**
  - `XDG_CURRENT_DESKTOP` değeri `cinnamon`, `gnome`, `xfce`, `mate`, `budgie`, `unity`, `pantheon` veya `lxde` içeriyorsa ve `QT_QPA_PLATFORMTHEME` atanmamışsa otomatik olarak `QT_QPA_PLATFORMTHEME=gtk3` ayarlanır.
  - `app.setWindowIcon(get_tray_icon())` eklendi.

---

### 4. `LC_NUMERIC` Yerel Ayar Düzeltmesi (Türkçe / Non-English Sistemlerde OCR Boş Dönme Sorunu)

#### Kök Neden
- Linux Mint (`LANG=tr_TR.UTF-8`) üzerinde `QApplication(sys.argv)` çağrısı C kütüphanesi düzeyinde `setlocale(LC_ALL, "")` çalıştırarak `LC_NUMERIC` kategorisini `tr_TR.UTF-8` (ondalık ayraç `,`) yapıyordu.
- Bu durumda `RapidOCR` (`RapidOcrEngine._infer_raw_items`) net ve yüksek kontrastlı görüntülerde dahi `self._ocr(img)` çağrısından `(None, None)` döndürüyor, bu yüzden `OcrWorker` metin bulamıyor ve çeviri geçmişi boş kalıyordu.

#### Yapılan Değişiklikler
- **`gameocr/__main__.py`:**
  - `QApplication(sys.argv)` çağrısının hemen ardından `locale.setlocale(locale.LC_NUMERIC, "C")` uygulanarak tüm sayısal ayrıştırma ve OCR eşiklerinin nokta (`.`) standardında kalması garanti altına alındı.

---

### 5. Testler ve Doğrulama

- **`tests/test_control_window.py` (Yeni Dosya):**
  - `test_control_window_actions_status_and_close_hides`: Tüm buton geri çağrıları, `update_status()`, `hide_on_close=True` gizleme ve `hide_on_close=False` iken çarpı (`×`) ile `on_quit` tetiklemesi doğrulandı.
  - `test_tray_icon_writes_xdg_theme_png`: `get_tray_icon()` fonksiyonunun `XDG_DATA_HOME/icons/hicolor/64x64/apps/gameocr.png` dosyasını ürettiği doğrulandı.
  - `test_single_instance_ipc_notify`: `QLocalServer` + `_try_notify_running_instance` ile `"SHOW"` IPC iletimi doğrulandı.
- **Birim Test Paketi (`uv run pytest -v`):** **82/82** test (`9.06s`) başarıyla geçti.
- **Canlı VM Doğrulaması (`Linux Mint Cinnamon` — `taner@192.168.221.129`, sıfır ek paket kurulumu):**
  - `GameOCR-Universal-x86_64.AppImage` (`824M`, `--de other --display hybrid`) çalıştırıldığında `GameOCR — Kontrol Merkezi` penceresi açıldı, X11 klavye olayı (`KeyPress`/`KeyRelease`) sonrası çökmeden çalıştı (`GAMEOCR_ALIVE_AFTER_KEYPRESS`), `StatusNotifierItem.IconName` `"gameocr"` olarak doğrulandı ve `LANG=tr_TR.UTF-8` altında canlı OCR (`güven=0.99`) + lokal çeviri çalıştı.

---

### 6. Windows Sürümü Self-Capture (`SetWindowDisplayAffinity`), DPI ve OCR Performans Düzeltmeleri

#### Kök Nedenler
1. **`WA_TranslucentBackground` / `UpdateLayeredWindow` Uyumsuzluğu:** Windows DWM, `WA_TranslucentBackground=True` kullanan pencerelerde `SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)` çağrısını reddeder (`ok=0`, `err=8`). Bu nedenle `mss` (`BitBlt`) her karede `OverlayWindow`'un kendi çizdiği çeviri metnini (ve `ControlWindow` / `RoiSelectorWindow` pencerelerini) yakalayıp tekrar çeviriye sokarak tutarsız/saçma çıktılara yol açıyordu.
2. **Büyük ROI'lerde Gereksiz 2x Büyütme Yavaşlığı:** `gameocr/preprocess.py` içindeki `upscale()` fonksiyonu `2000x1080` sınırına kadar 2x büyütme uyguladığından, `719x385` gibi çok satırlı alanları `1438x770` boyutuna çıkarıyor ve Windows CPU'da `RapidOCR` çıkarım süresini `~78 ms` yerine `836–1600 ms` seviyesine çıkarıyordu.

#### Yapılan Değişiklikler
- **`gameocr/ui/overlay.py`:**
  - Windows'ta (`sys.platform == "win32"`) `WA_TranslucentBackground` kaldırılarak `setMask(QRegion)` (`_sync_win32_mask`) + `setWindowOpacity()` (`_apply_win32_window_opacity`) mimarisine geçildi; `SetWindowDisplayAffinity` `ok=1` ile çalışır hale getirildi.
  - `set_roi_geometry()` içine Windows `devicePixelRatio()` ölçekleme dönüşümü eklendi.
- **`gameocr/ui/control_window.py` & `gameocr/ui/roi_selector.py`:**
  - Windows'ta `showEvent` içinde `set_win32_exclude_from_capture(..., exclude=True)` ve `RoiSelectorWindow` için `setWindowOpacity(0.42)` uygulanarak Kontrol Merkezi ile ROI seçicinin yakalamaya girmesi önlendi.
- **`gameocr/preprocess.py`:**
  - `upscale()` büyük ROI'lerde (`h >= 240 and w >= 400`) 2x büyütmeyi atlayacak ve maksimum sınırı `1280x480` tutacak şekilde optimize edildi.
- **`tests/test_logging_and_win32.py`:**
  - `test_win32_overlay_mask_and_large_roi_upscale_skip` birim testi eklendi (**83/83** test geçti).

---

### Değişen ve Eklenen Dosyalar
- `build.sh`
- `config.default.toml`
- `pyproject.toml`
- `gameocr/__init__.py`
- `gameocr/__main__.py`
- `gameocr/config.py`
- `gameocr/i18n.py`
- `gameocr/preprocess.py`
- `gameocr/ui/control_window.py` *(yeni)*
- `gameocr/ui/overlay.py`
- `gameocr/ui/roi_selector.py`
- `gameocr/ui/settings_dialog.py`
- `gameocr/ui/tray.py`
- `tests/test_control_window.py` *(yeni)*
- `tests/test_logging_and_win32.py`
- `PROGRESS.md`
- `CHANGELOG.md` *(yeni)*
