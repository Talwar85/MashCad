#!/usr/bin/env pwsh
# Gate: FAST - PR Validation (<2 min)
# Usage: .\scripts\gate_fast.ps1

param(
    [switch]$Verbose,
    [int]$Workers = 4
)

$ErrorActionPreference = "Stop"
$env:QT_QPA_PLATFORM = "offscreen"
$PYTHON = "C:\Users\User\miniforge3\envs\cad_env\python.exe"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  MashCAD Gate: FAST (PR Validation)" -ForegroundColor Cyan
Write-Host "  Target: <2 minutes" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

$startTime = Get-Date

# Run fast and kernel tests with parallelization
$pytestArgs = @(
    "-m", "fast or kernel",
    "-n", $Workers,
    "--timeout=30",
    "--maxfail=10",
    "-q"
)

if ($Verbose) {
    $pytestArgs += "-v"
}

Write-Host "`nRunning fast + kernel tests..." -ForegroundColor Yellow
& $PYTHON -m pytest $pytestArgs

$exitCode = $LASTEXITCODE
$elapsed = (Get-Date) - $startTime

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  Duration: $($elapsed.ToString('mm\:ss'))" -ForegroundColor $(if ($elapsed.TotalMinutes -lt 2) { "Green" } else { "Red" })
Write-Host "  Status: $(if ($exitCode -eq 0) { 'PASSED' } else { 'FAILED' })" -ForegroundColor $(if ($exitCode -eq 0) { "Green" } else { "Red" })
Write-Host "========================================" -ForegroundColor Cyan

exit $exitCode
