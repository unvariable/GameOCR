# Accessibility Statement — GameOCR

GameOCR aims to make non-native games and visual media more accessible through real-time subtitle OCR and translation.

## Built-in Accessibility Features

- **Dynamic Visual Alignment & Readability:** Translated text can either match the original subtitle font size, color, and position (`exact_alignment`), or render in a high-contrast centered overlay panel with configurable opacity, font family, minimum/maximum font size, and text drop-shadow.
- **Click-Through Non-Intrusive Overlay:** The overlay window never steals focus or blocks mouse/keyboard input to the underlying game.
- **Keyboard Shortcuts:** Global hotkeys allow pausing (`Ctrl+Alt+P`), selecting the subtitle region (`Ctrl+Alt+S`), toggling overlay visibility (`Ctrl+Alt+O`), opening translation history (`Ctrl+Alt+H`), and bringing up the Control Center (`Ctrl+Alt+G`).
- **Offline Translation & Multi-Language UI:** Supports bilingual UI (Turkish / English) and offline neural machine translation without requiring an internet connection.

## Known Limitations

- Global X11/Win32 hotkeys require keyboard input; screen-reader integration for the transparent click-through overlay itself is currently limited.
- Extremely stylized or low-contrast bitmap fonts in games may reduce OCR recognition accuracy.

## Feedback

If you encounter accessibility barriers while using GameOCR, please open an issue on GitHub so we can improve support.
