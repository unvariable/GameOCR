# 🪟 Windows Port (Beta) Architecture & Limitations

GameOCR includes a cross-platform Windows Beta layer that replaces Linux-specific X11/Wayland/KWin APIs with native Win32 (`user32`, `dwmapi`) and `MSS`/`DXcam` equivalents when `sys.platform == "win32"`.

---

## 1. Windows Subsystem Mapping

| Subsystem | Linux Implementation | Windows Beta Implementation |
| :--- | :--- | :--- |
| **Qt QPA Plugin** | Forced `QT_QPA_PLATFORM=xcb` | Native Qt `windows` platform plugin |
| **Screen Capture (`capture`)** | `PortalBackend` / `XCompositeBackend` | `Win32Backend` (`gameocr/capture/win32_backend.py`) using `DXcam` (Direct3D 11 Desktop Duplication) or `MSS` fallback |
| **Self-Capture Exclusion** | PipeWire window stream / XComposite offscreen pixmap | `user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)` (`0x00000011`) on Windows 10 2004+ / Windows 11 |
| **Blur-Behind HUD** | `_KDE_NET_WM_BLUR_BEHIND_REGION` X11 atom | `dwmapi.DwmEnableBlurBehindWindow` + `SetWindowCompositionAttribute` (Acrylic) in `gameocr/ui/blur.py` |
| **Click-Through & Topmost** | `WindowTransparentForInput` + `WindowStaysOnTopHint` | `user32.SetWindowLongW` (`WS_EX_LAYERED \| WS_EX_TRANSPARENT \| WS_EX_TOPMOST \| WS_EX_TOOLWINDOW`) + `SetWindowPos(HWND_TOPMOST)` |
| **Global Hotkeys** | Wayland UDP / X11 `grab_key` | `user32.RegisterHotKey` + `GetMessageW` listener thread in `gameocr/ui/hotkeys.py` |
| **Window Picker** | Portal / `xwininfo` + X11 `_NET_CLIENT_LIST` | `user32.EnumWindows` + `GetWindowTextW` (`list_win32_windows`) |

---

## 2. Known Beta Limitations on Windows

1. **Exclusive Fullscreen (DirectX 9/11 Exclusive Mode):**
   - When a game runs in legacy *Exclusive Fullscreen* mode, it takes direct ownership of the display swapchain, preventing standard Win32 `HWND_TOPMOST` windows from rendering on top of the game.
   - **Workaround:** Set the game to **Borderless Windowed (Windowed Fullscreen)** mode so Windows DWM composites the GameOCR HUD overlay cleanly over the game.
2. **Windows Version Requirement for `WDA_EXCLUDEFROMCAPTURE`:**
   - `WDA_EXCLUDEFROMCAPTURE` (`0x11`) requires **Windows 10 version 2004 (Build 19041)** or newer (including all Windows 11 builds). On older Windows 10 builds, the overlay may appear in screen captures if it overlaps the ROI.
3. **Anti-Cheat Compatibility:**
   - GameOCR never injects DLLs or hooks into game processes (`ReadProcessMemory` or DirectX hooking is never used). It only captures screen pixels via standard desktop APIs (`DXcam`/`MSS`).

