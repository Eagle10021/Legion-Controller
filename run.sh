#!/bin/bash

# Ensure we are in the script's directory
cd "$(dirname "$0")"

# Name of the virtual environment directory
VENV_DIR="venv"

# Check if venv exists
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment (with system packages)..."
    python3 -m venv --system-site-packages "$VENV_DIR"
    
    # Check if creation succeeded
    if [ ! -d "$VENV_DIR" ]; then
        echo "Error: Failed to create virtual environment. Do you have python3-venv installed?"
        exit 1
    fi
    
    echo "Installing dependencies..."
    "$VENV_DIR/bin/pip" install -r requirements.txt
fi

# Run the application using the venv python
# We use sudo/pkexec inside the python script for hardware access, 
# so we run the python interpreter as the regular user.
"$VENV_DIR/bin/python3" Legion_KBLight.py "$@"
