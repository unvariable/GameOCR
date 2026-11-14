# 📖 GameOCR Technical Documentation (English)

Welcome to the architectural, operational, and developer documentation for **GameOCR**.

## 📚 Table of Contents

1. [**Architecture & Pipeline (`architecture.md`)**](architecture.md)
   - Multi-threaded worker pipeline, inter-thread queues (`frame_q`, `text_q`, `translate_q`, `ui_q`), `TextStyleMeta` visual alignment flow, and `StageError` debugging telemetry.
2. [**Wayland vs. X11 Display Server Differences (`display_servers.md`)**](display_servers.md)
   - How `xdg-desktop-portal` + PipeWire (Wayland) and `XComposite` + `xwininfo` (X11) operate, why `QT_QPA_PLATFORM=xcb` is used on Linux, and how dynamic window selection (`WindowPickerDialog`) works.
3. [**Offline (Local) Translation Engine & Memory Management (`local_translation.md`)**](local_translation.md)
   - How `LocalModelManager` manages CTranslate2 / Argos Translate models in memory, why only `EN-TR` comes pre-installed by default, and how `ModelDownloadWorker(QThread)` downloads language packs without freezing the UI.
4. [**Smart Interactive Build Script (`building.md`)**](building.md)
   - How to compile standalone executables using `./build.sh` with interactive wizard prompts or CLI flags (`--de`, `--display`, `--gpu`, `--compiler`).
5. [**Windows Port (Beta) & Limitations (`windows_port.md`)**](windows_port.md)
   - How `Win32Backend`, `SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)`, `DwmEnableBlurBehindWindow`, and `RegisterHotKey` work on Windows, along with known Beta limitations.

---

> 🇹🇷 Türkçe dokümantasyon için: [`../tr/README.md`](../tr/README.md)

