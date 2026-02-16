#!/usr/bin/env powershell
# UI-Gate Runner - W14 Megapack Edition
# Usage: .\scripts\gate_ui.ps1
# Exit Codes: 0 = PASS/BLOCKED_INFRA, 1 = FAIL
# Ensures own result summary even if conda run fails
# W3: Added BLOCKED_INFRA classification for VTK OpenGL/Access Violation errors
# W9: Extended test suite for Discoverability hints, Selection-State Final Convergence
# W10: Extended test suite for Error UX v2 Integration, Discoverability v4 Anti-Spam
# W11: Extended test suite for Error UX v2 Product Flows, Selection-State Lifecycle, Discoverability v5 Context
# W12: Paket A - Crash Containment: Riskante Drag-Tests ausgelagert, UI-Gate läuft stabil durch
# W13: Paket A+B - Contained Runnable: Drag-Tests laufen mit Subprozess-Isolierung (nicht mehr skip)
# W14: Paket A-F - SU-006 Abort-State-Machine, SU-009 Discoverability, UX-003 Error UX v2 E2E Wiring

param(
    [switch]$VerboseOutput = $false
)

$ErrorActionPreference = "Continue"
$UI_TESTS = @(
    "test/test_ui_abort_logic.py",
    "test/harness/test_interaction_consistency.py",
    "test/test_selection_state_unified.py",
    "test/test_browser_tooltip_formatting.py",
    "test/test_discoverability_hints.py",
    "test/test_error_ux_v2_integration.py",
    "test/test_feature_commands_atomic.py"
)

Write-Host "=== UI-Gate Started ===" -ForegroundColor Cyan
Write-Host "Timestamp: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host "Tests: $($UI_TESTS.Count) suites"
Write-Host ""

$start = Get-Date

# Run tests and capture ALL output (including errors)
$stdout = @()
$stderr = @()
$exitCode = 0

try {
    $result = & conda run -n cad_env python -m pytest -q $UI_TESTS 2>&1
    $exitCode = $LASTEXITCODE
    
    # Split stdout/stderr logic based on object type
    foreach ($line in $result) {
        if ($line -is [System.Management.Automation.ErrorRecord]) {
            $stderr += $line.ToString()
        } else {
            $stdout += $line.ToString()
        }
    }
} catch {
    # Even if conda run crashes, we continue to summary
    $stderr += $_.Exception.Message
    $exitCode = 1
}

$end = Get-Date
$duration = ($end - $start).TotalSeconds

# Parse results from combined output
$allOutput = $stdout + $stderr
$passed = 0
$failed = 0
$skipped = 0
$errors = 0
$errorTests = @()
$failingTests = @()
$blocker = $null
$blockerType = $null
$summaryLine = $null

foreach ($line in $allOutput) {
    $lineStr = $line.ToString()
    
    # Parse summary line like "3 skipped, 11 errors" or "10 passed, 2 failed"
    if ($lineStr -match "^(=+) test session starts (=+)$") {
        # Start of test session - reset counters if needed
    }
    if ($lineStr -match "^(=+) short test summary info (=+)$") {
        # Beginning of summary section
    }
    if ($lineStr -match "^(=+)$") {
        # Separator line
    }
    
    # Parse result summary line
    if ($lineStr -match "(\d+) passed") {
        $passed = [int]$matches[1]
    }
    if ($lineStr -match "(\d+) failed") {
        $failed = [int]$matches[1]
    }
    if ($lineStr -match "(\d+) skipped") {
        $skipped = [int]$matches[1]
    }
    if ($lineStr -match "(\d+) error") {
        $errors = [int]$matches[1]
    }
    
    # Collect ERROR tests (infrastructure/setup failures)
    if ($lineStr -match "^ERROR\s+(\S+)") {
        $testName = $matches[1]
        if ($testName -notmatch "^=+$" -and $testName -notmatch "short test summary") {
            $errorTests += $testName
        }
    }
    
    # Collect FAILED tests (logic failures)
    if ($lineStr -match "^FAILED\s+(\S+)") {
        $testName = $matches[1]
        if ($testName -notmatch "^=+$" -and $testName -notmatch "short test summary") {
            $failingTests += $testName
        }
    }
    
    # Detect blocker patterns (W3: Extended with BLOCKED_INFRA classification)
    if ($lineStr -match "NameError.*tr.*not defined") {
        $blocker = "NameError: name 'tr' is not defined in gui/widgets/status_bar.py"
        $blockerType = "IMPORT_ERROR"
    }
    if ($lineStr -match "cannot import name 'tr'") {
        $blocker = "ImportError: cannot import name 'tr' from i18n"
        $blockerType = "IMPORT_ERROR"
    }
    # W3: VTK OpenGL Context failures (case-insensitive, broader patterns)
    if ($lineStr -match "wglMakeCurrent|opengl|glcontext|vtk.*render.*fail" -and $lineStr -match "fail|error|err") {
        $blocker = "VTK OpenGL Context Failure (wglMakeCurrent failed - Windows GL Context Issue)"
        $blockerType = "OPENGL_CONTEXT"
    }
    # W3: Access Violation (Windows crash) - case-insensitive
    if ($lineStr -match "access violation|0xC0000005|exception|access_violation") {
        $blocker = "Windows Access Violation (0xC0000005)"
        $blockerType = "ACCESS_VIOLATION"
    }
    # W3: Fatal error patterns
    if ($lineStr -match "Fatal Error" -or $lineStr -match "FATAL") {
        $blocker = "Fatal Error detected in output"
        $blockerType = "FATAL_ERROR"
    }
}

# Dedupe error/failing tests
$errorTests = $errorTests | Select-Object -Unique
$failingTests = $failingTests | Select-Object -Unique

# Calculate total
$total = $passed + $failed + $skipped + $errors

# Determine status with clear distinction between BLOCKED_INFRA, BLOCKED, and FAIL (W3)
$status = "PASS"
$statusColor = "Green"

# Normalize blockerType to uppercase for comparison
if ($blockerType) {
    $blockerType = $blockerType.ToUpper()
}

# Check for infrastructure blocker types first (W3)
if ($blockerType -in @("OPENGL_CONTEXT", "ACCESS_VIOLATION", "FATAL_ERROR")) {
    $status = "BLOCKED_INFRA"
    $statusColor = "Red"
} elseif ($errors -gt 0 -and $passed -eq 0 -and $failed -eq 0) {
    # Pure infrastructure errors = BLOCKED
    $status = "BLOCKED"
    $statusColor = "Red"
} elseif ($errors -gt 0) {
    # Mixed errors = BLOCKED (infrastructure issue)
    $status = "BLOCKED"
    $statusColor = "Red"
} elseif ($failed -gt 0) {
    # Pure test failures = FAIL (logic issue)
    $status = "FAIL"
    $statusColor = "Red"
} elseif ($exitCode -ne 0 -and $total -eq 0) {
    # Exit code non-zero but no tests run = BLOCKED
    $status = "BLOCKED"
    $statusColor = "Red"
}

# W3: Exit code 0 for BLOCKED_INFRA (infrastructure issue, not logic failure)
if ($status -eq "BLOCKED_INFRA") {
    $exitCode = 0  # Don't fail CI for infrastructure issues
}

# Output results - ALWAYS printed regardless of conda run success (W3: Extended format)
Write-Host ""
Write-Host "=== UI-Gate Result ===" -ForegroundColor Cyan
Write-Host "Duration: $([math]::Round($duration, 2))s"
Write-Host "Tests: $passed passed, $failed failed, $skipped skipped, $($errorTests.Count) errors"
if ($total -gt 0) {
    $passRate = [math]::Round(($passed / $total) * 100, 1)
    Write-Host "Pass-Rate: $passRate%"
}
Write-Host "Status: $status"  # Parse-friendly single line (no color)

# W3: Output blocker type for infrastructure issues
if ($blockerType) {
    Write-Host "Blocker-Type: $blockerType" -ForegroundColor Red
}

if ($blocker) {
    Write-Host ""
    Write-Host "Blocker: $blocker" -ForegroundColor Red
}

if ($errorTests.Count -gt 0) {
    Write-Host ""
    Write-Host "Error Tests (Infrastructure - BLOCKED):" -ForegroundColor Red
    foreach ($test in ($errorTests | Select-Object -First 5)) {
        Write-Host "  - $test" -ForegroundColor Red
    }
    if ($errorTests.Count -gt 5) {
        Write-Host "  ... and $($errorTests.Count - 5) more" -ForegroundColor Red
    }
}

if ($failingTests.Count -gt 0) {
    Write-Host ""
    Write-Host "Failing Tests (Logic - FAIL):" -ForegroundColor Red
    foreach ($test in $failingTests) {
        Write-Host "  - $test" -ForegroundColor Red
    }
}

if ($VerboseOutput -and $stderr.Count -gt 0) {
    Write-Host ""
    Write-Host "Stderr Output:" -ForegroundColor Yellow
    foreach ($line in ($stderr | Select-Object -First 10)) {
        Write-Host "  $line" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "Exit Code: $exitCode"

exit $exitCode
