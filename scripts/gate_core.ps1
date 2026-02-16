#!/usr/bin/env powershell
# Core-Gate Runner - Hardened W4
# Usage: .\scripts\gate_core.ps1
# Exit Codes: 0 = PASS, 1 = FAIL

$ErrorActionPreference = "Continue"

$CORE_TESTS = @(
    "test/test_feature_error_status.py",
    "test/test_tnp_v4_feature_refs.py",
    "test/test_trust_gate_core_workflow.py",
    "test/test_cad_workflow_trust.py",
    "test/test_brepopengun_offset_api.py",
    "test/test_feature_flags.py",
    "test/test_tnp_stability.py",
    "test/test_feature_edit_robustness.py",
    "test/test_project_roundtrip_persistence.py",
    "test/test_showstopper_red_flag_pack.py",
    "test/test_parametric_reference_modelset.py"
)

Write-Host "=== Core-Gate Started ===" -ForegroundColor Cyan
Write-Host "Timestamp: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host "Tests: $($CORE_TESTS.Count) suites"
Write-Host ""

$start = Get-Date

# Run tests and capture output
$result = & conda run -n cad_env python -m pytest -q $CORE_TESTS 2>&1
$exitCode = $LASTEXITCODE

$end = Get-Date
$duration = ($end - $start).TotalSeconds

# Parse results
$passed = 0
$failed = 0
$skipped = 0
$errors = 0
$failingTests = @()

foreach ($line in $result) {
    $lineStr = $line.ToString()
    
    # Parse summary line like "217 passed, 2 skipped"
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
    
    # Collect failing tests
    if ($lineStr -match "^FAILED\s+(\S+)" -and $lineStr -notmatch "^=+$") {
        $failingTests += $matches[1]
    }
}

# Calculate total and pass rate
$total = $passed + $failed + $skipped + $errors
$passRate = if ($total -gt 0) { [math]::Round(($passed / $total) * 100, 1) } else { 0 }

# Determine status
$status = "PASS"
$statusColor = "Green"
if ($failed -gt 0 -or $errors -gt 0) {
    $status = "FAIL"
    $statusColor = "Red"
} elseif ($exitCode -ne 0) {
    $status = "ERROR"
    $statusColor = "Red"
}

# Output results - Unified Format
Write-Host ""
Write-Host "=== Core-Gate Result ===" -ForegroundColor Cyan
Write-Host "Duration: $([math]::Round($duration, 2))s"
Write-Host "Tests: $passed passed, $failed failed, $skipped skipped" -NoNewline
if ($errors -gt 0) {
    Write-Host ", $errors errors" -NoNewline
}
Write-Host " (total: $total)"
Write-Host "Pass-Rate: $passRate%"
Write-Host "Status: " -NoNewline
Write-Host $status -ForegroundColor $statusColor

if ($failingTests.Count -gt 0) {
    Write-Host ""
    Write-Host "Failing Tests:" -ForegroundColor Red
    foreach ($test in $failingTests) {
        Write-Host "  - $test" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "Exit Code: $exitCode"

exit $exitCode
