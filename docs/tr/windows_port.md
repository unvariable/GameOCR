# 5. Windows 10/11 Mimarisi ve Platform Özellikleri

GameOCR, Linux mimarisiyle tam uyumlu şekilde Windows 10 (2004+) ve Windows 11 sistemlerde yerel Win32 / DWM katmanlarıyla tam sürüm olarak çalışır.

## 5.1. Windows Alt Sistem Karşılıkları

| Bileşen | Linux Mimarisi | Windows 10/11 Karşılığı |
| :--- | :--- | :--- |
| **Qt Platform Eklentisi** | `QT_QPA_PLATFORM=xcb` | Yerel Qt `windows` QPA eklentisi (`sys.platform == "win32"` otomatik algılanır) |
| **Yapılandırma & Veri Dizinleri** | `~/.config/gameocr` & `~/.local/share/gameocr` | `%APPDATA%\GameOCR` & `%LOCALAPPDATA%\GameOCR` |
| **Ekran / Pencere Yakalama** | `PortalBackend` / `XCompositeBackend` | `Win32Backend` (`PrintWindow` izole pencere yakalama, Z-order örtülme koruması, birincil ekranda `dxcam` veya `mss`) |
| **Self-Capture Engelleme** | XComposite ekran dışı pixmap | `user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)` (`0x11`) + `setMask(QRegion)` / `LWA_COLORKEY` |
| **Arka Plan Bulanıklığı (Blur)** | KWin `_KDE_NET_WM_BLUR_BEHIND_REGION` | `dwmapi.DwmEnableBlurBehindWindow` (Ayarlar'da Windows etiketi gösterilir, KWin kaydırıcısı gizlenir) |
| **Tıklama Geçirgenliği & Şeffaf Mod** | Qt Flags + `_NET_WM_STATE_ABOVE` + KWin Rules | `SetWindowLongW(WS_EX_LAYERED \| WS_EX_TRANSPARENT \| WS_EX_NOACTIVATE)` + `HWND_TOPMOST`; `opacity <= 0.01` standart modda `LWA_COLORKEY \| LWA_ALPHA` (`#010101`) |
| **Global Kısayollar** | KWin UDP + X11 `root.grab_key` | `user32.RegisterHotKey(MOD_NOREPEAT)` + `PeekMessageW` dinleyici thread'i (`Ctrl+Alt+G` dahil) + ek sanal tuşlar (`_WIN32_NAMED_VK`) |
| **Dinamik Pencere Seçici & ROI** | `xdg-desktop-portal` / `xwininfo` | `user32.EnumWindows` + `DWMWA_CLOAKED` / `IsIconic` filtresi (`WindowPickerDialog`) + `PrintWindow` pencere-göreli ROI seçimi (`roi.window_unavailable` koruması) |
| **Tek Örnek IPC & Görev Çubuğu Kimliği** | Kullanıcı UID bazlı `QLocalServer` + `.desktop` | `USERDOMAIN\USERNAME` `SHA-256` tabanlı deterministik `QLocalServer` + `SetCurrentProcessExplicitAppUserModelID` + PE `RT_GROUP_ICON` |
| **Çoklu Monitör & Yüksek DPI** | XRandR / Qt mantıksal piksel | `EnumDisplayMonitors` + `QScreen` eşleşmesi (`win32_physical_rect_to_qt_logical`) + `line_height_px / devicePixelRatio` + birincil ekranla sınırlı `dxcam` |
| **Güvenli Ayar / Model Yazımı** | `os.replace` atomik yazım | `atomic_replace()` (`PermissionError` yeniden denemeli), asenkron DeepL kota sorgusu ve `_detach_running_worker()` kapatma koruması |

## 5.2. Bilinen Platform Notları

1. **Exclusive Fullscreen (Tam Ekran Özel Mod) Oyunlar:**
   - DirectX 11/12 veya Vulkan oyunları "Exclusive Fullscreen" modunda çalıştığında Windows DWM kompozitörünü devre dışı bırakabilir. Bu durumda şeffaf PyQt6 overlay penceresi oyunun altında kalabilir.
   - **Çözüm:** Oyunların grafik ayarlarından **"Borderless Windowed" (Çerçevesiz Pencere)** modunun seçilmesi önerilir.
2. **Windows Sürüm Gereksinimi (`WDA_EXCLUDEFROMCAPTURE`):**
   - Overlay'in kendi ekran görüntüsüne girmesini titremesiz engelleyen `WDA_EXCLUDEFROMCAPTURE` bayrağı **Windows 10 sürüm 2004 (Build 19041)** ve sonrasında desteklenir. Daha eski Windows 10 sürümlerinde bu bayrak pencereyi siyah gösterebilir.
3. **Anti-Cheat (Hile Koruması) Yazılımları:**
   - GameOCR hiçbir oyun sürecine DLL enjekte etmez veya bellek okumaz; yalnızca standart masaüstü API'leri (`PrintWindow`/`DXcam`/`MSS`) üzerinden piksel okur. Bazı kernel düzeyindeki anti-cheat yazılımları `HWND_TOPMOST` veya `dxcam` erişimini kısıtlarsa otomatik olarak `mss` yedeği devreye girer.

