#!/usr/bin/env powershell
# Gate Summary Archiver (W9J)
# Archives gate_all_summary_v1 payloads and keeps bounded history + index.
#
# Usage:
#   .\scripts\archive_gate_summary.ps1 -InputJson gate_all_summary.json
#   .\scripts\archive_gate_summary.ps1 -InputJson gate_all_summary.json -ArchiveDir roadmap_ctp/gate_history -MaxFiles 50 -WriteMarkdownIndex
#
# Exit Codes:
#   0 = PASS, 1 = FAIL

param(
    [string]$InputJson = "",
    [string]$ArchiveDir = "roadmap_ctp/gate_history",
    [int]$MaxFiles = 50,
    [string]$Pattern = "gate_all_summary_*.json",
    [switch]$WriteMarkdownIndex = $false
)

$ErrorActionPreference = "Continue"

if (-not $InputJson) {
    Write-Host "InputJson is required." -ForegroundColor Red
    exit 1
}
if (-not (Test-Path -Path $InputJson -PathType Leaf)) {
    Write-Host "InputJson not found: $InputJson" -ForegroundColor Red
    exit 1
}
if ($MaxFiles -lt 1) {
    Write-Host "MaxFiles must be >= 1." -ForegroundColor Red
    exit 1
}
if (-not $Pattern) {
    Write-Host "Pattern is required." -ForegroundColor Red
    exit 1
}

try {
    $payload = Get-Content -Path $InputJson -Raw -Encoding UTF8 | ConvertFrom-Json
} catch {
    Write-Host ("Failed to parse input JSON: {0}" -f $_.Exception.Message) -ForegroundColor Red
    exit 1
}

if (-not $payload.metadata -or $payload.metadata.schema -ne "gate_all_summary_v1") {
    Write-Host "Input JSON is not gate_all_summary_v1." -ForegroundColor Red
    exit 1
}

if (-not (Test-Path -Path $ArchiveDir -PathType Container)) {
    New-Item -Path $ArchiveDir -ItemType Directory -Force | Out-Null
}

$generatedAt = $null
$runTime = Get-Date
if ($payload.metadata -and $payload.metadata.generated_at) {
    try {
        $generatedAt = [datetime]$payload.metadata.generated_at
    } catch {
        $generatedAt = $null
    }
}
if ($generatedAt -eq $null) {
    $generatedAt = $runTime
}

$stamp = $generatedAt.ToString("yyyyMMdd_HHmmss")
$targetName = "gate_all_summary_{0}.json" -f $stamp
$targetPath = Join-Path $ArchiveDir $targetName

if (Test-Path -Path $targetPath -PathType Leaf) {
    $suffix = [guid]::NewGuid().ToString("N").Substring(0, 8)
    $targetName = "gate_all_summary_{0}_{1}.json" -f $stamp, $suffix
    $targetPath = Join-Path $ArchiveDir $targetName
}

Copy-Item -Path $InputJson -Destination $targetPath -Force

$retained = @(Get-ChildItem -Path $ArchiveDir -Filter $Pattern -File | Sort-Object LastWriteTime)
while ($retained.Count -gt $MaxFiles) {
    $oldest = $retained[0]
    Remove-Item -Path $oldest.FullName -Force
    $retained = @($retained | Select-Object -Skip 1)
}
$retained = @(Get-ChildItem -Path $ArchiveDir -Filter $Pattern -File | Sort-Object LastWriteTime)

$entries = @()
foreach ($f in $retained) {
    $entry = @{
        file = $f.Name
        modified = $f.LastWriteTime.ToString("s")
        generated_at = $null
        overall_status = "UNKNOWN"
        overall_exit = $null
        core_status = "UNKNOWN"
        core_profile = ""
        parse_error = $null
    }

    try {
        $itemPayload = Get-Content -Path $f.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($itemPayload.metadata -and $itemPayload.metadata.generated_at) {
            $entry.generated_at = [string]$itemPayload.metadata.generated_at
        }
        if ($itemPayload.overall) {
            if ($itemPayload.overall.status) {
                $entry.overall_status = [string]$itemPayload.overall.status
            }
            if ($itemPayload.overall.exit_code -ne $null) {
                $entry.overall_exit = [int]$itemPayload.overall.exit_code
            }
        }
        $coreGate = @($itemPayload.gates | Where-Object { $_.name -eq "Core-Gate" }) | Select-Object -First 1
        if ($coreGate) {
            if ($coreGate.status) {
                $entry.core_status = [string]$coreGate.status
            }
            if ($coreGate.profile) {
                $entry.core_profile = [string]$coreGate.profile
            }
        }
    } catch {
        $entry.overall_status = "PARSE_ERROR"
        $entry.core_status = "PARSE_ERROR"
        $entry.parse_error = $_.Exception.Message
    }

    $entries += @($entry)
}

$sortedEntries = @($entries | Sort-Object modified -Descending)
$archivedAt = (Get-Date).ToString("s")
$index = @{
    metadata = @{
        generated_at = $archivedAt
        schema = "gate_summary_archive_index_v1"
        archive_dir = $ArchiveDir
        max_files = $MaxFiles
        pattern = $Pattern
    }
    latest = @{
        file = $targetName
        archived_at = $archivedAt
    }
    entries = @($sortedEntries)
}

$indexPath = Join-Path $ArchiveDir "index.json"
$index | ConvertTo-Json -Depth 12 | Out-File -FilePath $indexPath -Encoding UTF8

if ($WriteMarkdownIndex) {
    $rows = @()
    foreach ($e in $sortedEntries) {
        $rows += "| $($e.file) | $($e.generated_at) | $($e.modified) | $($e.overall_status) | $($e.core_status) | $($e.core_profile) |"
    }
    $md = @"
# Gate Summary Archive Index
**Generated:** $archivedAt  
**Schema:** gate_summary_archive_index_v1  
**ArchiveDir:** $ArchiveDir  
**MaxFiles:** $MaxFiles  
**Pattern:** $Pattern

## Latest

| Field | Value |
|---|---|
| File | $($index.latest.file) |
| Archived at | $($index.latest.archived_at) |

## Entries

| File | Generated At | Modified | Overall | Core | Profile |
|---|---|---|---|---|---|
$(($rows -join "`r`n"))
"@
    $mdPath = Join-Path $ArchiveDir "index.md"
    $md | Out-File -FilePath $mdPath -Encoding UTF8
}

Write-Host "=== Gate Summary Archiver ===" -ForegroundColor Green
Write-Host "Archived: $targetPath"
Write-Host "Index: $indexPath"
Write-Host "Entries: $(@($sortedEntries).Count)"
if ($WriteMarkdownIndex) {
    Write-Host "Index(MD): $(Join-Path $ArchiveDir 'index.md')"
}
Write-Host "Exit Code: 0"
exit 0
