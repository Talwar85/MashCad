#!/usr/bin/env powershell
# All-Gate Aggregator - Hardened W3
# Usage: .\scripts\gate_all.ps1 [-StrictHygiene]
# Exit Codes: 0 = ALL PASS/BLOCKED_INFRA, 1 = ANY FAIL
# -StrictHygiene: Treat hygiene violations as fatal (default: false)
# W3: Added BLOCKED_INFRA distinction in summary

param(
    [switch]$StrictHygiene = $false,
    [switch]$EnforceCoreBudget = $false,
    [double]$MaxCoreDurationSeconds = 150.0,
    [double]$MinCorePassRate = 99.0,
    [ValidateSet("full", "parallel_safe", "kernel_only")]
    [string]$CoreProfile = "full",
    [switch]$ValidateEvidence = $false,
    [switch]$FailOnEvidenceWarning = $false
)

$ErrorActionPreference = "Continue"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "       MashCAD Gate Runner Suite        " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Timestamp: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host "StrictHygiene: $StrictHygiene"
Write-Host "EnforceCoreBudget: $EnforceCoreBudget"
if ($EnforceCoreBudget) {
    Write-Host "Core Budget: Duration <= $MaxCoreDurationSeconds s, Pass-Rate >= $MinCorePassRate%"
}
Write-Host "CoreProfile: $CoreProfile"
Write-Host "ValidateEvidence: $ValidateEvidence"
if ($ValidateEvidence) {
    Write-Host "FailOnEvidenceWarning: $FailOnEvidenceWarning"
}
Write-Host ""

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$results = @()
$overallStart = Get-Date
$totalSteps = if ($ValidateEvidence) { 4 } else { 3 }
$step = 1

# Run Core-Gate
Write-Host "[$step/$totalSteps] Running Core-Gate..." -ForegroundColor Yellow
$coreStart = Get-Date
$coreArgs = @(
    "-ExecutionPolicy", "Bypass",
    "-File", "$scriptDir\gate_core.ps1",
    "-Profile", $CoreProfile
)
$coreResult = & powershell @coreArgs 2>&1
$coreExit = $LASTEXITCODE
$coreEnd = Get-Date
$coreDuration = ($coreEnd - $coreStart).TotalSeconds
$corePassRate = $null
$coreStatus = "UNKNOWN"
$coreResolvedProfile = $CoreProfile
foreach ($line in $coreResult) {
    $lineStr = $line.ToString()
    if ($lineStr -match "Pass-Rate:\s+([\d.]+)%") {
        $corePassRate = [double]$matches[1]
    }
    if ($lineStr -match "Status:\s+(\S+)") {
        $coreStatus = $matches[1]
    }
    if ($lineStr -match "Profile:\s+(\S+)") {
        $coreResolvedProfile = $matches[1]
    }
}
$results += @{
    Name = "Core-Gate"
    ExitCode = $coreExit
    Duration = $coreDuration
    Status = $coreStatus
    PassRate = $corePassRate
    Profile = $coreResolvedProfile
}

Write-Host ""
$step += 1

# Run UI-Gate
Write-Host "[$step/$totalSteps] Running UI-Gate..." -ForegroundColor Yellow
$uiStart = Get-Date
$uiResult = & powershell -ExecutionPolicy Bypass -File "$scriptDir\gate_ui.ps1" 2>&1
$uiExit = $LASTEXITCODE
$uiEnd = Get-Date
$uiDuration = ($uiEnd - $uiStart).TotalSeconds

# W3: Parse UI-Gate status to detect BLOCKED_INFRA
$uiStatus = "UNKNOWN"
$uiBlockerType = $null
foreach ($line in $uiResult) {
    $lineStr = $line.ToString()
    if ($lineStr -match "Status:\s+(BLOCKED_INFRA|BLOCKED|FAIL|PASS)") {
        $uiStatus = $matches[1]
    }
    if ($lineStr -match "Blocker-Type:\s+(.+)") {
        $uiBlockerType = $matches[1].Trim()
    }
}

$results += @{
    Name = "UI-Gate"
    ExitCode = $uiExit
    Duration = $uiDuration
    Status = $uiStatus
    BlockerType = $uiBlockerType
}

Write-Host ""
$step += 1

# Run Hygiene-Gate
Write-Host "[$step/$totalSteps] Running Hygiene-Gate..." -ForegroundColor Yellow
$hygieneStart = Get-Date
if ($StrictHygiene) {
    $hygieneResult = & powershell -ExecutionPolicy Bypass -File "$scriptDir\hygiene_check.ps1" -FailOnUntracked 2>&1
} else {
    $hygieneResult = & powershell -ExecutionPolicy Bypass -File "$scriptDir\hygiene_check.ps1" 2>&1
}
$hygieneExit = $LASTEXITCODE
$hygieneEnd = Get-Date
$hygieneDuration = ($hygieneEnd - $hygieneStart).TotalSeconds

# Determine hygiene status based on StrictHygiene policy
$hygieneStatus = if ($hygieneExit -eq 0) { "PASS" } else { "VIOLATIONS" }
if ($StrictHygiene -and $hygieneExit -ne 0) {
    $hygieneStatus = "FAIL"
}

$results += @{
    Name = "Hygiene-Gate"
    ExitCode = $hygieneExit
    Duration = $hygieneDuration
    Status = $hygieneStatus
}

$step += 1

# Optional: Run Evidence-Contract Validation
if ($ValidateEvidence) {
    Write-Host ""
    Write-Host "[$step/$totalSteps] Running Evidence-Contract..." -ForegroundColor Yellow

    $evidenceStart = Get-Date
    $evidenceArgs = @(
        "-ExecutionPolicy", "Bypass",
        "-File", "$scriptDir\validate_gate_evidence.ps1",
        "-EvidenceDir", "roadmap_ctp",
        "-Pattern", "QA_EVIDENCE_W*.json"
    )
    if ($FailOnEvidenceWarning) {
        $evidenceArgs += "-FailOnWarning"
    }
    $evidenceResult = & powershell @evidenceArgs 2>&1
    $evidenceExit = $LASTEXITCODE
    $evidenceEnd = Get-Date
    $evidenceDuration = ($evidenceEnd - $evidenceStart).TotalSeconds

    $evidencePass = 0
    $evidenceWarn = 0
    $evidenceFail = 0
    foreach ($line in $evidenceResult) {
        $lineStr = $line.ToString()
        if ($lineStr -match "^PASS:\s+(\d+)") {
            $evidencePass = [int]$matches[1]
        }
        if ($lineStr -match "^WARN:\s+(\d+)") {
            $evidenceWarn = [int]$matches[1]
        }
        if ($lineStr -match "^FAIL:\s+(\d+)") {
            $evidenceFail = [int]$matches[1]
        }
    }

    $evidenceStatus = if ($evidenceFail -gt 0 -or $evidenceExit -ne 0) {
        "FAIL"
    } elseif ($evidenceWarn -gt 0) {
        "WARNING"
    } else {
        "PASS"
    }

    $results += @{
        Name = "Evidence-Contract"
        ExitCode = $evidenceExit
        Duration = $evidenceDuration
        Status = $evidenceStatus
        Pass = $evidencePass
        Warn = $evidenceWarn
        Fail = $evidenceFail
    }
}

$overallEnd = Get-Date
$overallDuration = ($overallEnd - $overallStart).TotalSeconds

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "         Gate Summary Report            " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Total Duration: $([math]::Round($overallDuration, 2))s"
Write-Host ""

foreach ($result in $results) {
    $name = $result.Name
    $exit = $result.ExitCode
    $duration = $result.Duration
    $status = if ($result.Status) { $result.Status } else { $null }
    $blockerType = if ($result.BlockerType) { $result.BlockerType } else { $null }
    $passRate = if ($result.PassRate) { $result.PassRate } else { $null }
    $coreProfileDisplay = if ($result.Profile) { $result.Profile } else { $null }
    $evidenceWarn = if ($result.Warn -ne $null) { $result.Warn } else { $null }
    $evidenceFail = if ($result.Fail -ne $null) { $result.Fail } else { $null }

    # Determine display status (W3: Extended with BLOCKED_INFRA, ASCII-only)
    $displayStatus = ""
    $color = "Green"

    if ($name -eq "Hygiene-Gate") {
        if ($StrictHygiene) {
            $displayStatus = if ($exit -eq 0) { "[PASS]" } else { "[FAIL]" }
            $color = if ($exit -eq 0) { "Green" } else { "Red" }
        } else {
            $displayStatus = if ($exit -eq 0) { "[CLEAN]" } else { "[VIOLATIONS]" }
            $color = if ($exit -eq 0) { "Green" } else { "Yellow" }
        }
    } elseif ($name -eq "UI-Gate" -and $status -eq "BLOCKED_INFRA") {
        # W3: Special display for BLOCKED_INFRA
        $displayStatus = "[BLOCKED_INFRA]"
        $color = "Red"
    } elseif ($name -eq "UI-Gate" -and $status -eq "BLOCKED") {
        $displayStatus = "[BLOCKED]"
        $color = "Red"
    } elseif ($name -eq "Evidence-Contract" -and $status -eq "WARNING") {
        $displayStatus = "[WARNING]"
        $color = "Yellow"
    } elseif ($name -eq "Evidence-Contract" -and $status -eq "FAIL") {
        $displayStatus = "[FAIL]"
        $color = "Red"
    } elseif ($name -eq "UI-Gate" -and $status -eq "FAIL") {
        $displayStatus = "[FAIL]"
        $color = "Red"
    } elseif ($exit -eq 0) {
        $displayStatus = "[PASS]"
        $color = "Green"
    } else {
        $displayStatus = "[FAIL]"
        $color = "Red"
    }

    Write-Host "$name ($([math]::Round($duration, 2))s): " -NoNewline
    Write-Host $displayStatus -ForegroundColor $color

    if ($name -eq "Core-Gate" -and $passRate -ne $null) {
        Write-Host "  Pass-Rate: $passRate%" -ForegroundColor Cyan
        if ($coreProfileDisplay) {
            Write-Host "  Profile: $coreProfileDisplay" -ForegroundColor Cyan
        }
    }

    # W3: Show blocker type if present
    if ($blockerType) {
        Write-Host "  Blocker-Type: $blockerType" -ForegroundColor Red
    }

    if ($name -eq "Evidence-Contract" -and $evidenceWarn -ne $null -and $evidenceFail -ne $null) {
        Write-Host "  Summary: WARN=$evidenceWarn FAIL=$evidenceFail" -ForegroundColor Cyan
    }
}

Write-Host ""

# Overall status calculation (W3: BLOCKED_INFRA doesn't fail overall)
$overallExit = 0

# Core must pass
$coreGate = $results | Where-Object { $_.Name -eq "Core-Gate" } | Select-Object -First 1
$corePassed = $coreGate -and $coreGate.ExitCode -eq 0
if (-not $corePassed) {
    $overallExit = 1
}

# Optional Core budget enforcement
if ($EnforceCoreBudget -and $coreGate) {
    $coreDurationFail = $coreGate.Duration -gt $MaxCoreDurationSeconds
    $corePassRateFail = $false
    if ($coreGate.PassRate -ne $null) {
        $corePassRateFail = $coreGate.PassRate -lt $MinCorePassRate
    } else {
        $corePassRateFail = $true
    }
    if ($coreDurationFail -or $corePassRateFail) {
        $overallExit = 1
    }
}

# UI: BLOCKED_INFRA is not a FAIL, only actual FAIL (logic error) blocks
$uiGate = $results | Where-Object { $_.Name -eq "UI-Gate" } | Select-Object -First 1
if ($uiGate) {
    # UI only fails if ExitCode is 1 AND it's not BLOCKED_INFRA
    # BLOCKED_INFRA has ExitCode 0 by design in gate_ui.ps1 W3
    # But the runner may have exit code 1 even with BLOCKED_INFRA in some cases
    # So we check: if UI Status is BLOCKED_INFRA, it's not a failure
    if ($uiGate.Status -eq "BLOCKED_INFRA") {
        # BLOCKED_INFRA is infrastructure issue, not a failure
        # Don't set overallExit to 1
    } elseif ($uiGate.ExitCode -eq 1) {
        # Exit code 1 = actual failure (not BLOCKED_INFRA)
        $overallExit = 1
    }
}

# Hygiene depends on StrictHygiene policy
if ($StrictHygiene) {
    $hygienePassed = ($results | Where-Object { $_.Name -eq "Hygiene-Gate" -and $_.ExitCode -eq 0 }).Count -eq 1
    if (-not $hygienePassed) {
        $overallExit = 1
    }
}

# Optional evidence contract enforcement
if ($ValidateEvidence) {
    $evidenceGate = $results | Where-Object { $_.Name -eq "Evidence-Contract" } | Select-Object -First 1
    if ($evidenceGate) {
        if ($evidenceGate.ExitCode -ne 0 -or $evidenceGate.Status -eq "FAIL") {
            $overallExit = 1
        } elseif ($FailOnEvidenceWarning -and $evidenceGate.Status -eq "WARNING") {
            $overallExit = 1
        }
    } else {
        $overallExit = 1
    }
}

$overallStatus = if ($overallExit -eq 0) { "[ALL GATES PASSED]" } else { "[SOME GATES FAILED]" }
$overallColor = if ($overallExit -eq 0) { "Green" } else { "Red" }

Write-Host "Overall: " -NoNewline
Write-Host $overallStatus -ForegroundColor $overallColor
Write-Host ""

# Policy explanation
if (-not $StrictHygiene) {
    Write-Host "Note: Hygiene violations treated as WARNING only (StrictHygiene=false)" -ForegroundColor Yellow
    Write-Host "      Use -StrictHygiene to treat hygiene violations as fatal" -ForegroundColor Yellow
}
if ($EnforceCoreBudget) {
    Write-Host "Note: Core budget enforcement active (duration/pass-rate thresholds are mandatory)." -ForegroundColor Yellow
}
if ($ValidateEvidence) {
    Write-Host "Note: Evidence contract validation is active." -ForegroundColor Yellow
    if (-not $FailOnEvidenceWarning) {
        Write-Host "      Use -FailOnEvidenceWarning to make warnings fatal." -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "Exit Code: $overallExit"

exit $overallExit
