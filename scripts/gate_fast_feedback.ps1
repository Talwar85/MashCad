#!/usr/bin/env powershell
# Fast Feedback Gate - W27 RELEASE OPS MEGAPACK Edition
# Usage: .\scripts\gate_fast_feedback.ps1 [-Profile smoke|ui_quick|core_quick|ui_ultraquick|ops_quick] [-JsonOut <path>]
# Exit Codes: 0 = PASS, 1 = FAIL
#
# Lightweight runner for quick local verification between full gate runs.
# Designed for <60s turnaround in inner dev loops.
#
# W27: Added ui_ultraquick (<30s target) and ops_quick (<20s target) profiles.

param(
    [ValidateSet("smoke", "ui_quick", "core_quick", "ui_ultraquick", "ops_quick")]
    [string]$Profile = "smoke",
    [string]$JsonOut = ""
)

$ErrorActionPreference = "Continue"

# ============================================================================
# Profile Definitions
# ============================================================================

$PROFILES = @{
    "smoke" = @(
        "test/test_workflow_product_leaps_w25.py",
        "test/test_gate_runner_contract.py::TestGateRunnerContract::test_gate_all_script_exists"
    )
    "ui_quick" = @(
        "test/test_ui_abort_logic.py",
        "test/test_discoverability_hints_w17.py"
    )
    "core_quick" = @(
        "test/test_feature_error_status.py",
        "test/test_tnp_v4_feature_refs.py"
    )
    # W27: Ultra-quick UI profile (<30s target).
    # Use a tiny, non-recursive contract subset (do not run whole
    # test_gate_runner_contract.py because that file also tests this script).
    "ui_ultraquick" = @(
        "test/test_gate_runner_contract.py::TestGateRunnerContract::test_gate_ui_script_exists",
        "test/test_gate_runner_contract.py::TestGateRunnerContract::test_gate_all_script_exists"
    )
    # W27: Ops/Contract quick profile (<20s target) - script/contract-lastig
    "ops_quick" = @(
        "test/test_gate_evidence_contract.py"
    )
}

$tests = $PROFILES[$Profile]

# ============================================================================
# Pre-flight: Check that test files exist
# ============================================================================

$missingFiles = @()
foreach ($testSpec in $tests) {
    # Extract file path (strip ::class::method if present)
    $filePath = $testSpec -replace "::.*$", ""
    if (-not (Test-Path $filePath)) {
        $missingFiles += $filePath
    }
}

if ($missingFiles.Count -gt 0) {
    Write-Host "=== Fast Feedback Gate ($Profile) ===" -ForegroundColor Cyan
    Write-Host "Timestamp: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
    Write-Host "Profile: $Profile"
    Write-Host ""
    Write-Host "MISSING TEST FILES:" -ForegroundColor Red
    foreach ($f in $missingFiles) {
        Write-Host "  - $f" -ForegroundColor Red
    }
    Write-Host ""
    Write-Host "=== Fast Feedback Gate Result ===" -ForegroundColor Cyan
    Write-Host "Duration: 0s"
    Write-Host "Tests: 0 passed, 0 failed"
    Write-Host "Status: FAIL"
    Write-Host "Exit Code: 1"
    exit 1
}

# ============================================================================
# Run Tests
# ============================================================================

Write-Host "=== Fast Feedback Gate ($Profile) ===" -ForegroundColor Cyan
Write-Host "Timestamp: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host "Profile: $Profile"
Write-Host "Suites: $($tests.Count)"
Write-Host ""

$start = Get-Date
$stdout = @()
$testExitCode = 0

try {
    $result = & conda run -n cad_env python -m pytest -q $tests 2>&1
    $testExitCode = $LASTEXITCODE

    foreach ($line in $result) {
        if ($line -is [System.Management.Automation.ErrorRecord]) {
            # stderr — ignore for parsing
        } else {
            $stdout += $line.ToString()
        }
    }
} catch {
    $stdout += $_.Exception.Message
    $testExitCode = 1
}

$end = Get-Date
$duration = [math]::Round(($end - $start).TotalSeconds, 2)

# ============================================================================
# Parse Results
# ============================================================================

$passed = 0
$failed = 0
$skipped = 0
$errors = 0

foreach ($line in $stdout) {
    if ($line -match "(\d+) passed")  { $passed  = [int]$matches[1] }
    if ($line -match "(\d+) failed")  { $failed  = [int]$matches[1] }
    if ($line -match "(\d+) skipped") { $skipped = [int]$matches[1] }
    if ($line -match "(\d+) error")   { $errors  = [int]$matches[1] }
}

$total = $passed + $failed + $skipped + $errors

# Determine status
if ($failed -gt 0 -or $errors -gt 0 -or ($total -eq 0 -and $testExitCode -ne 0)) {
    $status = "FAIL"
    $statusColor = "Red"
    $exitCode = 1
} else {
    $status = "PASS"
    $statusColor = "Green"
    $exitCode = 0
}

# ============================================================================
# Output
# ============================================================================

Write-Host ""
Write-Host "=== Fast Feedback Gate Result ===" -ForegroundColor Cyan
Write-Host "Profile: $Profile"
Write-Host "Duration: ${duration}s"
Write-Host "Tests: $passed passed, $failed failed, $skipped skipped, $errors errors"
if ($total -gt 0) {
    $passRate = [math]::Round(($passed / $total) * 100, 1)
    Write-Host "Pass-Rate: $passRate%"
}
Write-Host "Status: $status"
Write-Host "Exit Code: $exitCode"

# ============================================================================
# Optional JSON Output
# ============================================================================

if ($JsonOut) {
    $jsonData = @{
        schema   = "fast_feedback_gate_v1"
        profile  = $Profile
        timestamp = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
        duration_seconds = $duration
        passed   = $passed
        failed   = $failed
        skipped  = $skipped
        errors   = $errors
        total    = $total
        status   = $status
        exit_code = $exitCode
        suites   = $tests
    }
    $jsonText = $jsonData | ConvertTo-Json -Depth 5
    [System.IO.File]::WriteAllText($JsonOut, $jsonText, (New-Object System.Text.UTF8Encoding $false))
    Write-Host ""
    Write-Host "JSON written: $JsonOut"
}

exit $exitCode
