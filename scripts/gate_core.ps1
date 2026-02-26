#!/usr/bin/env pwsh
# Gate: CORE - Core Modeling Tests
# Usage: .\scripts\gate_core.ps1 [-Profile <full|parallel_safe|kernel_only|red_flag>] [-DryRun]

param(
    [switch]$Verbose,
    [int]$Workers = 4,
    [ValidateSet("full", "parallel_safe", "kernel_only", "red_flag")]
    [string]$Profile = "full",
    [switch]$DryRun,
    [string]$JsonOut = ""
)

$ErrorActionPreference = "Continue"
$env:QT_QPA_PLATFORM = "offscreen"

# Prefer conda environment on CI/local if available; fallback to local path/system python.
$UseConda = $false
$PythonExe = $null
if (Get-Command conda -ErrorAction SilentlyContinue) {
    $UseConda = $true
} else {
    $candidate = "C:\Users\User\miniforge3\envs\cad_env\python.exe"
    if (Test-Path $candidate) {
        $PythonExe = $candidate
    } else {
        $PythonExe = "python"
    }
}

function Invoke-Python {
    param([string[]]$PyArgs)
    if ($script:UseConda) {
        & conda run -n cad_env python @PyArgs
    } else {
        & $script:PythonExe @PyArgs
    }
}

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

# Detect optional pytest plugins so Gate script is robust across CI environments.
$hasXdist = $false
Invoke-Python -PyArgs @("-c", "import xdist") *> $null
if ($LASTEXITCODE -eq 0) { $hasXdist = $true }

$hasTimeout = $false
Invoke-Python -PyArgs @("-c", "import pytest_timeout") *> $null
if ($LASTEXITCODE -eq 0) { $hasTimeout = $true }

# Build pytest arguments
$pytestArgs = @()
$pytestArgs += $markerArg
$pytestArgs += @(
    "--maxfail=30",
    "-q"
)

if ($hasXdist -and $Workers -gt 1) {
    $pytestArgs += @("-n", $Workers)
} else {
    Write-Host "[INFO] pytest-xdist not available or workers<=1 -> running sequential" -ForegroundColor DarkYellow
}

if ($hasTimeout) {
    $pytestArgs += "--timeout=120"
} else {
    Write-Host "[INFO] pytest-timeout not available -> timeout arg skipped" -ForegroundColor DarkYellow
}

if ($Verbose) {
    $pytestArgs += "-v"
}

Write-Host "Running core tests with profile: $Profile" -ForegroundColor Yellow
Write-Host ("Command: pytest {0}" -f ($pytestArgs -join " ")) -ForegroundColor Gray
Write-Host ""

$pytestCmd = @("-m", "pytest") + $pytestArgs
$pytestOutput = Invoke-Python -PyArgs $pytestCmd 2>&1
$pytestOutput | ForEach-Object { Write-Host $_ }
$exitCode = $LASTEXITCODE

$elapsed = (Get-Date) - $startTime

# Parse pass rate from pytest summary output
$passed = 0
$failed = 0
$skipped = 0
$errors = 0
foreach ($line in $pytestOutput) {
    $lineStr = $line.ToString()
    if ($lineStr -match "(\d+)\s+passed") { $passed = [int]$matches[1] }
    if ($lineStr -match "(\d+)\s+failed") { $failed = [int]$matches[1] }
    if ($lineStr -match "(\d+)\s+skipped") { $skipped = [int]$matches[1] }
    if ($lineStr -match "(\d+)\s+error") { $errors = [int]$matches[1] }
}
$total = $passed + $failed + $skipped + $errors
$passRate = if ($total -gt 0) { "{0:N1}%" -f (($passed / $total) * 100) } else { "N/A" }

if ($JsonOut) {
    $jsonDir = Split-Path -Parent $JsonOut
    if ($jsonDir) {
        New-Item -ItemType Directory -Force -Path $jsonDir | Out-Null
    }
    $json = @{
        profile = $Profile
        marker = $markerArg[1]
        counts = @{
            passed = $passed
            failed = $failed
            skipped = $skipped
            errors = $errors
            total = $total
        }
        duration_seconds = [math]::Round($elapsed.TotalSeconds, 2)
        pass_rate = $passRate
        status = if ($exitCode -eq 0) { "PASS" } else { "FAIL" }
        exit_code = $exitCode
    }
    $json | ConvertTo-Json -Depth 5 | Out-File -FilePath $JsonOut -Encoding utf8
    Write-Host "JSON summary written: $JsonOut" -ForegroundColor Gray
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Duration: $($elapsed.ToString('mm\:ss'))" -ForegroundColor $(if ($elapsed.TotalMinutes -lt 5) { "Green" } else { "Red" })
Write-Host "  Pass-Rate: $passRate" -ForegroundColor Cyan
Write-Host "  Profile: $Profile" -ForegroundColor Cyan
Write-Host "  Status: $(if ($exitCode -eq 0) { 'PASS' } else { 'FAIL' })" -ForegroundColor $(if ($exitCode -eq 0) { "Green" } else { "Red" })
Write-Host "========================================" -ForegroundColor Cyan

exit $exitCode
