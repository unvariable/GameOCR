"""GameOCR Uluslararasılaşma ve Yerelleştirme (i18n) Modülü.

Arayüz varsayılan olarak Türkçe'dir; ayrıca tam İngilizce desteği içerir.
Yeni bir dil eklemek için aşağıdaki TRANSLATIONS sözlüğüne yeni bir dil kodu
(örneğin "de", "fr", "ja") ve çeviri anahtarlarını eklemek yeterlidir.
Eksik anahtarlar otomatik olarak Türkçe varsayılanına düşer.
"""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)

_CURRENT_LANG: str = "tr"

AVAILABLE_LANGUAGES: dict[str, str] = {
    "tr": "Türkçe",
    "en": "English",
}

TRANSLATIONS: dict[str, dict[str, str]] = {
    "tr": {
        # Uygulama Genel
        "app.name": "GameOCR",
        "app.tagline": "Gerçek Zamanlı Oyun Altyazı Çevirmeni",
        "btn.save": "💾 Kaydet",
        "btn.reset_defaults": "↺ Varsayılanlara Sıfırla",
        "btn.close": "Kapat",
        "btn.cancel": "İptal",
        "btn.delete": "🗑 Seçileni Sil",
        "btn.clear_all": "Tümünü Temizle",
        "btn.copy": "📋 Panoya Kopyala",
        "btn.verify_key": "🔍 Kotayı Sorgula",
        "msg.saved": "✓ Ayarlar kaydedildi",
        "settings.reset_defaults_title": "Varsayılan Ayarlara Sıfırla",
        "settings.reset_defaults_confirm": "Tüm ayarlar (görünüm, OCR, filtreler, kısayollar) varsayılan fabrika değerlerine döndürülecek ve eski önbellek temizlenecektir.\n(DeepL API anahtarınız ve seçilen oyun penceresi korunur).\n\nDevam etmek istiyor musunuz?",
        "settings.reset_defaults_success": "✓ Tüm ayarlar varsayılanlara sıfırlandı",

        # Sistem Tepsisi (Tray)
        "tray.pause": "⏸ Duraklat",
        "tray.resume": "▶ Devam Et",
        "tray.select_window": "🪟 Program İzle / Pencere Seç…",
        "tray.select_roi": "🎯 Altyazı Alanı Seç…",
        "tray.toggle_overlay": "👁 Altyazıyı Göster/Gizle",
        "tray.history": "📜 Çeviri Geçmişi…",
        "tray.settings": "⚙ Ayarlar…",
        "tray.quit": "❌ Çıkış",
        "tray.show_panel": "🎛️ Kontrol Merkezi",
        "control.title": "GameOCR — Kontrol Merkezi",
        "control.status_active": "Durum: Aktif",
        "control.status_paused": "Durum: Duraklatıldı",
        "control.lang_pair": "Dil: {src} → {tgt}",
        "control.backend": "Yakalama: {backend}",
        "control.hide_to_tray": "Simge Durumuna Küçült",
        "control.tip": "İpucu: Kısayol ({shortcut}) veya simge durumundan pencereyi geri açabilirsiniz; çarpı (×) programı kapatır.",
        "tray.paused_badge": "[DURAKLATILDI]",
        "tray.roi_saved": "Yeni altyazı alanı (ROI) kaydedildi.",

        # Ayarlar Penceresi - Sekmeler
        "settings.title": "GameOCR - Ayarlar",
        "tab.translator": "Çevirmen",
        "tab.cache": "Önbellek ve Geçmiş",
        "tab.appearance": "Görünüm",
        "tab.ocr": "Algılama ve OCR",
        "tab.hotkeys": "Kısayollar",

        # Ayarlar - Çevirmen Sekmesi
        "settings.ui_language": "Arayüz Dili:",
        "settings.translation_engine": "Çeviri Motoru:",
        "engine.deepl": "DeepL Bulut API (Yüksek Kalite)",
        "engine.local": "Çevrimdışı / Lokal Model (CTranslate2 / Argos)",
        "engine.auto_fallback": "Hibrit (DeepL + Çevrimdışı Otomatik Yedek)",
        "settings.lang_pair": "Dil Çifti (Kaynak → Hedef):",
        "settings.swap_langs": "Dilleri Değiştir",
        "settings.deepl_key": "DeepL API Anahtarı:",
        "settings.deepl_key_ph": "DEEPL_AUTH_KEY (Örn: xxxx:fx)",
        "settings.monthly_quota": "Aylık DeepL Kotası:",
        "settings.quota_loading": "Kota bilgisi alınıyor…",
        "settings.quota_failed": "Kota sorgulanamadı (Anahtarı kontrol edin)",
        "settings.quota_info": "Kalan: {remaining:,} / {limit:,} karakter (%{percent} kullanılabilir)\nKullanılan: {count:,} karakter",
        "settings.formality": "Çeviri Biçimselliği:",
        "formality.default": "Varsayılan (Doğal)",
        "formality.more": "Daha Resmi (Siz / Saygılı)",
        "formality.less": "Daha Samimi (Sen / Arkadaşça)",
        "formality.prefer_more": "Öncelikli Resmi",
        "formality.prefer_less": "Öncelikli Samimi",
        "settings.local_packs_title": "📦 Lokal Dil Paketleri (Çevrimdışı Çeviri):",
        "settings.pack_col_pair": "Dil Çifti",
        "settings.pack_col_size": "Boyut",
        "settings.pack_col_status": "Durum",
        "settings.pack_col_action": "İşlem",
        "settings.pack_installed": "✓ Kurulu",
        "settings.pack_not_installed": "İndirilmedi",
        "settings.pack_btn_download": "⬇ İndir",
        "settings.pack_btn_remove": "🗑 Kaldır",
        "settings.pack_downloading": "İndiriliyor ({pack}): %{pct}",
        "settings.pack_download_ok": "✓ {pack} dil paketi başarıyla kuruldu",
        "settings.pack_download_err": "✗ {pack} indirilemedi: {err}",

        # Ayarlar - Önbellek Sekmesi
        "settings.max_cache": "Maksimum Kayıt (LRU):",
        "settings.cache_status": "Önbellek Durumu:",
        "settings.cache_stats": "{count:,} kayıt · {size_mb:.2f} MB disk kullanımı",
        "settings.cache_unconnected": "Önbellek bağlı değil",
        "settings.view_history": "📜 Çeviri Geçmişini Görüntüle…",
        "settings.history_label": "Çeviri Geçmişi:",
        "settings.clear_cache": "Önbelleği Tamamen Temizle",
        "settings.clear_cache_title": "Önbelleği Temizle",
        "settings.clear_cache_prompt": "Tüm kayıtlı çeviri önbelleği silinecek. Emin misiniz?",

        # Ayarlar - Görünüm Sekmesi
        "settings.exact_alignment_label": "Dinamik Görsel Hizalama:",
        "settings.exact_alignment": "Tam Hizalama (Orijinal Metin Koordinatı, Boyutu ve Rengi)",
        "settings.match_font_size": "Orijinal yazı tipi boyutunu eşle (Bounding Box yüksekliği)",
        "settings.match_text_color": "Orijinal metin rengini örnekle (Otsu / Medyan analizi)",
        "settings.bg_effect": "Arka Plan Efekti:",
        "settings.blur_kwin": "KWin Buzlu Cam Bulanıklaştırması (Blur-Behind)",
        "settings.blur_strength": "Bulanıklık Seviyesi:",
        "settings.blur_level": "Seviye {v}",
        "settings.panel_opacity": "Panel Opaklığı:",
        "settings.opacity_transparent": "0% (Şeffaf)",
        "settings.text_shadow_label": "Metin Gölgesi:",
        "settings.text_shadow": "Yazı Arkasına Gölge Ekle (Okunabilirliği Artırır)",
        "settings.font_family": "Yazı Tipi (Font):",
        "settings.font_range": "Font Boyut Aralığı:",
        "settings.corner_radius": "Panel Köşe Yuvarlaklığı:",

        # Ayarlar - Algılama ve OCR Sekmesi
        "settings.target_window": "Hedef Oyun Penceresi:",
        "settings.btn_select_window": "🪟 Program İzle / Pencere Seç…",
        "settings.hw_device": "Donanım Hızlandırma (GPU / CPU):",
        "device.auto": "Otomatik (NVIDIA GPU varsa CUDA, yoksa CPU)",
        "device.gpu": "GPU Hızlandırma (NVIDIA CUDA)",
        "device.cpu": "Yalnızca İşlemci (CPU — AMD / Intel / Düşük Güç)",
        "settings.low_end_label": "Düşük Sistem Modu:",
        "settings.low_end_mode": "Düşük Donanım (Low-End) Optimizasyonu (CPU ve RAM yükünü azaltır)",
        "settings.fps": "Yakalama Hızı (FPS):",
        "settings.preprocess_mode": "Ön İşleme Modu:",
        "settings.stability_frames": "Kararlılık Kare Sayısı (Daktilo Koruması):",
        "settings.similarity_threshold": "Tekrar / Benzerlik Eşiği (%):",
        "settings.change_threshold": "Kare Değişim Eşiği (%):",
        "settings.log_level": "Log Seviyesi (Hata Ayıklama):",
        "settings.ocr_packs_title": "🔍 OCR Dil Paketleri (Metin Tanıma Modelleri):",
        "settings.ocr_pack_col_lang": "OCR Dil Paketi",
        "settings.ocr_pack_col_size": "Boyut",
        "settings.ocr_pack_col_status": "Durum",
        "settings.ocr_pack_col_action": "İşlem",
        "settings.ocr_pack_downloading": "OCR paketi indiriliyor ({pack}): %{pct}",
        "settings.ocr_pack_download_ok": "✓ {pack} OCR dil paketi başarıyla kuruldu",
        "settings.ocr_pack_download_err": "✗ {pack} OCR paketi indirilemedi: {err}",

        # Pencere Seçici (WindowPickerDialog)
        "winpicker.title": "GameOCR - Program İzle / Pencere Seç",
        "winpicker.search_ph": "Pencere başlığı veya uygulama sınıfı ara…",
        "winpicker.refresh": "↻ Yenile",
        "winpicker.pick_click": "🎯 Ekranda Tıklayarak Seç",
        "winpicker.col_id": "Pencere ID",
        "winpicker.col_title": "Pencere Başlığı",
        "winpicker.col_class": "Uygulama",
        "winpicker.col_size": "Çözünürlük",
        "winpicker.btn_select": "✓ Bu Pencereyi İzle",
        "winpicker.count_status": "{count} aktif pencere bulundu",
        "winpicker.selected_msg": "İzlenen oyun penceresi güncellendi (0x{wid:x}).",

        # Ayarlar - Kısayollar Sekmesi
        "settings.hotkeys_status": "Durum:",
        "settings.hotkeys_enable": "Global Kısayolları Etkinleştir",
        "settings.hotkey_pause": "Duraklat / Devam Et:",
        "settings.hotkey_roi": "Altyazı Alanı Seç (ROI):",
        "settings.hotkey_overlay": "Altyazıyı Göster / Gizle:",
        "settings.hotkey_history": "Çeviri Geçmişi:",
        "settings.hotkey_show_panel": "Kontrol Merkezi / Arayüz:",
        "settings.hotkeys_info": "💡 Kısayollar tam ekran oyunlar dahil sistem genelinde çalışır.\nVarsayılan tuş kombinasyonları (Ctrl+Alt+...) Linux masaüstüyle çakışmaz.",
        "hotkeys.record_prompt": "⌨ Tuşlara basın… (İptal: Esc)",
        "hotkeys.none": "— (Atanmadı) —",
        "hotkeys.clear": "Kısayolu Kaldır",

        # Çeviri Geçmişi Penceresi
        "history.title": "GameOCR - Çeviri Geçmişi",
        "history.search_ph": "Geçmişte ara (orijinal veya çevrilmiş metin)…",
        "history.col_time": "Zaman",
        "history.col_src_lang": "Kaynak Dil",
        "history.col_tgt_lang": "Hedef Dil",
        "history.col_source": "Orijinal Metin",
        "history.col_target": "Çeviri",
        "history.status": "Toplam {total:,} çeviri kaydı",
        "history.status_filtered": "{shown:,} / {total:,} kayıt gösteriliyor",
        "history.copied": "Kopyalandı: {text}",
        "history.clear_title": "Geçmişi Temizle",
        "history.clear_prompt": "Tüm çeviri geçmişi kalıcı olarak silinecek. Emin misiniz?",
        "history.empty": "Henüz kayıtlı çeviri geçmişi yok.",

        # ROI Seçici
        "roi.hint": "Altyazı alanını seçmek için sürükleyin · Onayla: Enter / Çift Tık · İptal: Esc",
    },

    "en": {
        # App General
        "app.name": "GameOCR",
        "app.tagline": "Real-time Game Subtitle Translator",
        "btn.save": "💾 Save",
        "btn.reset_defaults": "↺ Reset to Defaults",
        "btn.close": "Close",
        "btn.cancel": "Cancel",
        "btn.delete": "🗑 Delete Selected",
        "btn.clear_all": "Clear All",
        "btn.copy": "📋 Copy to Clipboard",
        "btn.verify_key": "🔍 Check Quota",
        "msg.saved": "✓ Settings saved",
        "settings.reset_defaults_title": "Reset to Defaults",
        "settings.reset_defaults_confirm": "All settings (appearance, OCR, filters, hotkeys) will be restored to factory default values and the cache will be cleared.\n(Your DeepL API key and game window will be preserved).\n\nDo you want to proceed?",
        "settings.reset_defaults_success": "✓ All settings restored to defaults",

        # Tray Menu
        "tray.pause": "⏸ Pause",
        "tray.resume": "▶ Resume",
        "tray.select_window": "🪟 Watch Program / Select Window…",
        "tray.select_roi": "🎯 Select Subtitle Area…",
        "tray.toggle_overlay": "👁 Show/Hide Overlay",
        "tray.history": "📜 Translation History…",
        "tray.settings": "⚙ Settings…",
        "tray.quit": "❌ Exit",
        "tray.show_panel": "🎛️ Control Center",
        "control.title": "GameOCR — Control Center",
        "control.status_active": "Status: Active",
        "control.status_paused": "Status: Paused",
        "control.lang_pair": "Language: {src} → {tgt}",
        "control.backend": "Capture: {backend}",
        "control.hide_to_tray": "Minimize",
        "control.tip": "Tip: Restore from the taskbar or with {shortcut}; closing (×) exits GameOCR.",
        "tray.paused_badge": "[PAUSED]",
        "tray.roi_saved": "New subtitle area (ROI) saved.",

        # Settings Dialog - Tabs
        "settings.title": "GameOCR - Settings",
        "tab.translator": "Translator",
        "tab.cache": "Cache & History",
        "tab.appearance": "Appearance",
        "tab.ocr": "Detection & OCR",
        "tab.hotkeys": "Hotkeys",

        # Settings - Translator Tab
        "settings.ui_language": "Interface Language:",
        "settings.translation_engine": "Translation Engine:",
        "engine.deepl": "DeepL Cloud API (High Quality)",
        "engine.local": "Offline / Local Model (CTranslate2 / Argos)",
        "engine.auto_fallback": "Hybrid (DeepL + Offline Auto-Fallback)",
        "settings.lang_pair": "Language Pair (Source → Target):",
        "settings.swap_langs": "Swap Languages",
        "settings.deepl_key": "DeepL API Key:",
        "settings.deepl_key_ph": "DEEPL_AUTH_KEY (e.g. xxxx:fx)",
        "settings.monthly_quota": "Monthly DeepL Quota:",
        "settings.quota_loading": "Loading quota info…",
        "settings.quota_failed": "Could not query quota (check API key)",
        "settings.quota_info": "Remaining: {remaining:,} / {limit:,} chars ({percent}% available)\nUsed: {count:,} chars",
        "settings.formality": "Translation Formality:",
        "formality.default": "Default (Natural)",
        "formality.more": "More Formal",
        "formality.less": "Less Formal / Informal",
        "formality.prefer_more": "Prefer More Formal",
        "formality.prefer_less": "Prefer Less Formal",
        "settings.local_packs_title": "📦 Local Language Packs (Offline Translation):",
        "settings.pack_col_pair": "Language Pair",
        "settings.pack_col_size": "Size",
        "settings.pack_col_status": "Status",
        "settings.pack_col_action": "Action",
        "settings.pack_installed": "✓ Installed",
        "settings.pack_not_installed": "Not Installed",
        "settings.pack_btn_download": "⬇ Download",
        "settings.pack_btn_remove": "🗑 Remove",
        "settings.pack_downloading": "Downloading ({pack}): {pct}%",
        "settings.pack_download_ok": "✓ {pack} language pack installed",
        "settings.pack_download_err": "✗ Failed to download {pack}: {err}",

        # Settings - Cache Tab
        "settings.max_cache": "Maximum Entries (LRU):",
        "settings.cache_status": "Cache Status:",
        "settings.cache_stats": "{count:,} entries · {size_mb:.2f} MB disk usage",
        "settings.cache_unconnected": "Cache not connected",
        "settings.view_history": "📜 View Translation History…",
        "settings.history_label": "Translation History:",
        "settings.clear_cache": "Clear Entire Cache",
        "settings.clear_cache_title": "Clear Cache",
        "settings.clear_cache_prompt": "All stored translations will be deleted. Are you sure?",

        # Settings - Appearance Tab
        "settings.exact_alignment_label": "Dynamic Visual Alignment:",
        "settings.exact_alignment": "Exact Alignment (Match Original X/Y Coordinates, Size & Color)",
        "settings.match_font_size": "Match original font size (from Bounding Box height)",
        "settings.match_text_color": "Sample original text color (Otsu / Median analysis)",
        "settings.bg_effect": "Background Effect:",
        "settings.blur_kwin": "KWin Frosted Glass Blur (Blur-Behind)",
        "settings.blur_strength": "Blur Strength:",
        "settings.blur_level": "Level {v}",
        "settings.panel_opacity": "Panel Opacity:",
        "settings.opacity_transparent": "0% (Transparent)",
        "settings.text_shadow_label": "Text Shadow:",
        "settings.text_shadow": "Add Text Shadow (Improves Readability)",
        "settings.font_family": "Font Family:",
        "settings.font_range": "Font Size Range:",
        "settings.corner_radius": "Panel Corner Radius:",

        # Settings - Detection & OCR Tab
        "settings.target_window": "Target Game Window:",
        "settings.btn_select_window": "🪟 Watch Program / Select Window…",
        "settings.hw_device": "Hardware Acceleration (GPU / CPU):",
        "device.auto": "Automatic (CUDA if NVIDIA GPU present, else CPU)",
        "device.gpu": "GPU Acceleration (NVIDIA CUDA)",
        "device.cpu": "CPU Only (AMD / Intel / Low Power)",
        "settings.low_end_label": "Low-Spec Mode:",
        "settings.low_end_mode": "Low-End Hardware Optimization (Reduces CPU & RAM usage)",
        "settings.fps": "Capture Rate (FPS):",
        "settings.preprocess_mode": "Preprocessing Mode:",
        "settings.stability_frames": "Stability Frames (Typewriter Guard):",
        "settings.similarity_threshold": "Similarity Threshold (%):",
        "settings.change_threshold": "Frame Change Threshold (%):",
        "settings.log_level": "Log Level (Debugging):",
        "settings.ocr_packs_title": "🔍 OCR Language Packs (Text Recognition Models):",
        "settings.ocr_pack_col_lang": "OCR Language Pack",
        "settings.ocr_pack_col_size": "Size",
        "settings.ocr_pack_col_status": "Status",
        "settings.ocr_pack_col_action": "Action",
        "settings.ocr_pack_downloading": "Downloading OCR pack ({pack}): {pct}%",
        "settings.ocr_pack_download_ok": "✓ {pack} OCR language pack installed",
        "settings.ocr_pack_download_err": "✗ Failed to download {pack} OCR pack: {err}",

        # Window Picker Dialog
        "winpicker.title": "GameOCR - Watch Program / Select Window",
        "winpicker.search_ph": "Search window title or application class…",
        "winpicker.refresh": "↻ Refresh",
        "winpicker.pick_click": "🎯 Click Window on Screen",
        "winpicker.col_id": "Window ID",
        "winpicker.col_title": "Window Title",
        "winpicker.col_class": "Application",
        "winpicker.col_size": "Resolution",
        "winpicker.btn_select": "✓ Watch This Window",
        "winpicker.count_status": "{count} active windows found",
        "winpicker.selected_msg": "Watched game window updated (0x{wid:x}).",

        # Settings - Hotkeys Tab
        "settings.hotkeys_status": "Status:",
        "settings.hotkeys_enable": "Enable Global Hotkeys",
        "settings.hotkey_pause": "Pause / Resume:",
        "settings.hotkey_roi": "Select Subtitle Area (ROI):",
        "settings.hotkey_overlay": "Show / Hide Overlay:",
        "settings.hotkey_history": "Translation History:",
        "settings.hotkey_show_panel": "Control Center / UI:",
        "settings.hotkeys_info": "💡 Hotkeys work system-wide including fullscreen games.\nDefault combinations (Ctrl+Alt+...) do not conflict with Linux desktop.",
        "hotkeys.record_prompt": "⌨ Press keys… (Esc to cancel)",
        "hotkeys.none": "— (None) —",
        "hotkeys.clear": "Remove Shortcut",

        # History Window
        "history.title": "GameOCR - Translation History",
        "history.search_ph": "Search history (source or translated text)…",
        "history.col_time": "Time",
        "history.col_src_lang": "Source",
        "history.col_tgt_lang": "Target",
        "history.col_source": "Source Text",
        "history.col_target": "Translation",
        "history.status": "Total {total:,} translation records",
        "history.status_filtered": "Showing {shown:,} / {total:,} records",
        "history.copied": "Copied: {text}",
        "history.clear_title": "Clear History",
        "history.clear_prompt": "All translation history will be permanently deleted. Are you sure?",
        "history.empty": "No translation history recorded yet.",

        # ROI Selector
        "roi.hint": "Drag to select subtitle area · Confirm: Enter / Double Click · Cancel: Esc",
    },
}


def set_language(lang_code: str) -> None:
    """Aktif arayüz dilini ayarlar."""
    global _CURRENT_LANG
    lang = (lang_code or "tr").lower().strip()
    if lang in TRANSLATIONS:
        _CURRENT_LANG = lang
    else:
        log.warning("Desteklenmeyen arayüz dili: %s (tr varsayılanı kullanılıyor)", lang_code)
        _CURRENT_LANG = "tr"


def get_language() -> str:
    """Mevcut arayüz dili kodunu döndürür ('tr' veya 'en')."""
    return _CURRENT_LANG


def t(key: str, **kwargs: Any) -> str:
    """Verilen anahtara karşılık gelen yerelleştirilmiş metni döndürür.
    
    Aktif dilde bulunamazsa 'tr' diline, orada da yoksa doğrudan key'e düşer.
    Format değişkenleri kwargs ile desteklenir.
    """
    lang_dict = TRANSLATIONS.get(_CURRENT_LANG, TRANSLATIONS["tr"])
    text = lang_dict.get(key)
    if text is None:
        text = TRANSLATIONS["tr"].get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text
