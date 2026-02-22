#!/usr/bin/env pwsh
# Gate: STANDARD - Merge Validation (<5 min)
# Usage: .\scripts\gate_standard.ps1

param(
    [switch]$Verbose,
    [int]$Workers = 4,
    [switch]$SkipHygiene
)

$ErrorActionPreference = "Stop"
$env:QT_QPA_PLATFORM = "offscreen"
$PYTHON = "C:\Users\User\miniforge3\envs\cad_env\python.exe"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  MashCAD Gate: STANDARD (Merge)" -ForegroundColor Cyan
Write-Host "  Target: <5 minutes" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

$startTime = Get-Date
$overallExitCode = 0

# Step 1: Hygiene Check (unless skipped)
if (-not $SkipHygiene) {
    Write-Host "`n[1/2] Running hygiene check..." -ForegroundColor Yellow
    & "$PSScriptRoot\hygiene_check.ps1"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  Hygiene check FAILED" -ForegroundColor Red
        $overallExitCode = 1
    } else {
        Write-Host "  Hygiene check PASSED" -ForegroundColor Green
    }
}

# Step 2: Run all non-slow tests
Write-Host "`n[2/2] Running standard test suite..." -ForegroundColor Yellow
$pytestArgs = @(
    "-m", "not slow and not wip and not flaky",
    "-n", $Workers,
    "--timeout=60",
    "--maxfail=20",
    "-q"
)

if ($Verbose) {
    $pytestArgs += "-v"
}

& $PYTHON -m pytest $pytestArgs
if ($LASTEXITCODE -ne 0) {
    $overallExitCode = 1
}

$elapsed = (Get-Date) - $startTime

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  Duration: $($elapsed.ToString('mm\:ss'))" -ForegroundColor $(if ($elapsed.TotalMinutes -lt 5) { "Green" } else { "Red" })
Write-Host "  Status: $(if ($overallExitCode -eq 0) { 'PASSED' } else { 'FAILED' })" -ForegroundColor $(if ($overallExitCode -eq 0) { "Green" } else { "Red" })
Write-Host "========================================" -ForegroundColor Cyan

exit $overallExitCode
