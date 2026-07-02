#!/bin/bash

# Resolve absolute path of the app directory
APP_DIR="$(cd "$(dirname "$0")" && pwd)"

# Paths
EXEC_PATH="$APP_DIR/run.sh"
ICON_PATH="$APP_DIR/images/Senko_Loaf.png"
DESKTOP_FILE="$HOME/.local/share/applications/legion-controller.desktop"

# Ensure run.sh is executable
chmod +x "$EXEC_PATH"

# Create applications directory if missing
mkdir -p "$HOME/.local/share/applications"

# Generate KDE‑friendly .desktop file
cat > "$DESKTOP_FILE" << EOF
[Desktop Entry]
Type=Application
Name=Legion Controller
Comment=Keyboard RGB and Power Controller
Exec=$EXEC_PATH
Icon=$ICON_PATH
Terminal=false
StartupWMClass=Legioncontrol
X-KDE-WindowClass=Legioncontrol
Categories=System;Utility;
EOF

# Make the desktop file executable
chmod +x "$DESKTOP_FILE"

# Refresh KDE application cache
kbuildsycoca6

echo "KDE Plasma desktop entry installed!"
echo "Location: $DESKTOP_FILE"
echo "Icon: $ICON_PATH"
