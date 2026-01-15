#!/bin/bash
# Local build script for MashCAD
# Builds executable for the current platform

set -e  # Exit on error

echo "================================"
echo "MashCAD Local Build Script"
echo "================================"

# Check if PyInstaller is installed
if ! command -v pyinstaller &> /dev/null; then
    echo "PyInstaller not found. Installing..."
    pip install pyinstaller
fi

# Clean previous builds
echo "Cleaning previous builds..."
rm -rf build dist

# Build the executable
echo "Building MashCAD executable..."
pyinstaller MashCAD.spec

# Check the result
if [ $? -eq 0 ]; then
    echo ""
    echo "================================"
    echo "Build successful!"
    echo "================================"

    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "macOS App Bundle created at: dist/MashCAD.app"
        echo "To run: open dist/MashCAD.app"
    elif [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "win32" ]]; then
        echo "Windows executable created at: dist/MashCAD/MashCAD.exe"
        echo "To run: ./dist/MashCAD/MashCAD.exe"
    else
        echo "Linux executable created at: dist/MashCAD/MashCAD"
        echo "To run: ./dist/MashCAD/MashCAD"
    fi

    echo ""
    echo "To create a distributable archive, run:"
    echo "  cd dist && tar -czf MashCAD-$(uname -s)-$(uname -m).tar.gz MashCAD"
else
    echo "Build failed!"
    exit 1
fi
