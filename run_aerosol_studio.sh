#!/usr/bin/env bash
# Aerosol Studio Launch Script for Linux & macOS
set -e

echo "Starting Aerosol Studio..."

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    if ! command -v python &> /dev/null; then
        echo "Error: Python 3 is required but not found in PATH."
        exit 1
    fi
    PYTHON_CMD="python"
else
    PYTHON_CMD="python3"
fi

# Run the Bokeh server application
$PYTHON_CMD -m bokeh serve --show src/aerosolstudio/app/studio.py
