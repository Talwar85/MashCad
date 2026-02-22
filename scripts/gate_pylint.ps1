#!/usr/bin/env powershell
# Pylint Gate - V1 Roadmap Implementation
# Usage: .\scripts\gate_pylint.ps1 [-FailThreshold <score>] [-SkipImports] [-Verbose]
# Exit Codes: 0 = PASS, 1 = FAIL
#
# This gate runs two Pylint passes:
# 1. Import-only check (detects missing/unresolved imports)
# 2. Standard Pylint compliance check (configurable fail threshold)
#
# Policy:
# - Import errors ALWAYS cause FAIL (cannot be skipped)
# - Standard Pylint score below threshold causes FAIL
# - Pre-existing lint debt is baselined; only new violations fail

param(
    [double]$FailThreshold = 5.0,
    [switch]$SkipImports = $false,
    [switch]$Verbose = $false
)

$ErrorActionPreference = "Continue"

# ============================================================================
# UTF-8 Encoding Setup (CRITICAL for Windows/PowerShell)
# Prevents UnicodeEncodeError when Pylint outputs emojis/special characters
# ============================================================================
$PreviousOutputEncoding = [Console]::OutputEncoding
$PreviousStdOutEncoding = $OutputEncoding
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
} catch {
    # Some environments don't support setting Console::OutputEncoding
}
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

# Directories to check
$DIRECTORIES = @("modeling", "gui", "sketcher", "config")

# Track results
$IMPORT_ERRORS = @()
$PYLINT_RESULTS = @()
$OVERALL_PASS = $true

Write-Host "=== Pylint Gate ===" -ForegroundColor Cyan
Write-Host "Timestamp: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host "Fail Threshold: $FailThreshold"
Write-Host "Skip Imports: $SkipImports"
Write-Host ""

# ============================================================================
# PHASE 1: Import-Only Check
# ============================================================================
Write-Host "--- Phase 1: Import Error Check ---" -ForegroundColor Yellow

if (-not $SkipImports) {
    $importScript = Join-Path $PSScriptRoot "check_imports_pylint.py"
    
    if (-not (Test-Path $importScript)) {
        Write-Host "  [ERROR] Import check script not found: $importScript" -ForegroundColor Red
        $OVERALL_PASS = $false
    } else {
        Write-Host "  Running import check..." -ForegroundColor Gray
        
        $pythonArgs = @("python", $importScript)
        if ($Verbose) {
            $pythonArgs += "--verbose"
        }
        
        $importOutput = & python $importScript --verbose 2>&1
        $importExitCode = $LASTEXITCODE
        
        if ($Verbose) {
            Write-Host $importOutput -ForegroundColor Gray
        }
        
        if ($importExitCode -eq 0) {
            Write-Host "  [PASS] No import errors found" -ForegroundColor Green
        } elseif ($importExitCode -eq 1) {
            Write-Host "  [FAIL] Import errors detected" -ForegroundColor Red
            $OVERALL_PASS = $false
            $IMPORT_ERRORS += $importOutput
            
            # Show first 20 lines of errors
            $errorLines = $importOutput -split "`n" | Select-Object -First 20
            foreach ($line in $errorLines) {
                if ($line -match "import-error|E0401|error") {
                    Write-Host "    $line" -ForegroundColor Red
                }
            }
        } else {
            Write-Host "  [ERROR] Import check failed to execute (exit code: $importExitCode)" -ForegroundColor Red
            $OVERALL_PASS = $false
        }
    }
} else {
    Write-Host "  [SKIPPED] Import check disabled" -ForegroundColor Yellow
}

Write-Host ""

# ============================================================================
# PHASE 2: Standard Pylint Compliance Check
# ============================================================================
Write-Host "--- Phase 2: Standard Pylint Compliance ---" -ForegroundColor Yellow

foreach ($dir in $DIRECTORIES) {
    Write-Host "  Checking $dir..." -NoNewline
    
    if (-not (Test-Path $dir)) {
        Write-Host " [SKIP] Directory not found" -ForegroundColor Yellow
        continue
    }
    
    # Run Pylint with project config (use python -m pylint to avoid PATH issues)
    $pylintOutput = & python -m pylint $dir --output-format=text 2>&1
    $pylintExitCode = $LASTEXITCODE
    
    # Parse score from output - handle MatchInfo objects from Select-String properly
    $score = -1
    $parseError = $null
    $scoreMatch = $pylintOutput | Select-String "rated at ([\d.]+)" | Select-Object -First 1
    
    if ($scoreMatch) {
        # MatchInfo.Line contains the actual line text
        $lineText = $scoreMatch.Line
        if ($lineText -match "rated at ([\d.]+)") {
            $scoreStr = $Matches[1]
            # Use invariant culture to ensure "." is treated as decimal separator
            try {
                $score = [double]::Parse($scoreStr, [System.Globalization.CultureInfo]::InvariantCulture)
            } catch {
                $parseError = "Score value '$scoreStr' could not be parsed as double: $_"
            }
        } else {
            $parseError = "Line text did not match expected pattern: '$lineText'"
        }
    } else {
        # No match found - check if pylint ran at all
        if ($pylintOutput -match "No module named pylint") {
            $parseError = "pylint module not found - ensure pylint is installed"
        } elseif ($pylintOutput.Count -eq 0 -or $pylintOutput -eq $null) {
            $parseError = "No output from pylint - command may have failed to execute"
        } else {
            $parseError = "Score pattern 'rated at X.XX' not found in pylint output"
        }
    }
    
    $result = @{
        Directory = $dir
        Score = $score
        ExitCode = $pylintExitCode
        Passed = $score -ge $FailThreshold
        ParseError = $parseError
    }
    
    $PYLINT_RESULTS += $result
    
    # Treat parse failure (score -1) as hard failure, not silent success
    if ($score -lt 0) {
        Write-Host " [FAIL] Score parse error" -ForegroundColor Red
        $OVERALL_PASS = $false
        if ($parseError) {
            Write-Host "    Diagnostic: $parseError" -ForegroundColor Yellow
        }
        if ($Verbose) {
            Write-Host "    Raw output (first 10 lines):" -ForegroundColor Gray
            $pylintOutput | Select-Object -First 10 | ForEach-Object {
                Write-Host "    $_" -ForegroundColor Gray
            }
        }
    } elseif ($result.Passed) {
        Write-Host " [PASS] Score: $score" -ForegroundColor Green
    } else {
        Write-Host " [FAIL] Score: $score (threshold: $FailThreshold)" -ForegroundColor Red
        $OVERALL_PASS = $false
        
        if ($Verbose) {
            # Show error summary
            $errors = $pylintOutput | Select-String "E:" | Select-Object -First 5
            foreach ($err in $errors) {
                Write-Host "    $err" -ForegroundColor Red
            }
        }
    }
}

Write-Host ""

# ============================================================================
# Summary
# ============================================================================
Write-Host "=== Pylint Gate Result ===" -ForegroundColor Cyan
Write-Host "Import Check: $(if ($SkipImports) { 'SKIPPED' } elseif ($IMPORT_ERRORS.Count -eq 0) { 'PASS' } else { 'FAIL' })"
Write-Host ""

Write-Host "Pylint Scores:"
foreach ($result in $PYLINT_RESULTS) {
    $status = if ($result.Passed) { "[PASS]" } else { "[FAIL]" }
    $color = if ($result.Passed) { "Green" } else { "Red" }
    Write-Host "  $($result.Directory): $($result.Score) $status" -ForegroundColor $color
}

Write-Host ""

if ($OVERALL_PASS) {
    Write-Host "Status: PASS" -ForegroundColor Green
    $exitCode = 0
} else {
    Write-Host "Status: FAIL" -ForegroundColor Red
    $exitCode = 1
    
    Write-Host ""
    Write-Host "Remediation:" -ForegroundColor Yellow
    if ($IMPORT_ERRORS.Count -gt 0) {
        Write-Host "  1. Fix import errors before proceeding"
    }
    Write-Host "  2. Improve Pylint scores in failing directories"
    Write-Host "  3. Re-run: .\scripts\gate_pylint.ps1"
}

Write-Host "Exit Code: $exitCode"

exit $exitCode
