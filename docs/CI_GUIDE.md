# MashCAD CI Guide

This document describes the Continuous Integration (CI) setup for MashCAD, including how to debug CI failures locally.

## CI Workflows

### Main CI Workflow ([`.github/workflows/ci.yml`](../.github/workflows/ci.yml))

Cross-platform CI matrix that runs on every push and pull request.

**Platforms:**
- `windows-latest`
- `ubuntu-22.04`

**Jobs:**

| Job | Description | Blocking |
|-----|-------------|----------|
| `core-gate` | Core CAD functionality tests | ✅ Yes |
| `ui-gate` | UI/Qt tests (may have BLOCKED_INFRA) | ❌ No* |
| `hygiene-gate` | Code hygiene checks | ❌ No** |
| `evidence` | Generate QA evidence artifacts | ❌ No |
| `ci-summary` | Combined status report | ✅ Yes |

*UI-Gate failures due to OpenGL/context issues (BLOCKED_INFRA) don't fail CI
**Hygiene is warning-only except on `main`/`release/*` branches

### Gates Workflow ([`.github/workflows/gates.yml`](../.github/workflows/gates.yml))

Legacy workflow for detailed gate runs (Windows-only).

### Build Executables ([`.github/workflows/build-executables.yml`](../.github/workflows/build-executables.yml))

Triggered on version tags (e.g., `v1.0.0`) to build platform executables.

## Gates Overview

### Core-Gate

Tests core CAD functionality - must always pass.

**Test Suites:**
- Feature flags
- TNP (Topology Naming Protocol) stability
- Feature edit robustness
- Project roundtrip persistence
- Parametric reference modelset

**Run locally:**
```powershell
# Windows
powershell -ExecutionPolicy Bypass -File scripts/gate_core.ps1

# Linux
bash scripts/gate_ci.sh core
```

### UI-Gate

Tests Qt/PySide6 UI components.

**Known Issues:**
- VTK OpenGL context failures in headless CI (BLOCKED_INFRA)
- These don't block releases - they're infrastructure issues, not logic bugs

**Run locally:**
```powershell
# Windows
powershell -ExecutionPolicy Bypass -File scripts/gate_ui.ps1

# Linux (with virtual display)
xvfb-run -a bash scripts/gate_ci.sh ui
```

### Hygiene-Gate

Checks for code hygiene violations:
- Debug files in `test/`
- Test output files in root
- Temp files (`*.tmp`)
- Backup artifacts (`*.bak*`)

**Run locally:**
```powershell
# Windows
powershell -ExecutionPolicy Bypass -File scripts/hygiene_check.ps1

# Linux
bash scripts/gate_ci.sh hygiene
```

## Debugging CI Failures Locally

### 1. Setup Environment

```bash
# Create conda environment (if not exists)
conda create -n cad_env -c conda-forge python=3.11 \
    pytest pytest-qt \
    pyside6 pyvista pyvistaqt build123d ocp vtk \
    numpy scipy shapely ezdxf loguru trimesh \
    matplotlib pillow lib3mf

conda activate cad_env
pip install ocp-tessellate
```

### 2. Run Specific Gate

```bash
# All gates
bash scripts/gate_ci.sh all          # Linux
powershell -File scripts/gate_ci.ps1 -Gate all  # Windows

# Individual gates
bash scripts/gate_ci.sh core         # Core-Gate only
bash scripts/gate_ci.sh ui           # UI-Gate only
bash scripts/gate_ci.sh hygiene      # Hygiene-Gate only
```

### 3. Run Specific Test File

```bash
conda run -n cad_env python -m pytest -v test/test_feature_flags.py
```

### 4. Run with Verbose Output

```bash
conda run -n cad_env python -m pytest -v --tb=long test/test_feature_flags.py
```

## Platform-Specific Notes

### Windows

**Requirements:**
- PowerShell 5.1+ or PowerShell Core 7+
- Miniconda/Miniforge
- Visual C++ Redistributable (for OCP)

**Common Issues:**

1. **Conda not found in PowerShell**
   ```powershell
   # Initialize conda for PowerShell
   conda init powershell
   # Restart PowerShell
   ```

2. **OCP import error**
   ```
   Install OCP via conda (not pip):
   conda install -c conda-forge ocp
   ```

### Linux

**Requirements:**
- Bash 4.0+
- Miniconda/Miniforge
- X11 libraries for UI tests

**System Dependencies:**
```bash
sudo apt-get install -y \
    libxcb-xinerama0 libxcb-cursor0 libxkbcommon-x11-0 \
    libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 \
    libxcb-render-util0 libxcb-shape0 libdbus-1-3 \
    libgl1-mesa-glx libgl1-mesa-dev libegl1-mesa \
    xvfb
```

**Running UI Tests:**
```bash
# With virtual display (recommended for CI)
xvfb-run -a conda run -n cad_env python -m pytest test/test_ui_*.py

# With offscreen Qt platform
QT_QPA_PLATFORM=offscreen conda run -n cad_env python -m pytest test/test_ui_*.py
```

**Common Issues:**

1. **Qt platform plugin error**
   ```
   qt.qpa.plugin: Could not find the Qt platform plugin "xcb"
   
   Solution: Install X11 dependencies or use QT_QPA_PLATFORM=offscreen
   ```

2. **VTK OpenGL error**
   ```
   Error: cannot initialize GLX
   
   Solution: Use xvfb-run or skip VTK tests in headless mode
   ```

## CI Status Classification

| Status | Meaning | Blocks Release |
|--------|---------|----------------|
| `PASS` | All tests passed | No |
| `FAIL` | Logic failure | Yes |
| `BLOCKED` | Infrastructure issue | No |
| `BLOCKED_INFRA` | Known infra issue (OpenGL, etc.) | No |
| `WARNING` | Hygiene violation | No* |

*Hygiene warnings block on `main` and `release/*` branches

## Artifacts

CI uploads these artifacts (retained for 7-30 days):

| Artifact | Contents | Retention |
|----------|----------|-----------|
| `core-gate-evidence-*` | Test output, JSON summary | 7 days |
| `qa-evidence` | QA evidence markdown files | 30 days |

## Adding New Tests

1. Create test file in `test/` directory
2. Follow naming convention: `test_<feature>.py`
3. Add to appropriate gate:
   - Core tests: Update `CORE_TESTS` in `scripts/gate_core.ps1` and `scripts/gate_ci.sh`
   - UI tests: Update `UI_TESTS` in `scripts/gate_ui.ps1` and `scripts/gate_ci.sh`

## Troubleshooting Checklist

- [ ] Conda environment `cad_env` exists and is activated
- [ ] All dependencies installed (`conda list`)
- [ ] OCP imports successfully (`python -c "import OCP"`)
- [ ] pytest available (`python -m pytest --version`)
- [ ] On Linux: X11 dependencies installed
- [ ] On Linux: Using `xvfb-run` or `QT_QPA_PLATFORM=offscreen` for UI tests

## Contact

For CI issues, check:
1. GitHub Actions logs
2. This documentation
3. `scripts/` directory for gate scripts
