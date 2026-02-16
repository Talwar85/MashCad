#!/usr/bin/env powershell
# Core-Gate Budget Check (W7C Baseline)
# Usage: .\scripts\check_core_gate_budget.ps1 [-MaxDurationSeconds 150] [-MinPassRate 99.0]
# Exit Codes: 0 = PASS, 1 = FAIL

param(
    [double]$MaxDurationSeconds = 150.0,
    [double]$MinPassRate = 99.0,
    [ValidateSet("full", "parallel_safe", "kernel_only")]
    [string]$CoreProfile = "full"
)

$ErrorActionPreference = "Continue"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$gateScript = Join-Path $scriptDir "gate_core.ps1"

Write-Host "=== Core-Gate Budget Check ===" -ForegroundColor Cyan
Write-Host "Timestamp: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host "Budget: Duration <= $MaxDurationSeconds s, Pass-Rate >= $MinPassRate%"
Write-Host "CoreProfile: $CoreProfile"
Write-Host ""

$result = & powershell -ExecutionPolicy Bypass -File $gateScript -Profile $CoreProfile 2>&1
$gateExit = $LASTEXITCODE

$duration = $null
$passRate = $null
$status = "UNKNOWN"

foreach ($line in $result) {
    $lineStr = $line.ToString()
    if ($lineStr -match "Duration:\s+([\d.]+)s") {
        $duration = [double]$matches[1]
    }
    if ($lineStr -match "Pass-Rate:\s+([\d.]+)%") {
        $passRate = [double]$matches[1]
    }
    if ($lineStr -match "Status:\s+(\S+)") {
        $status = $matches[1]
    }
}

$failReasons = @()
if ($gateExit -ne 0 -or $status -ne "PASS") {
    $failReasons += "core gate status is not PASS"
}
if ($duration -eq $null) {
    $failReasons += "duration could not be parsed"
} elseif ($duration -gt $MaxDurationSeconds) {
    $failReasons += "duration budget exceeded ($duration s > $MaxDurationSeconds s)"
}
if ($passRate -eq $null) {
    $failReasons += "pass-rate could not be parsed"
} elseif ($passRate -lt $MinPassRate) {
    $failReasons += "pass-rate below budget ($passRate% < $MinPassRate%)"
}

$finalStatus = if ($failReasons.Count -eq 0) { "PASS" } else { "FAIL" }
$finalExit = if ($failReasons.Count -eq 0) { 0 } else { 1 }

Write-Host ""
Write-Host "=== Core-Gate Budget Result ===" -ForegroundColor Cyan
Write-Host ("Measured Duration: {0}" -f ($(if ($duration -eq $null) { "n/a" } else { "$duration s" })))
Write-Host ("Measured Pass-Rate: {0}" -f ($(if ($passRate -eq $null) { "n/a" } else { "$passRate%" })))
Write-Host "Gate Exit: $gateExit"
Write-Host "Gate Status: $status"
Write-Host "Status: " -NoNewline
Write-Host $finalStatus -ForegroundColor ($(if ($finalStatus -eq "PASS") { "Green" } else { "Red" }))

if ($failReasons.Count -gt 0) {
    Write-Host "Fail-Reasons:" -ForegroundColor Red
    foreach ($reason in $failReasons) {
        Write-Host "  - $reason" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "Exit Code: $finalExit"

exit $finalExit
