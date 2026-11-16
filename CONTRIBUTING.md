# Contributing to GameOCR

Thank you for your interest in contributing to **GameOCR**!

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

## Pull Request Guidelines

1. Keep changes focused and well-tested.
2. Add or update unit tests in `tests/` for any bug fixes or new features.
3. Ensure all UI strings are added to both `tr` and `en` dictionaries in `gameocr/i18n.py`.
4. Never commit personal paths, API keys (e.g., DeepL keys), `.env` files, or large binary artifacts. Run `./publish_github.sh --check-only` to verify before submitting.
5. Update `CHANGELOG.md` when introducing user-facing changes.

## Reporting Bugs & Suggesting Features

Please use the GitHub [Issue Templates](.github/ISSUE_TEMPLATE/) when reporting bugs or requesting features. Include your OS/desktop environment (e.g., KDE Plasma Wayland, Linux Mint Cinnamon X11, Windows 10/11) and relevant log excerpts from:
- Linux: `~/.local/share/gameocr/logs/gameocr.log`
- Windows: `%LOCALAPPDATA%\gameocr\logs\gameocr.log`
