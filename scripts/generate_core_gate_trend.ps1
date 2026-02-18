#!/usr/bin/env powershell
# Core Gate Trend Generator (W9G)
# Usage:
#   .\scripts\generate_core_gate_trend.ps1
#   .\scripts\generate_core_gate_trend.ps1 -EvidenceDir roadmap_ctp -Pattern "gate_all_summary*.json"
# Exit Codes:
#   0 = PASS, 1 = FAIL

param(
    [string]$EvidenceDir = "roadmap_ctp",
    [string]$Pattern = "gate_all_summary*.json",
    [string]$OutPrefix = "",
    [int]$MaxRuns = 30
)

$ErrorActionPreference = "Continue"

if (-not $OutPrefix) {
    $ts = Get-Date -Format "yyyyMMdd_HHmmss"
    $OutPrefix = Join-Path $EvidenceDir "CORE_GATE_TREND_$ts"
}

$jsonOut = "$OutPrefix.json"
$mdOut = "$OutPrefix.md"

Write-Host "=== Core Gate Trend Generator ===" -ForegroundColor Cyan
Write-Host "Timestamp: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host "EvidenceDir: $EvidenceDir"
Write-Host "Pattern: $Pattern"
Write-Host "OutPrefix: $OutPrefix"
Write-Host ""

$files = @(Get-ChildItem -Path $EvidenceDir -Filter $Pattern -File -ErrorAction SilentlyContinue | Sort-Object LastWriteTime)
if ($files.Count -eq 0) {
    Write-Host "No matching evidence files found." -ForegroundColor Red
    exit 1
}

$runs = @()
foreach ($f in $files) {
    try {
        $payload = Get-Content -Path $f.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
        $timestamp = $null
        if ($payload.metadata -and $payload.metadata.generated_at) {
            $timestamp = [datetime]$payload.metadata.generated_at
        } elseif ($payload.metadata -and $payload.metadata.date -and $payload.metadata.time) {
            $timestamp = [datetime]("{0} {1}" -f $payload.metadata.date, $payload.metadata.time)
        } else {
            $timestamp = $f.LastWriteTime
        }

        $coreStatus = "UNKNOWN"
        $coreDuration = $null
        $corePassRate = $null
        $coreProfile = $null

        if ($payload.gates) {
            $coreGate = @($payload.gates | Where-Object { $_.name -eq "Core-Gate" }) | Select-Object -First 1
            if ($coreGate) {
                $coreStatus = [string]$coreGate.status
                $coreDuration = $coreGate.duration_seconds
                $corePassRate = $coreGate.pass_rate
                $coreProfile = $coreGate.profile
            }
        } elseif ($payload.summary -and $payload.summary.core_gate) {
            $core = $payload.summary.core_gate
            if ($core.status_class) {
                $coreStatus = [string]$core.status_class
            } elseif ($core.status) {
                $coreStatus = [string]$core.status
            }
            $coreDuration = $core.duration_seconds
            if ($core.passed -ne $null -and $core.failed -ne $null -and $core.skipped -ne $null -and $core.errors -ne $null) {
                $total = [double]($core.passed + $core.failed + $core.skipped + $core.errors)
                if ($total -gt 0) {
                    $corePassRate = [math]::Round((([double]$core.passed / $total) * 100.0), 1)
                }
            }
            if ($payload.config -and $payload.config.core_profile) {
                $coreProfile = $payload.config.core_profile
            }
        }

        $runs += @(
            @{
                file = $f.Name
                timestamp = $timestamp.ToString("s")
                status = $coreStatus
                duration_seconds = $coreDuration
                pass_rate = $corePassRate
                profile = $coreProfile
            }
        )
    } catch {
        Write-Host ("Warning: failed to parse {0}: {1}" -f $f.Name, $_.Exception.Message) -ForegroundColor Yellow
    }
}

if (@($runs).Count -eq 0) {
    Write-Host "No parseable runs found." -ForegroundColor Red
    exit 1
}

$ordered = @($runs | Sort-Object { [datetime]$_.timestamp })
if (@($ordered).Count -gt $MaxRuns) {
    $ordered = @($ordered | Select-Object -Last $MaxRuns)
}

$statusCounts = @{
    PASS = @($ordered | Where-Object { $_.status -eq "PASS" }).Count
    FAIL = @($ordered | Where-Object { $_.status -eq "FAIL" }).Count
    OTHER = @($ordered | Where-Object { $_.status -ne "PASS" -and $_.status -ne "FAIL" }).Count
}

$durations = @($ordered | ForEach-Object { $_.duration_seconds } | Where-Object { $null -ne $_ })
$avgDuration = $null
if ($durations.Count -gt 0) {
    $avgDuration = [math]::Round((($durations | Measure-Object -Average).Average), 2)
}

$trend = @{
    metadata = @{
        generated_at = (Get-Date).ToString("s")
        schema = "core_gate_trend_v1"
        source_dir = $EvidenceDir
        source_pattern = $Pattern
        runs_tracked = @($ordered).Count
    }
    metrics = @{
        pass_count = $statusCounts.PASS
        fail_count = $statusCounts.FAIL
        other_count = $statusCounts.OTHER
        avg_duration_seconds = $avgDuration
    }
    latest = @($ordered | Select-Object -Last 1)[0]
    timeline = @($ordered)
}

$trend | ConvertTo-Json -Depth 10 | Out-File -FilePath $jsonOut -Encoding UTF8
Write-Host "JSON written: $jsonOut"

$rows = @()
foreach ($row in $ordered) {
    $rows += "| $($row.timestamp) | $($row.status) | $($row.pass_rate) | $($row.duration_seconds) | $($row.profile) | $($row.file) |"
}

$md = @"
# Core Gate Trend
**Generated:** $($trend.metadata.generated_at)
**Schema:** $($trend.metadata.schema)
**Runs tracked:** $($trend.metadata.runs_tracked)

## Metrics

| Metric | Value |
|---|---|
| PASS count | $($trend.metrics.pass_count) |
| FAIL count | $($trend.metrics.fail_count) |
| OTHER count | $($trend.metrics.other_count) |
| Avg duration (s) | $($trend.metrics.avg_duration_seconds) |

## Latest

| Field | Value |
|---|---|
| Timestamp | $($trend.latest.timestamp) |
| Status | $($trend.latest.status) |
| Pass rate | $($trend.latest.pass_rate) |
| Duration (s) | $($trend.latest.duration_seconds) |
| Profile | $($trend.latest.profile) |
| File | $($trend.latest.file) |

## Timeline

| Timestamp | Status | Pass Rate | Duration (s) | Profile | File |
|---|---|---:|---:|---|---|
$(($rows -join "`r`n"))
"@

$md | Out-File -FilePath $mdOut -Encoding UTF8
Write-Host "MD written: $mdOut"
Write-Host ""
Write-Host "=== Core Gate Trend Generated ===" -ForegroundColor Green
Write-Host "Exit Code: 0"
exit 0
