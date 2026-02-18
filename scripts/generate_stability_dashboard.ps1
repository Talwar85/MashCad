#!/usr/bin/env powershell
# Stability Dashboard Seed Generator (W7D)
# Usage:
#   .\scripts\generate_stability_dashboard.ps1
#   .\scripts\generate_stability_dashboard.ps1 -EvidenceDir roadmap_ctp -Pattern "QA_EVIDENCE_W*.json" -OutPrefix roadmap_ctp/STABILITY_DASHBOARD_SEED_W7

param(
    [string]$EvidenceDir = "roadmap_ctp",
    [string]$Pattern = "QA_EVIDENCE_W*.json",
    [string]$OutPrefix = "",
    [int]$MaxRuns = 50
)

$ErrorActionPreference = "Continue"

if (-not $OutPrefix) {
    $ts = Get-Date -Format "yyyyMMdd_HHmmss"
    $OutPrefix = Join-Path $EvidenceDir "STABILITY_DASHBOARD_SEED_$ts"
}

$jsonPath = "$OutPrefix.json"
$mdPath = "$OutPrefix.md"

Write-Host "=== Stability Dashboard Seed Generator ===" -ForegroundColor Cyan
Write-Host "Timestamp: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host "EvidenceDir: $EvidenceDir"
Write-Host "Pattern: $Pattern"
Write-Host "OutPrefix: $OutPrefix"
Write-Host ""

$files = Get-ChildItem -Path $EvidenceDir -Filter $Pattern -File -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime

if (-not $files -or $files.Count -eq 0) {
    Write-Host "No evidence files found." -ForegroundColor Red
    exit 1
}

function Get-GateSnapshot {
    param($SummaryObj, [string]$GateName)

    if ($null -eq $SummaryObj) {
        return @{
            status = "UNKNOWN"
            duration_seconds = $null
            passed = $null
            failed = $null
            skipped = $null
            errors = $null
        }
    }

    $gate = $SummaryObj.$GateName
    if ($null -eq $gate) {
        return @{
            status = "UNKNOWN"
            duration_seconds = $null
            passed = $null
            failed = $null
            skipped = $null
            errors = $null
        }
    }

    $status = ""
    if ($gate.PSObject.Properties.Name -contains "status_class") {
        $status = [string]$gate.status_class
    } elseif ($gate.PSObject.Properties.Name -contains "status") {
        $status = [string]$gate.status
    } else {
        $status = "UNKNOWN"
    }

    return @{
        status = $status
        duration_seconds = $(if ($gate.PSObject.Properties.Name -contains "duration_seconds") { $gate.duration_seconds } else { $null })
        passed = $(if ($gate.PSObject.Properties.Name -contains "passed") { $gate.passed } else { $null })
        failed = $(if ($gate.PSObject.Properties.Name -contains "failed") { $gate.failed } else { $null })
        skipped = $(if ($gate.PSObject.Properties.Name -contains "skipped") { $gate.skipped } else { $null })
        errors = $(if ($gate.PSObject.Properties.Name -contains "errors") { $gate.errors } else { $null })
    }
}

$runs = @()
foreach ($f in $files) {
    try {
        $raw = Get-Content $f.FullName -Raw -Encoding UTF8
        $data = $raw | ConvertFrom-Json

        $dateStr = ""
        $timeStr = "00:00:00"
        if ($data.PSObject.Properties.Name -contains "metadata") {
            if ($data.metadata.PSObject.Properties.Name -contains "date") {
                $dateStr = [string]$data.metadata.date
            }
            if ($data.metadata.PSObject.Properties.Name -contains "time") {
                $timeStr = [string]$data.metadata.time
            }
        }

        $combined = "$dateStr $timeStr".Trim()
        try {
            if ($combined) {
                $dt = [datetime]$combined
            } else {
                $dt = $f.LastWriteTime
            }
        } catch {
            $dt = $f.LastWriteTime
        }

        $summary = $null
        if ($data.PSObject.Properties.Name -contains "summary") {
            $summary = $data.summary
        }

        $core = Get-GateSnapshot -SummaryObj $summary -GateName "core_gate"
        $ui = Get-GateSnapshot -SummaryObj $summary -GateName "ui_gate"
        $pi10 = Get-GateSnapshot -SummaryObj $summary -GateName "pi010_gate"
        $hygiene = Get-GateSnapshot -SummaryObj $summary -GateName "hygiene_gate"

        $uiBlockerType = $null
        if ($summary -and $summary.ui_gate) {
            if ($summary.ui_gate.PSObject.Properties.Name -contains "blocker_type") {
                $uiBlockerType = $summary.ui_gate.blocker_type
            } elseif ($summary.ui_gate.PSObject.Properties.Name -contains "blocker") {
                if ($summary.ui_gate.blocker -and $summary.ui_gate.blocker.PSObject.Properties.Name -contains "type") {
                    $uiBlockerType = $summary.ui_gate.blocker.type
                }
            }
        }

        $runs += @{
            run_id = $f.BaseName
            timestamp = $dt.ToString("s")
            source_file = $f.Name
            core_gate = $core
            ui_gate = $ui
            pi010_gate = $pi10
            hygiene_gate = $hygiene
            ui_blocker_type = $uiBlockerType
        }
    } catch {
        Write-Host "Warning: failed to parse $($f.Name): $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

if ($runs.Count -eq 0) {
    Write-Host "No parseable evidence runs found." -ForegroundColor Red
    exit 1
}

$orderedRuns = $runs | Sort-Object { [datetime]$_.timestamp }
if ($orderedRuns.Count -gt $MaxRuns) {
    $orderedRuns = $orderedRuns | Select-Object -Last $MaxRuns
}

$corePassCount = @($orderedRuns | Where-Object { ($_.core_gate.status -eq "PASS") }).Count
$coreFailCount = $orderedRuns.Count - $corePassCount

$uiBlockedInfraCount = @($orderedRuns | Where-Object { $_.ui_gate.status -eq "BLOCKED_INFRA" }).Count
$uiBlockedCount = @($orderedRuns | Where-Object { $_.ui_gate.status -eq "BLOCKED" -or $_.ui_gate.status -eq "BLOCKED_INFRA" }).Count
$uiFailCount = @($orderedRuns | Where-Object { $_.ui_gate.status -eq "FAIL" }).Count

$coreDurations = @($orderedRuns | ForEach-Object { $_.core_gate.duration_seconds } | Where-Object { $null -ne $_ })
$avgCoreDuration = $null
if ($coreDurations.Count -gt 0) {
    $avgCoreDuration = [math]::Round((($coreDurations | Measure-Object -Average).Average), 2)
}

$latest = $orderedRuns | Select-Object -Last 1

$dashboard = @{
    metadata = @{
        generated_at = (Get-Date).ToString("s")
        source_pattern = $Pattern
        source_dir = $EvidenceDir
        source_files_count = $files.Count
        runs_tracked = $orderedRuns.Count
        schema = "stability_dashboard_seed_v1"
    }
    metrics = @{
        core_pass_count = $corePassCount
        core_fail_count = $coreFailCount
        core_pass_rate = [math]::Round(($corePassCount / [double]$orderedRuns.Count) * 100.0, 2)
        ui_blocked_count = $uiBlockedCount
        ui_blocked_infra_count = $uiBlockedInfraCount
        ui_fail_count = $uiFailCount
        avg_core_duration_seconds = $avgCoreDuration
    }
    latest = $latest
    timeline = @($orderedRuns)
}

$dashboard | ConvertTo-Json -Depth 20 | Out-File -FilePath $jsonPath -Encoding UTF8
Write-Host "JSON written: $jsonPath"

$rows = @()
foreach ($r in $orderedRuns) {
    $rows += "| $($r.timestamp) | $($r.core_gate.status) | $($r.ui_gate.status) | $($r.pi010_gate.status) | $($r.hygiene_gate.status) | $($r.core_gate.duration_seconds) |"
}

$md = @"
# Stability Dashboard Seed
**Generated:** $($dashboard.metadata.generated_at)
**Schema:** $($dashboard.metadata.schema)
**Runs tracked:** $($dashboard.metadata.runs_tracked)

## Key Metrics

| Metric | Value |
|---|---|
| Core pass count | $($dashboard.metrics.core_pass_count) |
| Core fail count | $($dashboard.metrics.core_fail_count) |
| Core pass rate | $($dashboard.metrics.core_pass_rate)% |
| UI blocked count | $($dashboard.metrics.ui_blocked_count) |
| UI blocked infra count | $($dashboard.metrics.ui_blocked_infra_count) |
| UI fail count | $($dashboard.metrics.ui_fail_count) |
| Avg core duration (s) | $($dashboard.metrics.avg_core_duration_seconds) |

## Latest Snapshot

| Field | Value |
|---|---|
| Run ID | $($latest.run_id) |
| Timestamp | $($latest.timestamp) |
| Core status | $($latest.core_gate.status) |
| UI status | $($latest.ui_gate.status) |
| PI-010 status | $($latest.pi010_gate.status) |
| Hygiene status | $($latest.hygiene_gate.status) |
| UI blocker type | $($latest.ui_blocker_type) |

## Timeline

| Timestamp | Core | UI | PI-010 | Hygiene | Core Duration (s) |
|---|---|---|---|---|---|
$(($rows -join "`r`n"))
"@

$md | Out-File -FilePath $mdPath -Encoding UTF8
Write-Host "MD written: $mdPath"
Write-Host ""
Write-Host "=== Stability Dashboard Seed Generated ===" -ForegroundColor Green
Write-Host "Exit Code: 0"
exit 0
