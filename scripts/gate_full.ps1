#!/usr/bin/env pwsh
# Gate: FULL - Nightly/Release Validation (<30 min)
# Usage: .\scripts\gate_full.ps1

param(
    [switch]$Verbose,
    [int]$Workers = 2,
    [switch]$IncludeFlaky
)

$ErrorActionPreference = "Stop"
$env:QT_QPA_PLATFORM = "offscreen"
$PYTHON = "C:\Users\User\miniforge3\envs\cad_env\python.exe"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  MashCAD Gate: FULL (Nightly/Release)" -ForegroundColor Cyan
Write-Host "  Target: <30 minutes" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

$startTime = Get-Date
$overallExitCode = 0

# Step 1: Hygiene Check
Write-Host "`n[1/3] Running hygiene check..." -ForegroundColor Yellow
& "$PSScriptRoot\hygiene_check.ps1"
if ($LASTEXITCODE -ne 0) {
    Write-Host "  Hygiene check FAILED" -ForegroundColor Red
    $overallExitCode = 1
} else {
    Write-Host "  Hygiene check PASSED" -ForegroundColor Green
}

# Step 2: Run all tests (excluding wip, optionally include flaky)
Write-Host "`n[2/3] Running full test suite..." -ForegroundColor Yellow
$excludeMarkers = "wip"
if (-not $IncludeFlaky) {
    $excludeMarkers = "wip or flaky"
}

$pytestArgs = @(
    "-m", "not ($excludeMarkers)",
    "-n", $Workers,
    "--timeout=300",
    "--maxfail=50",
    "-q"
)

if ($Verbose) {
    $pytestArgs += "-v"
}

& $PYTHON -m pytest $pytestArgs
if ($LASTEXITCODE -ne 0) {
    $overallExitCode = 1
}

# Step 3: Report summary
Write-Host "`n[3/3] Test Summary" -ForegroundColor Yellow
$elapsed = (Get-Date) - $startTime

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  Duration: $($elapsed.ToString('mm\:ss'))" -ForegroundColor $(if ($elapsed.TotalMinutes -lt 30) { "Green" } else { "Red" })
Write-Host "  Status: $(if ($overallExitCode -eq 0) { 'PASSED' } else { 'FAILED' })" -ForegroundColor $(if ($overallExitCode -eq 0) { "Green" } else { "Red" })
Write-Host "========================================" -ForegroundColor Cyan

exit $overallExitCode
