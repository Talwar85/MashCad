#!/usr/bin/env powershell
# Gate Archive Dashboard Generator (W9K)
# Builds a compact dashboard from gate_summary_archive_index_v1.
#
# Usage:
#   .\scripts\generate_gate_archive_dashboard.ps1
#   .\scripts\generate_gate_archive_dashboard.ps1 -ArchiveDir roadmap_ctp/gate_history -OutPrefix roadmap_ctp/gate_history/DASH
#
# Exit Codes:
#   0 = PASS, 1 = FAIL

param(
    [string]$ArchiveDir = "roadmap_ctp/gate_history",
    [string]$IndexJson = "",
    [string]$OutPrefix = ""
)

$ErrorActionPreference = "Continue"

if (-not $IndexJson) {
    $IndexJson = Join-Path $ArchiveDir "index.json"
}
if (-not (Test-Path -Path $IndexJson -PathType Leaf)) {
    Write-Host "IndexJson not found: $IndexJson" -ForegroundColor Red
    exit 1
}
if (-not $OutPrefix) {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $OutPrefix = Join-Path $ArchiveDir ("GATE_ARCHIVE_DASHBOARD_{0}" -f $stamp)
}

$jsonOut = "$OutPrefix.json"
$mdOut = "$OutPrefix.md"

try {
    $index = Get-Content -Path $IndexJson -Raw -Encoding UTF8 | ConvertFrom-Json
} catch {
    Write-Host ("Failed to parse IndexJson: {0}" -f $_.Exception.Message) -ForegroundColor Red
    exit 1
}

if (-not $index.metadata -or [string]$index.metadata.schema -ne "gate_summary_archive_index_v1") {
    Write-Host "Invalid archive index schema." -ForegroundColor Red
    exit 1
}

$entries = if ($index.entries) { @($index.entries) } else { @() }
$entriesTotal = $entries.Count
$maxFiles = 0
try { $maxFiles = [int]$index.metadata.max_files } catch { $maxFiles = 0 }
$retentionPercent = if ($maxFiles -gt 0) {
    [math]::Round((($entriesTotal / [double]$maxFiles) * 100.0), 1)
} else { 0.0 }

function CountByValue {
    param([array]$items, [string]$property)
    $map = @{}
    foreach ($i in $items) {
        $k = [string]$i.$property
        if (-not $k) { $k = "(none)" }
        if (-not $map.ContainsKey($k)) { $map[$k] = 0 }
        $map[$k] = [int]$map[$k] + 1
    }
    return $map
}

$overallCounts = CountByValue -items $entries -property "overall_status"
$coreCounts = CountByValue -items $entries -property "core_status"
$profileCounts = CountByValue -items $entries -property "core_profile"
$parseErrorCount = @($entries | Where-Object { $_.parse_error }).Count

$latest = $null
if ($index.latest -and $index.latest.file) {
    $latest = @($entries | Where-Object { $_.file -eq $index.latest.file } | Select-Object -First 1)[0]
}
if (-not $latest -and $entriesTotal -gt 0) {
    $latest = $entries[0]
}

$dashboard = @{
    metadata = @{
        generated_at = (Get-Date).ToString("s")
        schema = "gate_summary_archive_dashboard_v1"
        source_index = $IndexJson
        source_schema = [string]$index.metadata.schema
    }
    capacity = @{
        entries_total = $entriesTotal
        max_files = $maxFiles
        retention_percent = $retentionPercent
    }
    counts = @{
        overall_status = $overallCounts
        core_status = $coreCounts
        core_profile = $profileCounts
        parse_error_entries = $parseErrorCount
    }
    latest = @{
        file = if ($latest) { [string]$latest.file } else { "" }
        modified = if ($latest) { [string]$latest.modified } else { "" }
        generated_at = if ($latest) { [string]$latest.generated_at } else { "" }
        overall_status = if ($latest) { [string]$latest.overall_status } else { "" }
        core_status = if ($latest) { [string]$latest.core_status } else { "" }
        core_profile = if ($latest) { [string]$latest.core_profile } else { "" }
    }
}

$dashboard | ConvertTo-Json -Depth 12 | Out-File -FilePath $jsonOut -Encoding UTF8
Write-Host "JSON written: $jsonOut"

$overallRows = @()
foreach ($k in ($overallCounts.Keys | Sort-Object)) {
    $overallRows += "| $k | $($overallCounts[$k]) |"
}
if ($overallRows.Count -eq 0) { $overallRows += "| (none) | 0 |" }

$coreRows = @()
foreach ($k in ($coreCounts.Keys | Sort-Object)) {
    $coreRows += "| $k | $($coreCounts[$k]) |"
}
if ($coreRows.Count -eq 0) { $coreRows += "| (none) | 0 |" }

$profileRows = @()
foreach ($k in ($profileCounts.Keys | Sort-Object)) {
    $profileRows += "| $k | $($profileCounts[$k]) |"
}
if ($profileRows.Count -eq 0) { $profileRows += "| (none) | 0 |" }

$md = @"
# Gate Archive Dashboard
**Generated:** $($dashboard.metadata.generated_at)  
**Schema:** $($dashboard.metadata.schema)  
**Source index:** $($dashboard.metadata.source_index)

## Capacity

| Metric | Value |
|---|---:|
| Entries total | $($dashboard.capacity.entries_total) |
| Max files | $($dashboard.capacity.max_files) |
| Retention used (%) | $($dashboard.capacity.retention_percent) |

## Overall Status Counts

| Status | Count |
|---|---:|
$(($overallRows -join "`r`n"))

## Core Status Counts

| Status | Count |
|---|---:|
$(($coreRows -join "`r`n"))

## Core Profile Counts

| Profile | Count |
|---|---:|
$(($profileRows -join "`r`n"))

## Latest Entry

| Field | Value |
|---|---|
| File | $($dashboard.latest.file) |
| Modified | $($dashboard.latest.modified) |
| Generated At | $($dashboard.latest.generated_at) |
| Overall Status | $($dashboard.latest.overall_status) |
| Core Status | $($dashboard.latest.core_status) |
| Core Profile | $($dashboard.latest.core_profile) |
"@

$md | Out-File -FilePath $mdOut -Encoding UTF8
Write-Host "MD written: $mdOut"
Write-Host "=== Gate Archive Dashboard Generated ===" -ForegroundColor Green
Write-Host "Exit Code: 0"
exit 0
