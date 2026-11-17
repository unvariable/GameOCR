# Contributing to GameOCR

Thank you for your interest in contributing to **GameOCR**! Please follow these guidelines to keep the codebase clean, secure, and accessible.

## Development Setup

GameOCR uses **Python 3.12** (`>=3.12, <3.13`) and [`uv`](https://docs.astral.sh/uv/) for dependency management.

```bash
git clone https://github.com/unvariable/GameOCR.git
cd GameOCR
uv sync
```

Run the application from source:

```bash
uv run python -m gameocr
```

## Running Tests

Always run the full test suite before opening a pull request:

```bash
uv run pytest -v
```

> Note: GUI tests run cleanly in headless environments using `QT_QPA_PLATFORM=offscreen`.

## Coding, Security & Privacy Standards

1. **Type Annotations & Style:** Use `from __future__ import annotations` and explicit type hints for all functions and methods.
2. **Internationalization (i18n):** Every user-facing string must be added to both `tr` and `en` dictionaries in `gameocr/i18n.py`.
3. **Thread Safety:** Never manipulate Qt widgets from background worker threads; communicate via `ui_q` or `pyqtSignal`.
4. **Security & Privacy:**
   - Never commit personal file paths, API keys (e.g., DeepL keys), `.env` files, or large binary artifacts.
   - Use `gameocr/security.py` helpers (`validate_https_url`, `safe_extract_zip`, `harden_private_path`, `redact_secrets`) for any network downloads, archive extraction, private file writes, or logging.
   - Never use `eval()`, `exec()`, `pickle.loads()`, `shell=True`, or unvalidated `http://` downloads.
5. **Testing & Changelog:** Add or update unit tests in `tests/` for bug fixes or new features, and update `CHANGELOG.md` for user-facing changes.

## Pull Request Process

1. Fork the repository and create a descriptive branch from `main` (e.g., `fix/wayland-focus`, `feat/new-ocr-pack`).
2. Keep pull requests focused on a single concern and link any related issue.
3. Verify that `uv run pytest -v` passes with zero failures.
4. Complete all items in the [Pull Request Template](.github/PULL_REQUEST_TEMPLATE.md).

## Reporting Bugs & Suggesting Features

Please use the GitHub [Issue Templates](.github/ISSUE_TEMPLATE/) when reporting bugs or requesting features. Include:
- Your OS and desktop environment (e.g., KDE Plasma Wayland, Linux Mint Cinnamon X11, Windows 10/11)
- GameOCR version (`gameocr.__version__`)
- Relevant log excerpts (API keys are automatically redacted):
  - Linux: `~/.local/share/gameocr/logs/gameocr.log`
  - Windows: `%LOCALAPPDATA%\gameocr\logs\gameocr.log`
