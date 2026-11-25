# 2. Wayland ve X11 Davranış Farkları & Dinamik Pencere Seçimi

Linux masaüstlerinde görüntü sunucusu mimarisi pencere yakalama, şeffaf katman konumlandırma ve global kısayolları doğrudan etkiler. GameOCR oturum tipini (`XDG_SESSION_TYPE`) otomatik algılar.

## 2.1. Wayland ve X11 Karşılaştırma Tablosu

| Özellik | Wayland (KDE Plasma 6 / GNOME) | X11 (KWin / Mutter / XFCE) |
| :--- | :--- | :--- |
| **Pencere Yakalama** | `PortalBackend` (`xdg-desktop-portal` ScreenCast + PipeWire/GStreamer) veya XWayland oyunları için `XCompositeBackend` | `XCompositeBackend` (`composite_name_window_pixmap`) veya yedek olarak `MssBackend` |
| **Dinamik Pencere Seçimi** | `xdg-desktop-portal` yerel sistem pencere seçici diyaloğu (`restore_token` destekli) | `WindowPickerDialog` (`python-xlib` / `xwininfo` pencere tablosu + `xdotool` Crosshair tıklama) |
| **Overlay Konumlandırma** | `QT_QPA_PLATFORM=xcb` (XWayland köprüsü) ile mutlak ekran koordinatı ve tıklama geçirgenliği | Doğrudan X11/XCB mutlak koordinat ve `_NET_WM_STATE_ABOVE` |
| **Self-Capture (Kendi Kendini Yakalama) Koruması** | PipeWire pencere akışı ve XComposite pixmap'i overlay'i içermez | XComposite pixmap'i overlay'i içermez (`MssBackend` yedeğinde `_NET_WM_WINDOW_OPACITY` gizlemesi kullanılır) |
| **Global Kısayollar** | KWin `kglobalshortcutsrc` + yerel UDP soketi (`127.0.0.1:49281`) + XWayland `grab_key` | `root.grab_key` (NumLock, CapsLock, AltGr maske kombinasyonlarıyla) |

## 2.2. Neden Wayland Altında `QT_QPA_PLATFORM=xcb` Kullanılır?

Saf Wayland protokolünde istemci pencerelerin kendi mutlak `(X, Y)` ekran koordinatlarını belirlemesine ve doğrudan `_KDE_NET_WM_BLUR_BEHIND_REGION` atomu yazmasına güvenlik gerekçesiyle izin verilmez. GameOCR, Linux üzerinde `QT_QPA_PLATFORM=xcb` tanımlayarak overlay penceresini XWayland üzerinden çalıştırır. Bu sayede:
1. Tam ekran Proton/Wine/Steam oyunlarının üzerinde milimetrik `(X, Y)` koordinat hizalaması yapılabilir.
2. `WindowTransparentForInput` ile fare tıklamaları %100 oyuna geçer.
3. KWin buzlu cam (blur-behind) atomu sorunsuz çalışır.

## 2.3. Dinamik Pencere Seçimi ("Program İzle / Pencere Seç…") ve Kontrol Merkezi

- **Evrensel Kontrol Merkezi (`ControlWindow`, `Ctrl+Alt+G`) & `.desktop` İkonu:** Linux'ta `QIcon.fromTheme("gameocr")` + `setDesktopFileName("gameocr")` ile GNOME/Cinnamon/KDE sistem tepsisi ve görev çubuğu ikonları doğru eşlenir (`./packaging/linux/install-desktop.sh` ile menüye kurulabilir).
- Sistem tepsisinden veya **Kontrol Merkezi / Ayarlar → Algılama ve OCR** sekmesinden **"🪟 Program İzle / Pencere Seç…"** butonuna basıldığında:
  - **Wayland Oturumunda:** Mevcut `portal_restore_token` sıfırlanır ve `xdg-desktop-portal` üzerinden masaüstü ortamının güvenli pencere/ekran seçicisi açılır.
  - **X11 Oturumunda:** Açık pencerelerin başlıklarını, uygulama sınıflarını (`WM_CLASS`), çözünürlüklerini ve XID kimliklerini listeleyen `WindowPickerDialog` açılır. Kullanıcı listeden arama yapıp çift tıklayabilir veya **"🎯 Ekranda Tıklayarak Seç"** butonuyla doğrudan oyun penceresinin üzerine tıklayabilir.

