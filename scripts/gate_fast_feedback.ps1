#!/usr/bin/env powershell
# Fast Feedback Gate - W29 RELEASE OPS TIMEOUT-PROOF Edition
# Usage: .\scripts\gate_fast_feedback.ps1 [-Profile smoke|ui_quick|core_quick|ui_ultraquick|ops_quick] [-JsonOut <path>]
# Exit Codes: 0 = PASS, 1 = FAIL
#
# Lightweight runner for quick local verification between full gate runs.
# Designed for <60s turnaround in inner dev loops.
#
# W27: Added ui_ultraquick (<30s target) and ops_quick (<20s target) profiles.
# W28: Optimized profiles - ui_ultraquick <15s, ops_quick <12s, no recursive gate calls.
# W29: Timeout-proof profiles, static contract tests integration, version bump.

param(
    [ValidateSet("smoke", "ui_quick", "core_quick", "ui_ultraquick", "ops_quick")]
    [string]$Profile = "smoke",
    [string]$JsonOut = ""
)

$ErrorActionPreference = "Continue"

# ============================================================================
# Profile Definitions
# ============================================================================

# W29: Profile Definitions - Timeout-proof, no recursive gate calls
# Target times: ui_ultraquick <15s, ops_quick <12s, smoke <45s, ui_quick <60s, core_quick <60s
# IMPORTANT: None of these profiles run tests that call gate_fast_feedback.ps1
# Static contract tests (TestStaticGateContractW29) validate without subprocess calls.
$PROFILES = @{
    "smoke" = @(
        "test/test_workflow_product_leaps_w25.py",
        "test/test_gate_evidence_contract.py::test_validate_gate_evidence_passes_on_valid_schema"
    )
    "ui_quick" = @(
        "test/test_ui_abort_logic.py",
        "test/test_discoverability_hints_w17.py"
    )
    "core_quick" = @(
        "test/test_feature_error_status.py",
        "test/test_tnp_v4_feature_refs.py"
    )
    # W28: Ultra-quick UI profile (<15s target).
    # Uses only non-recursive, lightweight contract tests.
    # Excludes tests that call gate_fast_feedback.ps1 to avoid recursion.
    "ui_ultraquick" = @(
        "test/test_gate_evidence_contract.py::test_validate_gate_evidence_passes_on_valid_schema",
        "test/test_gate_evidence_contract.py::test_validate_gate_evidence_fails_on_core_status_semantic_mismatch"
    )
    # W28: Ops/Contract quick profile (<12s target) - evidence contract validation only
    "ops_quick" = @(
        "test/test_gate_evidence_contract.py::test_validate_gate_evidence_passes_on_valid_schema"
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
        schema   = "fast_feedback_gate_v2"
        version  = "W29"
        profile  = $Profile
        timestamp = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
        duration_seconds = $duration
        target_seconds = switch ($Profile) {
            "ui_ultraquick" { 15 }
            "ops_quick"     { 12 }
            "smoke"         { 45 }
            "ui_quick"      { 60 }
            "core_quick"    { 60 }
            default         { 60 }
        }
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
