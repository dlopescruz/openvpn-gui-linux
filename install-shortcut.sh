#!/usr/bin/env bash
# Install (or remove) the OpenVPN GUI launcher in the application menu.
#   bash install-shortcut.sh              -> create the menu launcher
#   bash install-shortcut.sh --autostart  -> create the launcher and start the app at login
#   bash install-shortcut.sh --remove     -> remove launcher, icon and autostart entry
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
CONF="${XDG_CONFIG_HOME:-$HOME/.config}"
APPS="$DATA/applications"
ICON_DIR="$DATA/icons/hicolor/scalable/apps"
AUTOSTART="$CONF/autostart"

if [ "${1:-}" = "--remove" ]; then
  rm -f "$APPS/openvpn-gui.desktop" "$ICON_DIR/openvpn-gui.svg" "$AUTOSTART/openvpn-gui.desktop"
  echo "Launcher removed."
  exit 0
fi

# use the project's venv if there is one; otherwise the system python3
if [ -x "$DIR/.venv/bin/python" ]; then PY="$DIR/.venv/bin/python"; else PY="$(command -v python3)"; fi
if ! "$PY" -c "import PySide6, keyring" 2>/dev/null; then
  echo "Warning: could not import PySide6/keyring with $PY - install the dependencies first (see the README)." >&2
fi

mkdir -p "$APPS" "$ICON_DIR"
cp "$DIR/data/openvpn-gui.svg" "$ICON_DIR/openvpn-gui.svg"

cat > "$APPS/openvpn-gui.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=OpenVPN GUI
Comment=Graphical client for OpenVPN
Exec="$PY" -m openvpn_gui
Path=$DIR
Icon=openvpn-gui
Terminal=false
Categories=Network;Security;
Keywords=vpn;openvpn;
EOF

if [ "${1:-}" = "--autostart" ]; then
  mkdir -p "$AUTOSTART"
  cp "$APPS/openvpn-gui.desktop" "$AUTOSTART/openvpn-gui.desktop"
  echo "The app will start with your session."
fi

update-desktop-database "$APPS" 2>/dev/null || true
gtk-update-icon-cache -f -t "$DATA/icons/hicolor" 2>/dev/null || true
echo "Done! Look for “OpenVPN GUI” in your application menu."
echo "Note: the launcher points to this folder ($DIR) - if you move it, run this script again."
