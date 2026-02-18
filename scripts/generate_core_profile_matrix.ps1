#!/usr/bin/env powershell
# Core Profile Matrix Generator (W9D)
# Usage:
#   .\scripts\generate_core_profile_matrix.ps1
#   .\scripts\generate_core_profile_matrix.ps1 -OutPrefix roadmap_ctp/CORE_PROFILE_MATRIX_W9
# Exit Codes:
#   0 = PASS, 1 = FAIL

param(
    [string]$OutPrefix = ""
)

$ErrorActionPreference = "Continue"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$gateCore = Join-Path $scriptDir "gate_core.ps1"

if (-not $OutPrefix) {
    $ts = Get-Date -Format "yyyyMMdd_HHmmss"
    $OutPrefix = "roadmap_ctp/CORE_PROFILE_MATRIX_$ts"
}

$jsonOut = "$OutPrefix.json"
$mdOut = "$OutPrefix.md"

Write-Host "=== Core Profile Matrix Generator ===" -ForegroundColor Cyan
Write-Host "Timestamp: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host "OutPrefix: $OutPrefix"
Write-Host ""

$profiles = @("full", "parallel_safe", "kernel_only", "red_flag")
$runs = @{}

foreach ($profile in $profiles) {
    $tmpPath = Join-Path $env:TEMP ("core_profile_{0}_{1}.json" -f $profile, [guid]::NewGuid().ToString("N"))
    try {
        $result = & powershell -ExecutionPolicy Bypass -File $gateCore -Profile $profile -DryRun -JsonOut $tmpPath 2>&1
        $exitCode = $LASTEXITCODE
        if ($exitCode -ne 0) {
            throw "gate_core dry-run failed for profile '$profile' (exit=$exitCode)."
        }
        if (-not (Test-Path -Path $tmpPath -PathType Leaf)) {
            throw "No JSON output for profile '$profile'."
        }
        $payload = Get-Content -Path $tmpPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $runs[$profile] = @{
            suite_count = @($payload.suites).Count
            suites = @($payload.suites)
            dry_run = [bool]$payload.dry_run
            status = [string]$payload.status
        }
        Write-Host ("[PASS] profile={0} suites={1}" -f $profile, $runs[$profile].suite_count) -ForegroundColor Green
    } catch {
        Write-Host ("[FAIL] profile={0}: {1}" -f $profile, $_.Exception.Message) -ForegroundColor Red
        exit 1
    } finally {
        if (Test-Path -Path $tmpPath -PathType Leaf) {
            Remove-Item -Path $tmpPath -ErrorAction SilentlyContinue
        }
    }
}

$fullSuites = @($runs["full"].suites)
$parallelSuites = @($runs["parallel_safe"].suites)
$kernelSuites = @($runs["kernel_only"].suites)
$redFlagSuites = @($runs["red_flag"].suites)

$removedParallel = @($fullSuites | Where-Object { $_ -notin $parallelSuites })
$removedKernel = @($fullSuites | Where-Object { $_ -notin $kernelSuites })
$removedRedFlag = @($fullSuites | Where-Object { $_ -notin $redFlagSuites })

$matrix = @{
    metadata = @{
        generated_at = (Get-Date).ToString("s")
        schema = "core_profile_matrix_v1"
        source = "scripts/gate_core.ps1 -DryRun"
    }
    profiles = @{
        full = $runs["full"]
        parallel_safe = $runs["parallel_safe"]
        kernel_only = $runs["kernel_only"]
        red_flag = $runs["red_flag"]
    }
    deltas = @{
        removed_from_full_parallel_safe = @($removedParallel)
        removed_from_full_kernel_only = @($removedKernel)
        removed_from_full_red_flag = @($removedRedFlag)
    }
}

$matrix | ConvertTo-Json -Depth 12 | Out-File -FilePath $jsonOut -Encoding UTF8
Write-Host "JSON written: $jsonOut"

$rows = @()
foreach ($p in $profiles) {
    $rows += "| $p | $($runs[$p].suite_count) | $($runs[$p].status) | $($runs[$p].dry_run) |"
}

$removedParallelRows = if ($removedParallel.Count -gt 0) {
    ($removedParallel | ForEach-Object { "- $_" }) -join "`r`n"
} else {
    "- (none)"
}

$removedKernelRows = if ($removedKernel.Count -gt 0) {
    ($removedKernel | ForEach-Object { "- $_" }) -join "`r`n"
} else {
    "- (none)"
}

$removedRedFlagRows = if ($removedRedFlag.Count -gt 0) {
    ($removedRedFlag | ForEach-Object { "- $_" }) -join "`r`n"
} else {
    "- (none)"
}

$md = @"
# Core Profile Matrix
**Generated:** $($matrix.metadata.generated_at)
**Schema:** $($matrix.metadata.schema)

## Profile Summary

| Profile | Suite Count | Status | Dry Run |
|---|---:|---|---|
$(($rows -join "`r`n"))

## Removed vs full

### parallel_safe
$removedParallelRows

### kernel_only
$removedKernelRows

### red_flag
$removedRedFlagRows
"@

$md | Out-File -FilePath $mdOut -Encoding UTF8
Write-Host "MD written: $mdOut"
Write-Host ""
Write-Host "=== Core Profile Matrix Generated ===" -ForegroundColor Green
Write-Host "Exit Code: 0"
exit 0
