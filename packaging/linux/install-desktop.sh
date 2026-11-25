#!/usr/bin/env bash
# GameOCR Linux Masaüstü (.desktop) ve Hicolor İkon Kurulum Betiği
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
APPS_DIR="$DATA_HOME/applications"
ICON_THEME_DIR="$DATA_HOME/icons/hicolor"
EXEC_CMD="gameocr"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --exec)
            EXEC_CMD="${2:-gameocr}"
            shift 2
            ;;
        -h|--help)
            echo "Kullanım: $0 [--exec <komut_veya_yol>]"
            exit 0
            ;;
        *)
            echo "Bilinmeyen seçenek: $1" >&2
            exit 1
            ;;
    esac
done

ICON_SRC_DIR="$PROJECT_ROOT/gameocr/assets/icons"
if [[ ! -d "$ICON_SRC_DIR" ]]; then
    ICON_SRC_DIR="$PROJECT_ROOT/logo"
fi

for size in 24 32 64 128 256 512 1024; do
    src_png="$ICON_SRC_DIR/logo_${size}.png"
    if [[ -f "$src_png" ]]; then
        dst_dir="$ICON_THEME_DIR/${size}x${size}/apps"
        mkdir -p "$dst_dir"
        cp -f "$src_png" "$dst_dir/gameocr.png"
    fi
done

mkdir -p "$APPS_DIR"
ESCAPED_EXEC="${EXEC_CMD//&/\\&}"
sed "s|^Exec=.*|Exec=${ESCAPED_EXEC}|" "$SCRIPT_DIR/gameocr.desktop" > "$APPS_DIR/gameocr.desktop"
chmod 644 "$APPS_DIR/gameocr.desktop"

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t "$ICON_THEME_DIR" >/dev/null 2>&1 || true
fi
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APPS_DIR" >/dev/null 2>&1 || true
fi

echo "GameOCR masaüstü girişi ve ikonları kuruldu: $APPS_DIR/gameocr.desktop"
