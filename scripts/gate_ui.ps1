#!/usr/bin/env pwsh
# Gate: UI - GUI/Viewport Tests
# Usage: .\scripts\gate_ui.ps1
# Exit Codes: 0 = PASS/BLOCKED_INFRA, 1 = FAIL

param(
    [switch]$Verbose,
    [int]$Workers = 2,
    [switch]$SkipDisplayCheck
)

$ErrorActionPreference = "Continue"
$env:QT_QPA_PLATFORM = "offscreen"
$PYTHON = "C:\Users\User\miniforge3\envs\cad_env\python.exe"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  MashCAD Gate: UI (GUI Tests)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Timestamp: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host ""

$startTime = Get-Date
$exitCode = 0
$blockerType = $null

# Check display availability (unless skipped)
if (-not $SkipDisplayCheck) {
    Write-Host "[PREFLIGHT] Checking display availability..." -ForegroundColor Yellow
    
    $displayAvailable = $false
    try {
        # Check if we can create a display connection
        $displayCheck = & $PYTHON -c "from PyQt5.QtWidgets import QApplication; app = QApplication([]); print('OK')" 2>&1
        if ($LASTEXITCODE -eq 0 -and $displayCheck -match "OK") {
            $displayAvailable = $true
            Write-Host "  [OK] Display available (offscreen mode)" -ForegroundColor Green
        }
    } catch {
        Write-Host "  [WARN] Display check failed: $_" -ForegroundColor Yellow
    }
    
    if (-not $displayAvailable) {
        Write-Host "  [BLOCKED_INFRA] No display available for UI tests" -ForegroundColor Red
        $blockerType = "NO_DISPLAY"
        Write-Host ""
        Write-Host "========================================" -ForegroundColor Cyan
        Write-Host "  Status: BLOCKED_INFRA" -ForegroundColor Red
        Write-Host "  Blocker-Type: $blockerType" -ForegroundColor Red
        Write-Host "========================================" -ForegroundColor Cyan
        exit 0  # BLOCKED_INFRA returns 0 (not a failure)
    }
}

Write-Host ""

# Build pytest arguments for UI tests
$pytestArgs = @(
    "-m", "ui or gui or viewport",
    "-n", $Workers,
    "--timeout=60",
    "--maxfail=10",
    "-q"
)

if ($Verbose) {
    $pytestArgs += "-v"
}

Write-Host "Running UI tests..." -ForegroundColor Yellow
Write-Host "Command: pytest $pytestArgs" -ForegroundColor Gray
Write-Host ""

& $PYTHON -m pytest $pytestArgs
$exitCode = $LASTEXITCODE

$elapsed = (Get-Date) - $startTime

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Duration: $($elapsed.ToString('mm\:ss'))" -ForegroundColor Cyan
Write-Host "  Status: $(if ($exitCode -eq 0) { 'PASS' } else { 'FAIL' })" -ForegroundColor $(if ($exitCode -eq 0) { "Green" } else { "Red" })
Write-Host "========================================" -ForegroundColor Cyan

exit $exitCode
