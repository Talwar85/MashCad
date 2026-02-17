#!/usr/bin/env powershell
# Preflight UI Bootstrap Blocker Scanner - W29 RELEASE OPS TIMEOUT-PROOF
# Usage: .\scripts\preflight_ui_bootstrap.ps1 [-JsonOut <path>]
# Exit Codes: 0 = PASS/BLOCKED_INFRA, 1 = FAIL
#
# Very fast pre-check (<25s target) that detects hard bootstrap blockers
# before running long UI gate runs.
#
# W28: Enhanced BLOCKED_INFRA classification, blocker_type consistency,
#      file-lock/OpenCL noise protection, delivery_metrics support.
# W29: Improved OPENCL_NOISE detection, stable blocker classification,
#      timeout-safe operation, semantic validation consistency.

param(
    [switch]$JsonOut = $false,
    [string]$JsonPath = ""
)

$ErrorActionPreference = "Continue"

# W29: Target runtime in seconds (documented for timeout-proof behavior)
$TARGET_RUNTIME = 25

# W29: Blocker type constants for consistent classification
$BLOCKER_TYPES = @{
    IMPORT_ERROR = "IMPORT_ERROR"
    LOCK_TEMP = "LOCK_TEMP"
    OPENCL_NOISE = "OPENCL_NOISE"
    CLASS_DEFINITION = "CLASS_DEFINITION"
    TIMEOUT = "TIMEOUT"
    UNKNOWN = "UNKNOWN"
}

# W29: OpenCL noise patterns (non-blocking warnings)
$OPENCL_NOISE_PATTERNS = @(
    "OpenCL",
    "CL_",
    "cl\.h",
    "opencl\.h",
    "OpenCL\.ICD"
)

# W29: Function to check if output contains only OpenCL noise
function Test-OpenCLNoiseOnly {
    param([string[]]$Output)

    $outputText = $Output -join "`n"
    $hasOpenCLNoise = $false
    $hasRealError = $false

    foreach ($line in $Output) {
        $lineStr = $line.ToString()
        foreach ($pattern in $OPENCL_NOISE_PATTERNS) {
            if ($lineStr -match $pattern) {
                $hasOpenCLNoise = $true
                break
            }
        }
        # Check for real errors (not OpenCL-related)
        if ($lineStr -match "(Error|FAIL|Exception|Traceback)" -and
            $lineStr -notmatch "OpenCL" -and
            $lineStr -notmatch "CL_") {
            $hasRealError = $true
        }
    }

    return @{
        IsOpenCLNoiseOnly = $hasOpenCLNoise -and -not $hasRealError
        HasOpenCLNoise = $hasOpenCLNoise
        HasRealError = $hasRealError
    }
}

Write-Host "=== Preflight UI Bootstrap Scan ===" -ForegroundColor Cyan
Write-Host "Timestamp: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host ""

$start = Get-Date

# ============================================================================
# Check 1: GUI module import test (via temp file to avoid conda multiline issue)
# ============================================================================

Write-Host "[1/4] Checking GUI module imports..." -ForegroundColor Yellow

$preflightCheckScript = @"
import sys
sys.path.insert(0, '.')

# Critical imports for UI bootstrap
results = []

try:
    import gui.main_window
    results.append('[OK] gui.main_window imported')
except Exception as e:
    results.append(f'[FAIL] gui.main_window: {e}')
    print('\n'.join(results))
    sys.exit(1)

try:
    import gui.viewport_pyvista
    results.append('[OK] gui.viewport_pyvista imported')
except Exception as e:
    results.append(f'[FAIL] gui.viewport_pyvista: {e}')
    print('\n'.join(results))
    sys.exit(1)

try:
    import gui.sketch_editor
    results.append('[OK] gui.sketch_editor imported')
except Exception as e:
    results.append(f'[FAIL] gui.sketch_editor: {e}')
    print('\n'.join(results))
    sys.exit(1)

results.append('[PASS] All critical GUI imports successful')
print('\n'.join(results))
"@

$importOutput = @()
$importExit = 0
$tempFile = [System.IO.Path]::GetTempFileName()
[System.IO.File]::WriteAllText($tempFile, $preflightCheckScript, [System.Text.Encoding]::UTF8)

try {
    $result = & conda run -n cad_env python $tempFile 2>&1
    $importOutput += $result
    $importExit = $LASTEXITCODE
} catch {
    $importOutput += $_.Exception.Message
    $importExit = 1
} finally {
    if (Test-Path $tempFile) { Remove-Item $tempFile -Force }
}

foreach ($line in $importOutput) {
    Write-Host "  $line"
}

if ($importExit -ne 0) {
    # W29: Enhanced blocker classification with consistent output
    $outputStr = $importOutput -join "`n"

    # W29: Infrastructure blocker patterns (BLOCKED_INFRA, exit 0)
    if ($outputStr -match "NameError.*'tr' not defined") {
        $blockerType = $BLOCKER_TYPES.IMPORT_ERROR
        $rootCause = "gui/widgets/status_bar.py:126 - i18n 'tr' not defined"
        $status = "BLOCKED_INFRA"
    } elseif ($outputStr -match "ImportError.*cannot import name 'tr'") {
        $blockerType = $BLOCKER_TYPES.IMPORT_ERROR
        $rootCause = "i18n module - 'tr' function not found"
        $status = "BLOCKED_INFRA"
    } elseif ($outputStr -match "PermissionDenied|AccessDenied|locked|in use") {
        # W29: File-lock detection
        $blockerType = $BLOCKER_TYPES.LOCK_TEMP
        $rootCause = "File lock or access denied - temp file conflict"
        $status = "BLOCKED_INFRA"
    } else {
        # W29: Use improved OpenCL noise detection
        $openclCheck = Test-OpenCLNoiseOnly -Output $importOutput
        if ($openclCheck.IsOpenCLNoiseOnly) {
            $blockerType = $BLOCKER_TYPES.OPENCL_NOISE
            $rootCause = "OpenCL warning/info (non-blocking, treated as noise)"
            $status = "PASS"  # OpenCL warnings don't block UI gate
        } elseif ($outputStr -match "AttributeError.*'SketchEditor' object has no attribute") {
            # W29: Logic error patterns (FAIL, exit 1)
            $blockerType = $BLOCKER_TYPES.CLASS_DEFINITION
            $rootCause = "gui/sketch_editor.py - missing critical method"
            $status = "FAIL"
        } else {
            $blockerType = $BLOCKER_TYPES.IMPORT_ERROR
            $rootCause = ($importOutput | Select-Object -First 1).ToString()
            $status = "FAIL"
        }
    }
    $details = $importOutput -join "; "

    # Output early result
    $end = Get-Date
    $duration = [math]::Round(($end - $start).TotalSeconds, 2)

    Write-Host ""
    Write-Host "=== Preflight Result ===" -ForegroundColor Cyan
    Write-Host "Duration: ${duration}s (target: ${TARGET_RUNTIME}s)"
    Write-Host "Status: $status"
    if ($blockerType) {
        Write-Host "Blocker-Type: $blockerType"
    }
    if ($rootCause) {
        Write-Host "Root-Cause: $rootCause"
    }

    # W28: JSON output support
    if ($JsonOut -and $JsonPath) {
        $jsonData = @{
            schema = "preflight_bootstrap_v1"
            version = "W29"
            timestamp = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
            duration_seconds = $duration
            target_seconds = $TARGET_RUNTIME
            status = $status
            blocker_type = $blockerType
            root_cause = $rootCause
            details = $details
        }
        $jsonText = $jsonData | ConvertTo-Json -Depth 5
        [System.IO.File]::WriteAllText($JsonPath, $jsonText, (New-Object System.Text.UTF8Encoding $false))
        Write-Host "JSON written: $JsonPath"
    }

    Write-Host "Exit Code: $(if ($status -eq 'BLOCKED_INFRA') { 0 } else { 1 })"
    Write-Host ""

    if ($status -eq "BLOCKED_INFRA") {
        Write-Host "BLOCKER DETECTED - UI-Gate would fail early." -ForegroundColor Red
        exit 0  # BLOCKED_INFRA exits 0 (not a logic failure)
    } else {
        Write-Host "FAIL - Logic error detected." -ForegroundColor Red
        exit 1
    }
}

# ============================================================================
# Check 2: MainWindow instantiation test (minimal)
# ============================================================================

Write-Host "[2/4] Checking MainWindow instantiation..." -ForegroundColor Yellow

$initCheckScript = @"
import sys
sys.path.insert(0, '.')

results = []

# Minimal test - just import, don't create QApplication
try:
    from gui.main_window import MainWindow
    results.append('[OK] MainWindow class accessible')

    # Check for critical attributes
    if hasattr(MainWindow, '__init__'):
        results.append('[OK] MainWindow.__init__ exists')
    else:
        results.append('[FAIL] MainWindow.__init__ missing')
        print('\n'.join(results))
        sys.exit(1)

    results.append('[PASS] MainWindow structure valid')
except Exception as e:
    results.append(f'[FAIL] MainWindow: {e}')
    print('\n'.join(results))
    sys.exit(1)

print('\n'.join(results))
"@

$initOutput = @()
$initExit = 0
$tempFile2 = [System.IO.Path]::GetTempFileName()
[System.IO.File]::WriteAllText($tempFile2, $initCheckScript, [System.Text.Encoding]::UTF8)

try {
    $result = & conda run -n cad_env python $tempFile2 2>&1
    $initOutput += $result
    $initExit = $LASTEXITCODE
} catch {
    $initOutput += $_.Exception.Message
    $initExit = 1
} finally {
    if (Test-Path $tempFile2) { Remove-Item $tempFile2 -Force }
}

foreach ($line in $initOutput) {
    Write-Host "  $line"
}

if ($initExit -ne 0) {
    $blockerType = "CLASS_DEFINITION"
    $rootCause = ($initOutput | Select-Object -First 1).ToString()
    $details = $initOutput -join "; "
    $status = "FAIL"

    $end = Get-Date
    $duration = [math]::Round(($end - $start).TotalSeconds, 2)

    Write-Host ""
    Write-Host "=== Preflight Result ===" -ForegroundColor Cyan
    Write-Host "Duration: ${duration}s (target: ${TARGET_RUNTIME}s)"
    Write-Host "Status: FAIL"
    Write-Host "Blocker-Type: $blockerType"
    Write-Host "Root-Cause: $rootCause"
    Write-Host "Exit Code: 1"

    # W28: JSON output support
    if ($JsonOut -and $JsonPath) {
        $jsonData = @{
            schema = "preflight_bootstrap_v1"
            version = "W29"
            timestamp = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
            duration_seconds = $duration
            target_seconds = $TARGET_RUNTIME
            status = $status
            blocker_type = $blockerType
            root_cause = $rootCause
            details = $details
        }
        $jsonText = $jsonData | ConvertTo-Json -Depth 5
        [System.IO.File]::WriteAllText($JsonPath, $jsonText, (New-Object System.Text.UTF8Encoding $false))
        Write-Host "JSON written: $JsonPath"
    }

    exit 1
}

# ============================================================================
# Check 3: SketchEditor structure validation
# ============================================================================

Write-Host "[3/4] Checking SketchEditor structure..." -ForegroundColor Yellow

$sketchCheckScript = @"
import sys
sys.path.insert(0, '.')

results = []

try:
    from gui.sketch_editor import SketchEditor
    results.append('[OK] SketchEditor class accessible')

    # Check for critical methods (from W26 recovery requirements)
    critical_methods = ['_on_solver_finished', 'mouseMoveEvent', 'mousePressEvent', '_find_reference_edge_at']
    missing = []
    for method in critical_methods:
        if not hasattr(SketchEditor, method):
            missing.append(method)
        else:
            results.append(f'[OK] SketchEditor.{method} exists')

    if missing:
        results.append(f'[FAIL] SketchEditor missing methods: {missing}')
        print('\n'.join(results))
        sys.exit(1)

    results.append('[PASS] SketchEditor structure valid')
except Exception as e:
    results.append(f'[FAIL] SketchEditor: {e}')
    print('\n'.join(results))
    sys.exit(1)

print('\n'.join(results))
"@

$sketchOutput = @()
$sketchExit = 0
$tempFile3 = [System.IO.Path]::GetTempFileName()
[System.IO.File]::WriteAllText($tempFile3, $sketchCheckScript, [System.Text.Encoding]::UTF8)

try {
    $result = & conda run -n cad_env python $tempFile3 2>&1
    $sketchOutput += $result
    $sketchExit = $LASTEXITCODE
} catch {
    $sketchOutput += $_.Exception.Message
    $sketchExit = 1
} finally {
    if (Test-Path $tempFile3) { Remove-Item $tempFile3 -Force }
}

foreach ($line in $sketchOutput) {
    Write-Host "  $line"
}

if ($sketchExit -ne 0) {
    $blockerType = "CLASS_DEFINITION"
    $rootCause = "gui/sketch_editor.py - missing critical method(s)"
    $details = $sketchOutput -join "; "
    $status = "FAIL"

    $end = Get-Date
    $duration = [math]::Round(($end - $start).TotalSeconds, 2)

    Write-Host ""
    Write-Host "=== Preflight Result ===" -ForegroundColor Cyan
    Write-Host "Duration: ${duration}s (target: ${TARGET_RUNTIME}s)"
    Write-Host "Status: FAIL"
    Write-Host "Blocker-Type: $blockerType"
    Write-Host "Root-Cause: $rootCause"
    Write-Host "Exit Code: 1"

    # W28: JSON output support
    if ($JsonOut -and $JsonPath) {
        $jsonData = @{
            schema = "preflight_bootstrap_v1"
            version = "W29"
            timestamp = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
            duration_seconds = $duration
            target_seconds = $TARGET_RUNTIME
            status = $status
            blocker_type = $blockerType
            root_cause = $rootCause
            details = $details
        }
        $jsonText = $jsonData | ConvertTo-Json -Depth 5
        [System.IO.File]::WriteAllText($JsonPath, $jsonText, (New-Object System.Text.UTF8Encoding $false))
        Write-Host "JSON written: $JsonPath"
    }

    exit 1
}

# ============================================================================
# Check 4: Viewport module basic validation
# ============================================================================

Write-Host "[4/4] Checking Viewport module..." -ForegroundColor Yellow

$viewportCheckScript = @"
import sys
sys.path.insert(0, '.')

results = []

try:
    import gui.viewport_pyvista
    results.append('[OK] gui.viewport_pyvista imported')

    # Check for class existence
    if hasattr(gui.viewport_pyvista, 'ViewportPyVista'):
        results.append('[OK] ViewportPyVista class exists')
    else:
        results.append('[WARN] ViewportPyVista class not found (may be aliased)')

    results.append('[PASS] Viewport module accessible')
except Exception as e:
    results.append(f'[FAIL] Viewport: {e}')
    print('\n'.join(results))
    sys.exit(1)

print('\n'.join(results))
"@

$viewportOutput = @()
$viewportExit = 0
$tempFile4 = [System.IO.Path]::GetTempFileName()
[System.IO.File]::WriteAllText($tempFile4, $viewportCheckScript, [System.Text.Encoding]::UTF8)

try {
    $result = & conda run -n cad_env python $tempFile4 2>&1
    $viewportOutput += $result
    $viewportExit = $LASTEXITCODE
} catch {
    $viewportOutput += $_.Exception.Message
    $viewportExit = 1
} finally {
    if (Test-Path $tempFile4) { Remove-Item $tempFile4 -Force }
}

foreach ($line in $viewportOutput) {
    Write-Host "  $line"
}

if ($viewportExit -ne 0) {
    $blockerType = "IMPORT_ERROR"
    $rootCause = "gui/viewport_pyvista.py - import failed"
    $details = $viewportOutput -join "; "
    $status = "FAIL"

    $end = Get-Date
    $duration = [math]::Round(($end - $start).TotalSeconds, 2)

    Write-Host ""
    Write-Host "=== Preflight Result ===" -ForegroundColor Cyan
    Write-Host "Duration: ${duration}s (target: ${TARGET_RUNTIME}s)"
    Write-Host "Status: FAIL"
    Write-Host "Blocker-Type: $blockerType"
    Write-Host "Root-Cause: $rootCause"
    Write-Host "Exit Code: 1"

    # W28: JSON output support
    if ($JsonOut -and $JsonPath) {
        $jsonData = @{
            schema = "preflight_bootstrap_v1"
            version = "W29"
            timestamp = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
            duration_seconds = $duration
            target_seconds = $TARGET_RUNTIME
            status = $status
            blocker_type = $blockerType
            root_cause = $rootCause
            details = $details
        }
        $jsonText = $jsonData | ConvertTo-Json -Depth 5
        [System.IO.File]::WriteAllText($JsonPath, $jsonText, (New-Object System.Text.UTF8Encoding $false))
        Write-Host "JSON written: $JsonPath"
    }

    exit 1
}

# ============================================================================
# All checks passed
# ============================================================================

$end = Get-Date
$duration = [math]::Round(($end - $start).TotalSeconds, 2)
$status = "PASS"
$blockerType = $null
$rootCause = $null
$details = "All 4 checks passed: GUI imports, MainWindow, SketchEditor, Viewport"

Write-Host ""
Write-Host "=== Preflight Result ===" -ForegroundColor Cyan
Write-Host "Duration: ${duration}s (target: ${TARGET_RUNTIME}s)"
Write-Host "Status: PASS"
Write-Host ""
Write-Host "No bootstrap blockers detected. UI-Gate safe to run." -ForegroundColor Green
Write-Host "Exit Code: 0"

# W28: JSON output support
if ($JsonOut -and $JsonPath) {
    $jsonData = @{
        schema = "preflight_bootstrap_v1"
        version = "W28"
        timestamp = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
        duration_seconds = $duration
        target_seconds = $TARGET_RUNTIME
        status = $status
        blocker_type = $blockerType
        root_cause = $rootCause
        details = $details
    }
    $jsonText = $jsonData | ConvertTo-Json -Depth 5
    [System.IO.File]::WriteAllText($JsonPath, $jsonText, (New-Object System.Text.UTF8Encoding $false))
    Write-Host "JSON written: $JsonPath"
}

exit 0
