@echo off
REM Local build script for MashCAD on Windows

echo ================================
echo MashCAD Local Build Script (Windows)
echo ================================

REM Check if PyInstaller is installed
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo PyInstaller not found. Installing...
    pip install pyinstaller
)

REM Clean previous builds
echo Cleaning previous builds...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

REM Fix OpenMP conflict during analysis
set KMP_DUPLICATE_LIB_OK=TRUE

REM Build the executable
echo Building MashCAD executable...
pyinstaller MashCAD.spec

if %errorlevel% equ 0 (
    echo.
    echo ================================
    echo Build successful!
    echo ================================
    echo Windows executable created at: dist\MashCAD\MashCAD.exe
    echo To run: dist\MashCAD\MashCAD.exe
    echo.
    echo To create a distributable archive:
    echo   cd dist
    echo   tar -czf MashCAD-Windows-x64.zip MashCAD
) else (
    echo Build failed!
    exit /b 1
)
