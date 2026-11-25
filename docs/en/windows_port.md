# 🪟 Windows 10/11 Architecture & Platform Notes

GameOCR runs as a full-featured native desktop release on Windows 10 (2004+) and Windows 11, pairing its cross-platform OCR/translation pipeline with native Win32 (`user32`, `gdi32`, `dwmapi`) and `DXcam`/`MSS` subsystems when `sys.platform == "win32"`.

---

## 1. Windows Subsystem Mapping

| Subsystem | Linux Implementation | Windows 10/11 Implementation |
| :--- | :--- | :--- |
| **Qt QPA Plugin** | Forced `QT_QPA_PLATFORM=xcb` | Native Qt `windows` platform plugin |
| **Screen & Window Capture** | `PortalBackend` / `XCompositeBackend` | `Win32Backend` (`PrintWindow` isolated window capture, Z-order occlusion guard, `DXcam` on primary monitor or `MSS` fallback) |
| **Self-Capture Exclusion** | PipeWire window stream / XComposite offscreen pixmap | `user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)` (`0x11`) + `setMask(QRegion)` / `LWA_COLORKEY` |
| **Blur-Behind HUD** | `_KDE_NET_WM_BLUR_BEHIND_REGION` X11 atom | `dwmapi.DwmEnableBlurBehindWindow` in `gameocr/ui/blur.py` (Settings shows Win32 DWM label and hides KWin slider) |
| **Click-Through & Transparent Mode** | `WindowTransparentForInput` + `WindowStaysOnTopHint` | `user32.SetWindowLongW` (`WS_EX_LAYERED \| WS_EX_TRANSPARENT \| WS_EX_TOOLWINDOW \| WS_EX_NOACTIVATE`) + `HWND_TOPMOST`; `LWA_COLORKEY \| LWA_ALPHA` (`#010101`) when `opacity <= 0.01` |
| **Global Hotkeys** | Wayland UDP / X11 `grab_key` | `user32.RegisterHotKey(MOD_NOREPEAT)` + `PeekMessageW` listener thread (`Ctrl+Alt+G` & extended `_WIN32_NAMED_VK` keys supported) |
| **Window Picker & Window ROI** | Portal / `xwininfo` + X11 `_NET_CLIENT_LIST` | `user32.EnumWindows` with `IsIconic` & `DWMWA_CLOAKED` filtering + window-relative ROI (`PrintWindow` & `roi.window_unavailable` guard) |
| **Single-Instance IPC & Taskbar Identity** | UID-scoped `QLocalServer` + `.desktop` | Deterministic `USERDOMAIN\USERNAME` `SHA-256` `QLocalServer` + `SetCurrentProcessExplicitAppUserModelID` + PE `RT_GROUP_ICON` |
| **Multi-Monitor & High-DPI** | XRandR / Qt logical coordinates | `EnumDisplayMonitors` + `QScreen` mapping (`win32_physical_rect_to_qt_logical`) + `line_height_px / dpr` + primary-monitor-scoped `dxcam` |
| **Safe Atomic I/O & Settings UI** | POSIX atomic `os.replace` | `atomic_replace()` with `PermissionError` retries, async DeepL quota fetch, and `_detach_running_worker()` close guard |

---

## 2. Platform Notes on Windows

1. **Exclusive Fullscreen (DirectX 9/11 Exclusive Mode):**
   - When a game runs in legacy *Exclusive Fullscreen* mode, it takes direct ownership of the display swapchain, preventing standard Win32 `HWND_TOPMOST` windows from rendering on top of the game.
   - **Workaround:** Set the game to **Borderless Windowed (Windowed Fullscreen)** mode so Windows DWM composites the GameOCR HUD overlay cleanly over the game.
2. **Windows Version Requirement for `WDA_EXCLUDEFROMCAPTURE`:**
   - `WDA_EXCLUDEFROMCAPTURE` (`0x11`) requires **Windows 10 version 2004 (Build 19041)** or newer (including all Windows 11 builds). On older Windows 10 builds, the overlay may appear black or in screen captures if it overlaps the ROI.
3. **Anti-Cheat Compatibility:**
   - GameOCR never injects DLLs or hooks into game processes (`ReadProcessMemory` or DirectX hooking is never used). It only captures pixels via standard desktop APIs (`PrintWindow`/`DXcam`/`MSS`).

