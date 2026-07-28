#!/bin/bash
# Installs a "ShoppingAgent" launcher: app-menu entry + optional Desktop icon.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ICON_DIR="$HOME/.local/share/icons/hicolor/128x128/apps"
APPS_DIR="$HOME/.local/share/applications"
DESKTOP_FILE="ShoppingAgent.desktop"

mkdir -p "$ICON_DIR" "$APPS_DIR"
cp "$DIR/shopping-agent-icon.png" "$ICON_DIR/shopping-agent.png"
cp "$DIR/$DESKTOP_FILE" "$APPS_DIR/$DESKTOP_FILE"
chmod +x "$APPS_DIR/$DESKTOP_FILE"

# Refresh icon/desktop caches if the tools are available (harmless if not).
command -v gtk-update-icon-cache >/dev/null 2>&1 && \
    gtk-update-icon-cache -f "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
command -v update-desktop-database >/dev/null 2>&1 && \
    update-desktop-database "$APPS_DIR" 2>/dev/null || true

echo "Installed ShoppingAgent to the app menu: $APPS_DIR/$DESKTOP_FILE"

if [ -d "$HOME/Desktop" ]; then
    cp "$DIR/$DESKTOP_FILE" "$HOME/Desktop/$DESKTOP_FILE"
    chmod +x "$HOME/Desktop/$DESKTOP_FILE"
    # Nautilus needs the file marked "trusted" or it shows an "untrusted
    # launcher" warning instead of running directly on double-click.
    gio set "$HOME/Desktop/$DESKTOP_FILE" metadata::trusted true 2>/dev/null || true
    echo "Installed desktop icon: $HOME/Desktop/$DESKTOP_FILE"
fi

echo "Done. Look for 'ShoppingAgent' in your app menu (and on the Desktop)."
