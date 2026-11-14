# 🖥️ Wayland vs. X11 Display Server Architecture

GameOCR runs on both **Wayland** and **X11** desktop environments on Linux (as well as Windows Beta) by automatically detecting `$XDG_SESSION_TYPE` and adapting its screen capture, window selection, blur-behind, and global hotkey backends.

---

## 1. Comparison Matrix

| Feature | Wayland (`XDG_SESSION_TYPE=wayland`) | X11 (`XDG_SESSION_TYPE=x11`) |
| :--- | :--- | :--- |
| **Frame Capture (`capture`)** | `xdg-desktop-portal` (`org.freedesktop.portal.ScreenCast`) + PipeWire / GStreamer (`PortalBackend`) | `XComposite` offscreen window pixmap (`XCompositeBackend`) or `MSS` (`MssBackend`) |
| **Self-Capture Prevention** | Captures the isolated window stream selected in the Portal; never captures the HUD overlay | Captures the target window's XID offscreen buffer directly via `XCompositeNameWindowPixmap` |
| **Dynamic Window Selection** | Re-invokes the native compositor Portal window picker dialog (`RESELECT_WINDOW`) | Opens `WindowPickerDialog` with searchable X11 window list + `xwininfo` crosshair click-to-pick |
| **Qt Platform Plugin** | Runs under `QT_QPA_PLATFORM=xcb` (XWayland bridge) | Native `xcb` |
| **Blur-Behind Effect** | `_KDE_NET_WM_BLUR_BEHIND_REGION` X11 atom via XWayland -> KWin | `_KDE_NET_WM_BLUR_BEHIND_REGION` X11 atom |
| **Global Hotkeys** | KDE Plasma global shortcut -> local UDP socket (`127.0.0.1:49281`) | `python-xlib` `root.grab_key` across all NumLock/CapsLock/AltGr masks |

---

## 2. Why `QT_QPA_PLATFORM=xcb` is Used on Linux

On Wayland compositors, pure Wayland client windows are intentionally restricted from:
1. Positioning themselves at arbitrary global `(X, Y)` screen coordinates,
2. Setting click-through input masks (`WindowTransparentForInput`) reliably across all compositors,
3. Writing the `_KDE_NET_WM_BLUR_BEHIND_REGION` property directly.

By setting `os.environ.setdefault("QT_QPA_PLATFORM", "xcb")` on Linux in `gameocr/__main__.py`, the HUD overlay runs through XWayland while `PortalBackend` still communicates natively with the Wayland compositor over D-Bus (`dbus-fast`) and PipeWire for zero-flicker window capture.

---

## 3. Dynamic Window Selection (`gameocr/ui/window_picker.py`)

Users can switch the watched game window at any time from:
- **System Tray Menu:** `🎯 Watch Program / Select Window...`
- **Settings Dialog -> Capture Tab:** `🎯 Watch Program / Select Window...`

### Behavior by Session Type:
- **Wayland:** Sends `ControlKind.RESELECT_WINDOW` to `CaptureWorker`, which closes the active PipeWire stream and opens the system's native `xdg-desktop-portal` window/screen selector.
- **X11:** Opens `WindowPickerDialog`, listing all active top-level application windows (`_NET_CLIENT_LIST`) with search filtering and a **"🎯 Click on Window to Pick (Crosshair)"** button powered by `xwininfo` / X11 pointer grab.

