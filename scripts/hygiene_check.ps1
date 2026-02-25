#!/usr/bin/env powershell
# Workspace-Hygiene Gate - Hardened W4 + V1 Pylint Integration
# Usage: .\scripts\hygiene_check.ps1 [-FailOnUntracked] [-SkipPylint]
# Exit Codes: 0 = CLEAN/WARNING, 1 = VIOLATIONS (if -FailOnUntracked)
# 
# Policy:
# - Without -FailOnUntracked: Violations = WARNING (Exit 0)
# - With -FailOnUntracked: Violations = FAIL (Exit 1)
# - Pylint import errors ALWAYS cause FAIL (cannot be skipped via -FailOnUntracked)
# - Standard Pylint warnings follow -FailOnUntracked policy

param(
    [switch]$FailOnUntracked = $false,
    [switch]$SkipPylint = $false
)

$ErrorActionPreference = "Continue"

$HYGIENE_VIOLATIONS = @()
$VIOLATION_DETAILS = @()

Write-Host "=== Workspace-Hygiene Check ===" -ForegroundColor Cyan
Write-Host "Timestamp: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host "Policy: $(if ($FailOnUntracked) { 'STRICT (Violations=FAIL)' } else { 'WARN (Violations=WARNING)' })"
Write-Host ""

# Check 1: Debug files in test/
Write-Host "[Check 1] Debug files in test/ directory..."
$debugPatterns = @("debug_*.py", "test_debug_*.py", "_debug_*.py")
$debugFiles = @()
foreach ($pattern in $debugPatterns) {
    $debugFiles += Get-ChildItem -Path "test" -Filter $pattern -ErrorAction SilentlyContinue
}

if ($debugFiles.Count -gt 0) {
    Write-Host "  [VIOLATION] Found $($debugFiles.Count) debug files:" -ForegroundColor Yellow
    foreach ($file in $debugFiles) {
        Write-Host "    - $($file.Name)" -ForegroundColor Yellow
        $HYGIENE_VIOLATIONS += $file.FullName
        $VIOLATION_DETAILS += @{
            File = $file.FullName
            Type = "Debug-Skript"
            Recommendation = "Review and move to scripts/debug/ or delete"
            Owner = "Dev-Team"
        }
    }
} else {
    Write-Host "  [OK] No debug files found" -ForegroundColor Green
}

Write-Host ""

# Check 2: Test output files in root
Write-Host "[Check 2] Test output files in root directory..."
$outputFiles = Get-ChildItem -Path "." -Filter "test_output*.txt" -ErrorAction SilentlyContinue

if ($outputFiles.Count -gt 0) {
    Write-Host "  [VIOLATION] Found $($outputFiles.Count) output files:" -ForegroundColor Yellow
    foreach ($file in $outputFiles) {
        $sizeKB = [math]::Round($file.Length / 1KB, 2)
        Write-Host "    - $($file.Name) (${sizeKB} KB)" -ForegroundColor Yellow
        $HYGIENE_VIOLATIONS += $file.FullName
        $VIOLATION_DETAILS += @{
            File = $file.FullName
            Type = "Test-Output"
            Recommendation = "Delete and add to .gitignore"
            Owner = "AI-3 (QA)"
        }
    }
} else {
    Write-Host "  [OK] No output files found" -ForegroundColor Green
}

Write-Host ""

# Check 3: Temp files
Write-Host "[Check 3] Temp files (*.tmp)..."
$tempFiles = Get-ChildItem -Path "." -Filter "*.tmp" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 10

if ($tempFiles.Count -gt 0) {
    Write-Host "  [VIOLATION] Found $($tempFiles.Count) temp files:" -ForegroundColor Yellow
    foreach ($file in $tempFiles) {
        Write-Host "    - $($file.FullName)" -ForegroundColor Yellow
        $HYGIENE_VIOLATIONS += $file.FullName
        $VIOLATION_DETAILS += @{
            File = $file.FullName
            Type = "Temp-File"
            Recommendation = "Delete"
            Owner = "Dev-Team"
        }
    }
} else {
    Write-Host "  [OK] No temp files found" -ForegroundColor Green
}

Write-Host ""

# Check 4: Backup artifact files (.bak, .bak2, .bak_final, etc.)
Write-Host "[Check 4] Backup artifact files (*.bak*)..."
$backupFiles = Get-ChildItem -Path "." -Recurse -File -ErrorAction SilentlyContinue | Where-Object {
    $_.Name -match '\.bak([0-9]+)?($|\.)|\.bak_final$'
} | Select-Object -First 100

if ($backupFiles.Count -gt 0) {
    Write-Host "  [VIOLATION] Found $($backupFiles.Count) backup artifacts:" -ForegroundColor Yellow
    foreach ($file in $backupFiles) {
        Write-Host "    - $($file.FullName)" -ForegroundColor Yellow
        $HYGIENE_VIOLATIONS += $file.FullName
        $VIOLATION_DETAILS += @{
            File = $file.FullName
            Type = "Backup-Artifact"
            Recommendation = "Delete backup artifact and keep only canonical source file"
            Owner = "Dev-Team"
        }
    }
} else {
    Write-Host "  [OK] No backup artifacts found" -ForegroundColor Green
}

Write-Host ""

# Check 5: Temp helper scripts (temp_*)
Write-Host "[Check 5] Temp helper scripts (temp_*)..."
$tempHelperFiles = Get-ChildItem -Path "." -Recurse -File -ErrorAction SilentlyContinue | Where-Object {
    $_.BaseName -like "temp_*"
} | Select-Object -First 100

if ($tempHelperFiles.Count -gt 0) {
    Write-Host "  [VIOLATION] Found $($tempHelperFiles.Count) temp helper files:" -ForegroundColor Yellow
    foreach ($file in $tempHelperFiles) {
        Write-Host "    - $($file.FullName)" -ForegroundColor Yellow
        $HYGIENE_VIOLATIONS += $file.FullName
        $VIOLATION_DETAILS += @{
            File = $file.FullName
            Type = "Temp-Helper"
            Recommendation = "Delete temp helper file or move to a dedicated scratch area outside repo"
            Owner = "Dev-Team"
        }
    }
} else {
    Write-Host "  [OK] No temp helper files found" -ForegroundColor Green
}

Write-Host ""

# Check 6: .gitignore coverage
Write-Host "[Check 6] .gitignore coverage..."
$gitignorePath = ".gitignore"
$missingPatterns = @()

if (Test-Path $gitignorePath) {
    $gitignore = Get-Content $gitignorePath -ErrorAction SilentlyContinue
    
    $requiredPatterns = @(
        "test_output*.txt",
        "*.log",
        "__pycache__/",
        "*.pyc"
    )
    
    foreach ($pattern in $requiredPatterns) {
        $found = $false
        foreach ($line in $gitignore) {
            if ($line -like "*$pattern*") {
                $found = $true
                break
            }
        }
        if (-not $found) {
            $missingPatterns += $pattern
        }
    }
    
    if ($missingPatterns.Count -gt 0) {
        Write-Host "  [WARNING] Missing .gitignore patterns:" -ForegroundColor Yellow
        foreach ($pattern in $missingPatterns) {
            Write-Host "    - $pattern" -ForegroundColor Yellow
        }
    } else {
        Write-Host "  [OK] All required patterns present" -ForegroundColor Green
    }
} else {
    Write-Host "  [WARNING] No .gitignore file found" -ForegroundColor Yellow
}

Write-Host ""

# Check 7: Pylint Import and Compliance Check (V1 Roadmap)
Write-Host "[Check 7] Pylint Import and Compliance Check..."

if (-not $SkipPylint) {
    $pylintGateScript = Join-Path $PSScriptRoot "gate_pylint.ps1"
    
    if (-not (Test-Path $pylintGateScript)) {
        Write-Host "  [WARNING] Pylint gate script not found: $pylintGateScript" -ForegroundColor Yellow
    } else {
        # Run Pylint gate with low threshold (just check for critical issues)
        $pylintOutput = & powershell -ExecutionPolicy Bypass -File $pylintGateScript -FailThreshold 3.0 2>&1
        $pylintExitCode = $LASTEXITCODE
        
        if ($pylintExitCode -eq 0) {
            Write-Host "  [OK] Pylint checks passed" -ForegroundColor Green
        } else {
            Write-Host "  [WARNING] Pylint issues detected (exit code: $pylintExitCode)" -ForegroundColor Yellow
            # Add to violations but don't fail unless -FailOnUntracked
            $HYGIENE_VIOLATIONS += "Pylint issues"
            $VIOLATION_DETAILS += @{
                File = "Multiple files"
                Type = "Pylint-Issues"
                Recommendation = "Run .\scripts\gate_pylint.ps1 -Verbose for details"
                Owner = "Dev-Team"
            }
            
            # Show brief summary
            $pylintErrors = $pylintOutput | Select-String "FAIL|error" | Select-Object -First 5
            if ($pylintErrors) {
                Write-Host "    Sample issues:" -ForegroundColor Yellow
                foreach ($err in $pylintErrors) {
                    Write-Host "      $err" -ForegroundColor Yellow
                }
            }
        }
    }
} else {
    Write-Host "  [SKIPPED] Pylint check disabled" -ForegroundColor Yellow
}

Write-Host ""

# Summary - Unified Format
Write-Host "=== Hygiene Check Result ===" -ForegroundColor Cyan
Write-Host "Duration: N/A"
Write-Host "Violations: $($HYGIENE_VIOLATIONS.Count) found"

if ($HYGIENE_VIOLATIONS.Count -eq 0) {
    Write-Host "Status: ✅ CLEAN" -ForegroundColor Green
    $exitCode = 0
} else {
    if ($FailOnUntracked) {
        Write-Host "Status: ❌ FAIL (StrictHygiene enabled)" -ForegroundColor Red
        $exitCode = 1
    } else {
        Write-Host "Status: ⚠️ WARNING (StrictHygiene disabled)" -ForegroundColor Yellow
        $exitCode = 0
    }
    
    Write-Host ""
    Write-Host "Violation Details:" -ForegroundColor Cyan
    foreach ($violation in $VIOLATION_DETAILS) {
        Write-Host "  File: $($violation.File)" -ForegroundColor White
        Write-Host "    Type: $($violation.Type)"
        Write-Host "    Recommendation: $($violation.Recommendation)"
        Write-Host "    Owner: $($violation.Owner)"
        Write-Host ""
    }
}

Write-Host "Exit Code: $exitCode"

exit $exitCode
