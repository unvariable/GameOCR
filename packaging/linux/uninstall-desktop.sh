#!/usr/bin/env bash
# GameOCR Linux Masaüstü (.desktop) ve Hicolor İkon Kaldırma Betiği
set -euo pipefail

DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
APPS_DIR="$DATA_HOME/applications"
ICON_THEME_DIR="$DATA_HOME/icons/hicolor"

rm -f "$APPS_DIR/gameocr.desktop"
for size in 24 32 64 128 256 512 1024; do
    rm -f "$ICON_THEME_DIR/${size}x${size}/apps/gameocr.png"
done

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t "$ICON_THEME_DIR" >/dev/null 2>&1 || true
fi
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APPS_DIR" >/dev/null 2>&1 || true
fi

echo "GameOCR masaüstü girişi ve ikonları kaldırıldı: $DATA_HOME"
