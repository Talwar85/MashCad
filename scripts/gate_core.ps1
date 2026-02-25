#!/usr/bin/env pwsh
# Gate: CORE - Core Modeling Tests
# Usage: .\scripts\gate_core.ps1 [-Profile <full|parallel_safe|kernel_only|red_flag>] [-DryRun]

param(
    [switch]$Verbose,
    [int]$Workers = 4,
    [ValidateSet("full", "parallel_safe", "kernel_only", "red_flag")]
    [string]$Profile = "full",
    [switch]$DryRun
)

$ErrorActionPreference = "Continue"
$env:QT_QPA_PLATFORM = "offscreen"
$PYTHON = "C:\Users\User\miniforge3\envs\cad_env\python.exe"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  MashCAD Gate: CORE (Modeling Tests)" -ForegroundColor Cyan
Write-Host "  Profile: $Profile" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Timestamp: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host ""

$startTime = Get-Date
$exitCode = 0

# Define test markers based on profile
switch ($Profile) {
    "full" {
        $markerArg = "-m", "not slow and not wip and not flaky"
    }
    "parallel_safe" {
        $markerArg = "-m", "not slow and not wip and not flaky and parallel_safe"
    }
    "kernel_only" {
        $markerArg = "-m", "kernel"
    }
    "red_flag" {
        $markerArg = "-m", "red_flag or smoke"
    }
}

if ($DryRun) {
    Write-Host "[DRY RUN] Would run: pytest $markerArg" -ForegroundColor Yellow
    Write-Host "Profile: $Profile"
    exit 0
}

# Build pytest arguments
$pytestArgs = @(
    $markerArg,
    "-n", $Workers,
    "--timeout=120",
    "--maxfail=30",
    "-q"
)

if ($Verbose) {
    $pytestArgs += "-v"
}

Write-Host "Running core tests with profile: $Profile" -ForegroundColor Yellow
Write-Host "Command: pytest $pytestArgs" -ForegroundColor Gray
Write-Host ""

& $PYTHON -m pytest $pytestArgs
$exitCode = $LASTEXITCODE

$elapsed = (Get-Date) - $startTime

# Parse pass rate from output (simplified)
$passRate = "N/A"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Duration: $($elapsed.ToString('mm\:ss'))" -ForegroundColor $(if ($elapsed.TotalMinutes -lt 5) { "Green" } else { "Red" })
Write-Host "  Pass-Rate: $passRate" -ForegroundColor Cyan
Write-Host "  Profile: $Profile" -ForegroundColor Cyan
Write-Host "  Status: $(if ($exitCode -eq 0) { 'PASS' } else { 'FAIL' })" -ForegroundColor $(if ($exitCode -eq 0) { "Green" } else { "Red" })
Write-Host "========================================" -ForegroundColor Cyan

exit $exitCode
