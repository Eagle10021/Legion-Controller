#!/bin/bash

# Get the absolute path of the directory containing this script
APP_DIR="$(cd "$(dirname "$0")" && pwd)"

# Define paths
ICON_PATH="$APP_DIR/images/Senko_Loaf.jpg"
EXEC_PATH="$APP_DIR/run.sh"
DESKTOP_FILE="$HOME/.local/share/applications/legion-controller.desktop"

# Ensure run.sh is executable
chmod +x "$EXEC_PATH"

# create the .local/share/applications directory if it doesn't exist
mkdir -p "$HOME/.local/share/applications"

# Generate the .desktop file content
cat > "$DESKTOP_FILE" << EOF
[Desktop Entry]
Type=Application
Name=Legion Controller
Comment=Keyboard RGB and Power Controller
Exec="$EXEC_PATH"
Icon="$ICON_PATH"
Terminal=false
Categories=System;Utility;
EOF

# Make the desktop file executable (trusted)
chmod +x "$DESKTOP_FILE"

echo "✅ Desktop shortcut created!"
echo "Location: $DESKTOP_FILE"
echo "You might need to log out and back in, or restart GNOME Shell (Alt+F2, r), for it to appear."
