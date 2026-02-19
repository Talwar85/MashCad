#!/usr/bin/env powershell
# Core-Gate Runner - Hardened W4
# Usage: .\scripts\gate_core.ps1
# Exit Codes: 0 = PASS, 1 = FAIL

param(
    [ValidateSet("full", "parallel_safe", "kernel_only", "red_flag")]
    [string]$Profile = "full",
    [switch]$SkipUxBoundSuites = $false,
    [switch]$DryRun = $false,
    [string]$JsonOut = ""
)

$ErrorActionPreference = "Continue"

$CORE_TESTS_FULL = @(
    "test/test_feature_error_status.py",
    "test/test_tnp_v4_1_regression_suite.py",
    "test/test_trust_gate_core_workflow.py",
    "test/test_cad_workflow_trust.py",
    "test/test_brepopengun_offset_api.py",
    "test/test_feature_flags.py",
    "test/test_tnp_stability.py",
    "test/test_feature_edit_robustness.py",
    "test/test_feature_commands_atomic.py",
    "test/test_project_roundtrip_persistence.py",
    "test/test_showstopper_red_flag_pack.py",
    "test/test_golden_model_regression_harness.py",
    "test/test_core_cross_platform_contract.py",
    "test/test_gate_evidence_contract.py",
    "test/test_stability_dashboard_seed.py",
    "test/test_parametric_reference_modelset.py"
)

$CORE_TESTS_RED_FLAG = @(
    "test/test_showstopper_red_flag_pack.py",
    "test/test_feature_error_status.py",
    "test/test_tnp_v4_1_regression_suite.py",
    "test/test_feature_edit_robustness.py",
    "test/test_project_roundtrip_persistence.py",
    "test/test_parametric_reference_modelset.py"
)

$UX_BOUND_SUITES = @(
    "test/test_feature_commands_atomic.py"
)

$NON_KERNEL_CONTRACT_SUITES = @(
    "test/test_gate_evidence_contract.py",
    "test/test_stability_dashboard_seed.py"
)

$CORE_TESTS = @($CORE_TESTS_FULL)
if ($Profile -eq "red_flag") {
    $CORE_TESTS = @($CORE_TESTS_RED_FLAG)
} elseif ($Profile -eq "parallel_safe") {
    $CORE_TESTS = @($CORE_TESTS | Where-Object { $_ -notin $UX_BOUND_SUITES })
} elseif ($Profile -eq "kernel_only") {
    $excludeSuites = @($UX_BOUND_SUITES + $NON_KERNEL_CONTRACT_SUITES)
    $CORE_TESTS = @($CORE_TESTS | Where-Object { $_ -notin $excludeSuites })
}

if ($SkipUxBoundSuites) {
    $CORE_TESTS = @($CORE_TESTS | Where-Object { $_ -ne "test/test_feature_commands_atomic.py" })
}

Write-Host "=== Core-Gate Started ===" -ForegroundColor Cyan
Write-Host "Timestamp: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host "Profile: $Profile"
Write-Host "SkipUxBoundSuites: $SkipUxBoundSuites"
Write-Host "DryRun: $DryRun"
Write-Host "Tests: $($CORE_TESTS.Count) suites"
Write-Host ""

Write-Host "=== Environment Debug ===" -ForegroundColor Yellow
Write-Host "Working Directory: $(Get-Location)"
conda run -n cad_env python --version
conda run -n cad_env python -m pytest --version
Write-Host "Test files in test/: $(@(Get-ChildItem test/test_*.py).Count)"
Write-Host "Selected test suites: $($CORE_TESTS.Count)"
Write-Host ""

if ($DryRun) {
    Write-Host "Selected Suites:" -ForegroundColor Cyan
    $idx = 1
    foreach ($suite in $CORE_TESTS) {
        Write-Host ("  [{0}] {1}" -f $idx, $suite)
        $idx += 1
    }
    if ($JsonOut) {
        $drySummary = @{
            profile = $Profile
            skip_ux_bound_suites = [bool]$SkipUxBoundSuites
            dry_run = $true
            suites = @($CORE_TESTS)
            counts = @{
                passed = 0
                failed = 0
                skipped = 0
                errors = 0
                total = 0
            }
            duration_seconds = 0
            pass_rate = 0
            status = "DRY_RUN"
            exit_code = 0
        }
        $drySummary | ConvertTo-Json -Depth 8 | Out-File -FilePath $JsonOut -Encoding UTF8
        Write-Host "JSON written: $JsonOut"
    }
    Write-Host ""
    Write-Host "Exit Code: 0"
    exit 0
}

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

$jsonSummary = @{
    profile = $Profile
    skip_ux_bound_suites = [bool]$SkipUxBoundSuites
    suites = @($CORE_TESTS)
    counts = @{
        passed = $passed
        failed = $failed
        skipped = $skipped
        errors = $errors
        total = $total
    }
    duration_seconds = [math]::Round($duration, 2)
    pass_rate = $passRate
    status = $status
    exit_code = $exitCode
}
if ($JsonOut) {
    $jsonSummary | ConvertTo-Json -Depth 8 | Out-File -FilePath $JsonOut -Encoding UTF8
    Write-Host "JSON written: $JsonOut"
}

exit $exitCode
