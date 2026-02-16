#!/usr/bin/env powershell
# Core Ops Dashboard Generator (W9H)
# Combines:
# - Core profile matrix JSON (`core_profile_matrix_v1`)
# - Core gate trend JSON (`core_gate_trend_v1`)
#
# Usage:
#   .\scripts\generate_core_ops_dashboard.ps1 -MatrixJson <path> -TrendJson <path> [-OutPrefix <path>]
# Exit Codes:
#   0 = PASS, 1 = FAIL

param(
    [string]$MatrixJson = "",
    [string]$TrendJson = "",
    [string]$OutPrefix = ""
)

$ErrorActionPreference = "Continue"

if (-not $MatrixJson -or -not $TrendJson) {
    Write-Host "MatrixJson and TrendJson are required." -ForegroundColor Red
    exit 1
}

if (-not (Test-Path -Path $MatrixJson -PathType Leaf)) {
    Write-Host "MatrixJson not found: $MatrixJson" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path -Path $TrendJson -PathType Leaf)) {
    Write-Host "TrendJson not found: $TrendJson" -ForegroundColor Red
    exit 1
}

if (-not $OutPrefix) {
    $ts = Get-Date -Format "yyyyMMdd_HHmmss"
    $OutPrefix = "roadmap_ctp/CORE_OPS_DASHBOARD_$ts"
}

$jsonOut = "$OutPrefix.json"
$mdOut = "$OutPrefix.md"

Write-Host "=== Core Ops Dashboard Generator ===" -ForegroundColor Cyan
Write-Host "Timestamp: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host "MatrixJson: $MatrixJson"
Write-Host "TrendJson: $TrendJson"
Write-Host "OutPrefix: $OutPrefix"
Write-Host ""

try {
    $matrix = Get-Content -Path $MatrixJson -Raw -Encoding UTF8 | ConvertFrom-Json
    $trend = Get-Content -Path $TrendJson -Raw -Encoding UTF8 | ConvertFrom-Json
} catch {
    Write-Host ("Failed to parse input JSON: {0}" -f $_.Exception.Message) -ForegroundColor Red
    exit 1
}

if ($matrix.metadata.schema -ne "core_profile_matrix_v1") {
    Write-Host "Invalid matrix schema." -ForegroundColor Red
    exit 1
}
if ($trend.metadata.schema -ne "core_gate_trend_v1") {
    Write-Host "Invalid trend schema." -ForegroundColor Red
    exit 1
}

$fullCount = [int]$matrix.profiles.full.suite_count
$parallelCount = [int]$matrix.profiles.parallel_safe.suite_count
$kernelCount = [int]$matrix.profiles.kernel_only.suite_count
$redFlagCount = [int]$matrix.profiles.red_flag.suite_count

$passCount = [int]$trend.metrics.pass_count
$failCount = [int]$trend.metrics.fail_count
$otherCount = [int]$trend.metrics.other_count
$trackedRuns = [int]$trend.metadata.runs_tracked
$passRate = if ($trackedRuns -gt 0) { [math]::Round((($passCount / [double]$trackedRuns) * 100.0), 1) } else { 0.0 }

$dashboard = @{
    metadata = @{
        generated_at = (Get-Date).ToString("s")
        schema = "core_ops_dashboard_v1"
        matrix_schema = $matrix.metadata.schema
        trend_schema = $trend.metadata.schema
    }
    profile_overview = @{
        full_suite_count = $fullCount
        parallel_safe_suite_count = $parallelCount
        kernel_only_suite_count = $kernelCount
        red_flag_suite_count = $redFlagCount
    }
    trend_overview = @{
        runs_tracked = $trackedRuns
        pass_count = $passCount
        fail_count = $failCount
        other_count = $otherCount
        pass_rate_percent = $passRate
        avg_duration_seconds = $trend.metrics.avg_duration_seconds
    }
    latest_core = $trend.latest
    removed_from_full = @{
        parallel_safe = @($matrix.deltas.removed_from_full_parallel_safe)
        kernel_only = @($matrix.deltas.removed_from_full_kernel_only)
        red_flag = @($matrix.deltas.removed_from_full_red_flag)
    }
}

$dashboard | ConvertTo-Json -Depth 12 | Out-File -FilePath $jsonOut -Encoding UTF8
Write-Host "JSON written: $jsonOut"

$parallelRemoved = @($dashboard.removed_from_full.parallel_safe)
$kernelRemoved = @($dashboard.removed_from_full.kernel_only)
$redFlagRemoved = @($dashboard.removed_from_full.red_flag)

$parallelRemovedText = if ($parallelRemoved.Count -gt 0) { ($parallelRemoved | ForEach-Object { "- $_" }) -join "`r`n" } else { "- (none)" }
$kernelRemovedText = if ($kernelRemoved.Count -gt 0) { ($kernelRemoved | ForEach-Object { "- $_" }) -join "`r`n" } else { "- (none)" }
$redFlagRemovedText = if ($redFlagRemoved.Count -gt 0) { ($redFlagRemoved | ForEach-Object { "- $_" }) -join "`r`n" } else { "- (none)" }

$md = @"
# Core Ops Dashboard
**Generated:** $($dashboard.metadata.generated_at)
**Schema:** $($dashboard.metadata.schema)

## Profile Overview

| Profile | Suite Count |
|---|---:|
| full | $($dashboard.profile_overview.full_suite_count) |
| parallel_safe | $($dashboard.profile_overview.parallel_safe_suite_count) |
| kernel_only | $($dashboard.profile_overview.kernel_only_suite_count) |
| red_flag | $($dashboard.profile_overview.red_flag_suite_count) |

## Trend Overview

| Metric | Value |
|---|---|
| Runs tracked | $($dashboard.trend_overview.runs_tracked) |
| PASS count | $($dashboard.trend_overview.pass_count) |
| FAIL count | $($dashboard.trend_overview.fail_count) |
| OTHER count | $($dashboard.trend_overview.other_count) |
| Pass rate | $($dashboard.trend_overview.pass_rate_percent)% |
| Avg duration (s) | $($dashboard.trend_overview.avg_duration_seconds) |

## Latest Core Snapshot

| Field | Value |
|---|---|
| Timestamp | $($dashboard.latest_core.timestamp) |
| Status | $($dashboard.latest_core.status) |
| Pass rate | $($dashboard.latest_core.pass_rate) |
| Duration (s) | $($dashboard.latest_core.duration_seconds) |
| Profile | $($dashboard.latest_core.profile) |
| File | $($dashboard.latest_core.file) |

## Removed vs full

### parallel_safe
$parallelRemovedText

### kernel_only
$kernelRemovedText

### red_flag
$redFlagRemovedText
"@

$md | Out-File -FilePath $mdOut -Encoding UTF8
Write-Host "MD written: $mdOut"
Write-Host ""
Write-Host "=== Core Ops Dashboard Generated ===" -ForegroundColor Green
Write-Host "Exit Code: 0"
exit 0
