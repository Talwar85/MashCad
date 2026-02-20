#!/usr/bin/env pwsh
# MashCAD CI Gate Runner - Cross-Platform Unified Entry Point (QA-007)
# PowerShell version for Windows
# Usage: .\scripts\gate_ci.ps1 [-Gate <core|ui|hygiene|all>]
# Exit Codes: 0 = PASS, 1 = FAIL

param(
    [Parameter(Position=0)]
    [ValidateSet("core", "ui", "hygiene", "all")]
    [string]$Gate = "all",
    
    [switch]$DryRun = $false,
    [string]$JsonOut = ""
)

$ErrorActionPreference = "Continue"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# ============================================================================
# Platform Detection
# ============================================================================

Write-Host "=== MashCAD CI Gate Runner (Windows) ===" -ForegroundColor Cyan
Write-Host "Timestamp: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host "Platform: $( $PSVersionTable.OS )"
Write-Host "PowerShell: $($PSVersionTable.PSVersion)"
Write-Host "Gate: $Gate"
Write-Host ""

# ============================================================================
# Dependency Verification
# ============================================================================

Write-Host "[PREFLIGHT] Verifying dependencies..." -ForegroundColor Yellow

# Check conda
$condaAvailable = $false
try {
    $condaVersion = & conda --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  [OK] Conda: $condaVersion" -ForegroundColor Green
        $condaAvailable = $true
    }
} catch {
    Write-Host "  [ERROR] Conda not found" -ForegroundColor Red
}

# Check Python in cad_env
if ($condaAvailable) {
    try {
        $pythonVersion = & conda run -n cad_env python --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  [OK] Python: $pythonVersion" -ForegroundColor Green
        } else {
            Write-Host "  [ERROR] cad_env environment not found" -ForegroundColor Red
            Write-Host "  Create it with: conda create -n cad_env python=3.11" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "  [ERROR] Failed to check Python" -ForegroundColor Red
    }
    
    # Check pytest
    try {
        $pytestVersion = & conda run -n cad_env python -m pytest --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  [OK] pytest available" -ForegroundColor Green
        } else {
            Write-Host "  [ERROR] pytest not installed in cad_env" -ForegroundColor Red
        }
    } catch {
        Write-Host "  [ERROR] Failed to check pytest" -ForegroundColor Red
    }
    
    # Check OCP
    try {
        $ocpCheck = & conda run -n cad_env python -c "import OCP; print('OCP OK')" 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  [OK] OCP (OpenCASCADE) available" -ForegroundColor Green
        } else {
            Write-Host "  [ERROR] OCP not available" -ForegroundColor Red
        }
    } catch {
        Write-Host "  [ERROR] Failed to check OCP" -ForegroundColor Red
    }
}

Write-Host ""

if ($DryRun) {
    Write-Host "[DRY RUN] Would run gate: $Gate" -ForegroundColor Yellow
    exit 0
}

# ============================================================================
# Gate Execution
# ============================================================================

$exitCode = 0
$gateStart = Get-Date

function Run-CoreGate {
    param([string]$JsonOutPath)
    
    Write-Host ""
    Write-Host "=== Running Core-Gate ===" -ForegroundColor Cyan
    
    $params = @{}
    if ($JsonOutPath) {
        $params["JsonOut"] = $JsonOutPath
    }
    
    & powershell -ExecutionPolicy Bypass -File "$scriptDir\gate_core.ps1" @params
    return $LASTEXITCODE
}

function Run-UiGate {
    Write-Host ""
    Write-Host "=== Running UI-Gate ===" -ForegroundColor Cyan
    
    & powershell -ExecutionPolicy Bypass -File "$scriptDir\gate_ui.ps1"
    return $LASTEXITCODE
}

function Run-HygieneGate {
    Write-Host ""
    Write-Host "=== Running Hygiene-Gate ===" -ForegroundColor Cyan
    
    & powershell -ExecutionPolicy Bypass -File "$scriptDir\hygiene_check.ps1"
    return $LASTEXITCODE
}

# Run requested gates
switch ($Gate) {
    "core" {
        $exitCode = Run-CoreGate -JsonOutPath $JsonOut
    }
    "ui" {
        $exitCode = Run-UiGate
    }
    "hygiene" {
        $exitCode = Run-HygieneGate
    }
    "all" {
        $coreResult = Run-CoreGate -JsonOutPath $JsonOut
        $uiResult = Run-UiGate
        $hygieneResult = Run-HygieneGate
        
        # Core gate must pass
        if ($coreResult -ne 0) {
            $exitCode = $coreResult
        }
    }
}

$gateEnd = Get-Date
$totalDuration = ($gateEnd - $gateStart).TotalSeconds

# ============================================================================
# Summary
# ============================================================================

Write-Host ""
Write-Host "=== CI Gate Runner Summary ===" -ForegroundColor Cyan
Write-Host "Total Duration: $([math]::Round($totalDuration, 2))s"
Write-Host "Gate: $Gate"
Write-Host "Exit Code: $exitCode"

exit $exitCode
