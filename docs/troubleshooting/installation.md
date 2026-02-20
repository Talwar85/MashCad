# Installation & Environment Troubleshooting Guide

This guide covers installation issues, dependency conflicts, GPU/driver problems, and cross-platform considerations for MashCAD.

## Table of Contents

1. [OCP/OCCT Installation Issues](#ocpocct-installation-issues)
2. [Dependency Conflicts](#dependency-conflicts)
3. [GPU/Driver Problems](#gpudriver-problems)
4. [Cross-Platform Issues](#cross-platform-issues)
5. [Environment Setup](#environment-setup)
6. [Error Messages Reference](#error-messages-reference)

---

## OCP/OCCT Installation Issues

### Symptoms
- `ImportError: cannot import name 'OCP'`
- `ModuleNotFoundError: No module named 'OCP'`
- OCP crashes on import
- Version mismatch errors

### Root Causes

#### 1. OCP Not Installed

**Diagnosis:**
```bash
# Check if OCP is installed
python -c "import OCP; print(OCP.__version__)"

# Or with pip
pip show ocp
```

**Solution:**
```bash
# Install OCP (OpenCascade Python wrapper)
pip install ocp

# Or with conda (recommended)
conda install -c conda-forge ocp
```

#### 2. Wrong OCP Version

**Problem:** Incompatible OCP version with MashCAD requirements

**Required Version:**
```
ocp>=7.7.0
```

**Solution:**
```bash
# Check current version
pip show ocp | grep Version

# Upgrade to latest
pip install --upgrade ocp

# Or install specific version
pip install ocp==7.7.2
```

#### 3. OCP Import Crash

**Problem:** OCP crashes when imported

**Common Causes:**
- Missing Visual C++ Redistributable (Windows)
- Missing system libraries (Linux)
- Incompatible Python version

**Windows Solution:**
1. Install Visual C++ Redistributable:
   - Download from Microsoft: https://aka.ms/vs/17/release/vc_redist.x64.exe
   - Install and restart

**Linux Solution:**
```bash
# Ubuntu/Debian
sudo apt-get install libgl1-mesa-dev libglu1-mesa-dev

# Fedora/RHEL
sudo dnf install mesa-libGL-devel mesa-libGLU-devel

# Arch Linux
sudo pacman -S mesa
```

**macOS Solution:**
```bash
# Install Xcode command line tools
xcode-select --install

# Install dependencies via Homebrew
brew install mesa
```

#### 4. Python Version Incompatibility

**Problem:** OCP requires specific Python version

**Requirements:**
- Python 3.8 - 3.11 (3.12 support may be limited)

**Solution:**
```bash
# Check Python version
python --version

# Create new virtual environment with correct version
conda create -n mashcad python=3.11
conda activate mashcad
pip install -r requirements.txt
```

---

## Dependency Conflicts

### Symptoms
- `ImportError` for various packages
- Version conflict warnings
- Application crashes on startup
- Features not working correctly

### Root Causes

#### 1. Package Version Conflicts

**Diagnosis:**
```bash
# Check installed packages
pip list

# Check for conflicts
pip check
```

**Solution:**
```bash
# Create fresh environment
python -m venv mashcad_env
source mashcad_env/bin/activate  # Linux/macOS
# or
.\mashcad_env\Scripts\activate  # Windows

# Install requirements
pip install -r requirements.txt
```

#### 2. VTK Version Issues

**Problem:** VTK version incompatible with PySide6 or OCP

**Required Version:**
```
vtk>=9.2.0
```

**Solution:**
```bash
# Install compatible VTK
pip install vtk==9.3.0

# If using conda
conda install -c conda-forge vtk
```

#### 3. PySide6 Conflicts

**Problem:** Qt version conflicts with system Qt or other packages

**Solution:**
```bash
# Clean install PySide6
pip uninstall PySide6 pyside6-essentials pyside6-addons
pip install PySide6

# Or specific version
pip install PySide6==6.6.0
```

#### 4. NumPy/SciPy Version Issues

**Problem:** Incompatible NumPy version affecting solver

**Solution:**
```bash
# Install compatible versions
pip install numpy>=1.24.0 scipy>=1.10.0
```

### Dependency Resolution Flowchart

```
Start
  │
  ▼
pip check → Errors? ──Yes──▶ pip install -r requirements.txt --force-reinstall
  │
  No
  │
  ▼
Test imports ──Fail? ──Yes──▶ Check Python version (3.8-3.11)
  │
  Pass
  │
  ▼
Run MashCAD
```

---

## GPU/Driver Problems

### Symptoms
- Black viewport
- Graphics artifacts
- Application crashes during 3D operations
- "Failed to create OpenGL context" error

### Root Causes

#### 1. Outdated GPU Drivers

**Diagnosis:**
```python
# Check GPU info
from gui.viewport import get_gpu_info
info = get_gpu_info()
print(f"GPU: {info.renderer}")
print(f"Driver: {info.driver_version}")
print(f"OpenGL: {info.opengl_version}")
```

**Minimum Requirements:**
- OpenGL 3.3 or higher
- Updated drivers (within last 6 months)

**Solution:**
- **NVIDIA:** Download from https://www.nvidia.com/drivers
- **AMD:** Download from https://www.amd.com/support
- **Intel:** Download from https://downloadcenter.intel.com

#### 2. Unsupported GPU

**Problem:** GPU doesn't support required OpenGL version

**Solution:**
```python
# Enable software rendering (slower but compatible)
import os
os.environ["LIBGL_ALWAYS_SOFTWARE"] = "1"

# Or use Mesa software renderer
os.environ["MESA_GL_VERSION_OVERRIDE"] = "3.3"
```

#### 3. Multiple GPU Issues

**Problem:** System has multiple GPUs and wrong one is used

**Solution:**
```python
# NVIDIA: Force specific GPU
import os
os.environ["CUDA_VISIBLE_DEVICES"] = "0"  # Use first NVIDIA GPU

# Or on laptops with hybrid graphics
os.environ["__GLX_VENDOR_LIBRARY_NAME"] = "nvidia"
```

**Windows Hybrid Graphics:**
1. Open Windows Graphics Settings
2. Add MashCAD to the list
3. Set to "High performance" (dedicated GPU)

#### 4. Virtual Environment GPU Access

**Problem:** VM or container doesn't have GPU access

**Solution:**
- Ensure GPU passthrough is enabled
- Install appropriate drivers in VM
- Use software rendering as fallback

---

## Cross-Platform Issues

### Windows-Specific Issues

#### 1. Long Path Names

**Problem:** Windows has 260 character path limit

**Solution:**
```powershell
# Enable long paths (requires admin)
New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" `
    -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force
```

#### 2. Permission Denied

**Problem:** Cannot write to installation directory

**Solution:**
- Run terminal as Administrator
- Or install in user directory:
  ```bash
  pip install --user -r requirements.txt
  ```

#### 3. Antivirus Blocking

**Problem:** Antivirus software blocks Python/OCP

**Solution:**
- Add Python directory to antivirus exceptions
- Add MashCAD directory to exceptions
- Temporarily disable real-time scanning during installation

### Linux-Specific Issues

#### 1. Missing System Libraries

**Problem:** Required system libraries not installed

**Solution:**
```bash
# Ubuntu/Debian
sudo apt-get install \
    libgl1-mesa-dev \
    libglu1-mesa-dev \
    libx11-dev \
    libxext-dev \
    libxrender-dev \
    libxtst-dev

# Fedora/RHEL
sudo dnf install \
    mesa-libGL-devel \
    mesa-libGLU-devel \
    libX11-devel \
    libXext-devel \
    libXrender-devel \
    libXtst-devel
```

#### 2. Wayland Display Issues

**Problem:** Application doesn't render correctly on Wayland

**Solution:**
```bash
# Force X11 backend
export QT_QPA_PLATFORM=xcb

# Or run with
QT_QPA_PLATFORM=xcb python main.py
```

#### 3. AppImage/Flatpak Issues

**Problem:** Sandboxed environment blocks file access

**Solution:**
- Grant file system permissions
- Use --filesystem flag with Flatpak
- Run from extracted AppImage

### macOS-Specific Issues

#### 1. Apple Silicon (M1/M2/M3)

**Problem:** Some packages not available for ARM64

**Solution:**
```bash
# Use conda-forge for ARM64 packages
conda config --add channels conda-forge
conda install -c conda-forge ocp vtk pyside6

# Or use Rosetta for x86_64
arch -x86_64 python main.py
```

#### 2. Gatekeeper Blocking

**Problem:** macOS blocks unsigned application

**Solution:**
```bash
# Allow the application
xattr -cr /path/to/MashCAD.app

# Or in System Preferences
# Privacy & Security → Open Anyway
```

#### 3. Xcode Command Line Tools

**Problem:** Missing compilation tools

**Solution:**
```bash
# Install command line tools
xcode-select --install
```

---

## Environment Setup

### Recommended Setup (conda)

```bash
# Create environment
conda create -n mashcad python=3.11
conda activate mashcad

# Install dependencies
conda install -c conda-forge ocp vtk
pip install PySide6 numpy scipy

# Install MashCAD
pip install -e .
```

### Recommended Setup (venv + pip)

```bash
# Create environment
python -m venv mashcad_env
source mashcad_env/bin/activate  # Linux/macOS
.\mashcad_env\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Install MashCAD
pip install -e .
```

### Verify Installation

```python
# Run verification script
def verify_installation():
    errors = []
    
    # Check Python version
    import sys
    if sys.version_info < (3, 8):
        errors.append("Python 3.8+ required")
    if sys.version_info > (3, 12):
        errors.append("Python 3.12+ not fully tested")
    
    # Check OCP
    try:
        import OCP
        print(f"✓ OCP version: {OCP.__version__}")
    except ImportError as e:
        errors.append(f"OCP import failed: {e}")
    
    # Check VTK
    try:
        import vtk
        print(f"✓ VTK version: {vtk.vtkVersion.GetVTKVersion()}")
    except ImportError as e:
        errors.append(f"VTK import failed: {e}")
    
    # Check PySide6
    try:
        import PySide6
        print(f"✓ PySide6 version: {PySide6.__version__}")
    except ImportError as e:
        errors.append(f"PySide6 import failed: {e}")
    
    # Check NumPy/SciPy
    try:
        import numpy as np
        print(f"✓ NumPy version: {np.__version__}")
    except ImportError as e:
        errors.append(f"NumPy import failed: {e}")
    
    try:
        import scipy
        print(f"✓ SciPy version: {scipy.__version__}")
    except ImportError as e:
        errors.append(f"SciPy import failed: {e}")
    
    if errors:
        print("\n❌ Errors found:")
        for error in errors:
            print(f"  - {error}")
        return False
    else:
        print("\n✓ All dependencies installed correctly")
        return True

verify_installation()
```

---

## Error Messages Reference

### Installation Errors

| Code | Message | Cause | Solution |
|------|---------|-------|----------|
| IN-001 | "Failed to build wheel for OCP" | Missing compiler | Install build tools |
| IN-002 | "OCP not found" | Not installed | `pip install ocp` |
| IN-003 | "Python version incompatible" | Wrong Python version | Use Python 3.8-3.11 |
| IN-004 | "Permission denied" | No write access | Run as admin or use --user |
| IN-005 | "Network connection failed" | No internet/firewall | Check connection |

### Import Errors

| Code | Message | Cause | Solution |
|------|---------|-------|----------|
| IM-001 | "DLL load failed" | Missing dependencies | Install VC++ redistributable |
| IM-002 | "Symbol not found" | Version mismatch | Reinstall package |
| IM-003 | "Module not found" | Not installed | Install package |
| IM-004 | "Cannot import name" | API change | Check version compatibility |

### GPU Errors

| Code | Message | Cause | Solution |
|------|---------|-------|----------|
| GP-001 | "Failed to create OpenGL context" | Driver issue | Update drivers |
| GP-002 | "OpenGL version too old" | Old GPU/drivers | Update or use software rendering |
| GP-003 | "GPU not detected" | Driver missing | Install GPU drivers |
| GP-004 | "Out of video memory" | Insufficient VRAM | Reduce quality settings |

### Platform Errors

| Code | Message | Cause | Solution |
|------|---------|-------|----------|
| PL-001 | "Long path not supported" | Windows limitation | Enable long paths |
| PL-002 | "Library not found" | Missing system lib | Install system package |
| PL-003 | "Wayland not supported" | Qt/Wayland issue | Use X11 backend |
| PL-004 | "Architecture not supported" | Wrong CPU arch | Use correct package |

---

## Debug Checklist

When experiencing installation issues:

- [ ] Check Python version (3.8-3.11)
- [ ] Verify all dependencies installed: `pip list`
- [ ] Run `pip check` for conflicts
- [ ] Test imports individually
- [ ] Check GPU drivers are current
- [ ] Verify OpenGL version ≥ 3.3
- [ ] Check system libraries (Linux)
- [ ] Try fresh virtual environment
- [ ] Check antivirus isn't blocking

## Getting Help

If issues persist after following this guide:

1. **Collect Diagnostics:**
   ```python
   # Generate diagnostic report
   from core.diagnostics import generate_report
   report = generate_report()
   report.save("mashcad_diagnostics.txt")
   ```

2. **Report Issue:**
   - Include diagnostic report
   - Include exact error messages
   - Include steps to reproduce
   - Include system information

## Related Files

- [`requirements.txt`](../../requirements.txt) - Python dependencies
- [`requirements-dev.txt`](../../requirements-dev.txt) - Development dependencies
- [`config/feature_flags.py`](../../config/feature_flags.py) - Feature configuration
- [`main.py`](../../main.py) - Application entry point

## Quick Reference

### Minimal Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| Python | 3.8 | 3.11 |
| RAM | 4 GB | 8 GB |
| GPU VRAM | 1 GB | 2 GB |
| OpenGL | 3.3 | 4.5 |
| Disk Space | 2 GB | 5 GB |

### Supported Platforms

| Platform | Version | Status |
|----------|---------|--------|
| Windows | 10/11 | ✅ Full support |
| Linux | Ubuntu 22.04+ | ✅ Full support |
| macOS | 12+ (Intel) | ✅ Full support |
| macOS | 12+ (Apple Silicon) | ⚠️ Rosetta recommended |
