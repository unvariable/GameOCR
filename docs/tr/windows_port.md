# 5. Windows Portu (Beta) Mimarisi ve Limitasyonları

GameOCR, Linux odaklı mimarisini korurken Windows 10 (2004+) ve Windows 11 sistemlerde de çalışabilmesi için yerel Win32 / DWM yedek (fallback) katmanlarıyla donatılmıştır.

## 5.1. Windows Alt Sistem Karşılıkları

| Bileşen | Linux Mimarisi | Windows (Beta) Karşılığı |
| :--- | :--- | :--- |
| **Qt Platform Eklentisi** | `QT_QPA_PLATFORM=xcb` | Yerel Qt `windows` QPA eklentisi (`sys.platform == "win32"` otomatik algılanır) |
| **Yapılandırma & Veri Dizinleri** | `~/.config/gameocr` & `~/.local/share/gameocr` | `%APPDATA%\GameOCR` & `%LOCALAPPDATA%\GameOCR` |
| **Ekran / Pencere Yakalama** | `PortalBackend` / `XCompositeBackend` | `Win32Backend` (`dxcam` Desktop Duplication veya `mss` + `GetWindowRect`) |
| **Self-Capture Engelleme** | XComposite ekran dışı pixmap | `user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)` (`0x11`) |
| **Arka Plan Bulanıklığı (Blur)** | KWin `_KDE_NET_WM_BLUR_BEHIND_REGION` | `dwmapi.DwmEnableBlurBehindWindow` |
| **Tıklama Geçirgenliği & Üstte Tutma** | Qt Flags + `_NET_WM_STATE_ABOVE` + KWin Rules | `SetWindowLongW(WS_EX_LAYERED \| WS_EX_TRANSPARENT)` + `SetWindowPos(HWND_TOPMOST)` |
| **Global Kısayollar** | KWin UDP + X11 `root.grab_key` | `user32.RegisterHotKey` + `PeekMessageW` dinleyici thread'i |
| **Dinamik Pencere Seçici** | `xdg-desktop-portal` / `xwininfo` | `user32.EnumWindows` + `GetWindowTextW` (`WindowPickerDialog`) |

## 5.2. Bilinen Limitasyonlar (Beta Sürüm)

1. **Exclusive Fullscreen (Tam Ekran Özel Mod) Oyunlar:**
   - DirectX 11/12 veya Vulkan oyunları "Exclusive Fullscreen" modunda çalıştığında Windows DWM kompozitörünü devre dışı bırakabilir. Bu durumda şeffaf PyQt6 overlay penceresi oyunun altında kalabilir.
   - **Çözüm:** Oyunların grafik ayarlarından **"Borderless Windowed" (Çerçevesiz Pencere)** modunun seçilmesi önerilir.
2. **Windows Sürüm Gereksinimi (`WDA_EXCLUDEFROMCAPTURE`):**
   - Overlay'in kendi ekran görüntüsüne girmesini titremesiz engelleyen `WDA_EXCLUDEFROMCAPTURE` bayrağı **Windows 10 sürüm 2004 (Build 19041)** ve sonrasında desteklenir. Daha eski Windows 10 sürümlerinde bu bayrak pencereyi siyah gösterebilir.
3. **Anti-Cheat (Hile Koruması) Yazılımları:**
   - Kernel düzeyinde çalışan bazı anti-cheat sistemleri (Vanguard, BattleEye vb.) `SetWindowPos(HWND_TOPMOST)` veya `dxcam` Desktop Duplication API çağrılarını kısıtlayabilir. Bu durumda `mss` yedek yakalayıcısı devreye girer.

