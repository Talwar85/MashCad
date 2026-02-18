#!/usr/bin/env powershell
# Gate Summary Archive Validator (W9K)
# Validates roadmap_ctp/gate_history index + referenced gate_all summaries.
#
# Usage:
#   .\scripts\validate_gate_summary_archive.ps1
#   .\scripts\validate_gate_summary_archive.ps1 -ArchiveDir roadmap_ctp/gate_history -FailOnParseError
#   .\scripts\validate_gate_summary_archive.ps1 -JsonOut roadmap_ctp/gate_history/validation.json
#
# Exit Codes:
#   0 = PASS, 1 = FAIL

param(
    [string]$ArchiveDir = "roadmap_ctp/gate_history",
    [string]$IndexJson = "",
    [switch]$FailOnParseError = $false,
    [string]$JsonOut = ""
)

$ErrorActionPreference = "Continue"

if (-not $IndexJson) {
    $IndexJson = Join-Path $ArchiveDir "index.json"
}

if (-not (Test-Path -Path $ArchiveDir -PathType Container)) {
    Write-Host "ArchiveDir not found: $ArchiveDir" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path -Path $IndexJson -PathType Leaf)) {
    Write-Host "IndexJson not found: $IndexJson" -ForegroundColor Red
    exit 1
}

try {
    $index = Get-Content -Path $IndexJson -Raw -Encoding UTF8 | ConvertFrom-Json
} catch {
    Write-Host ("Failed to parse IndexJson: {0}" -f $_.Exception.Message) -ForegroundColor Red
    exit 1
}

$violations = @()
$warnings = @()

if (-not $index.metadata -or [string]$index.metadata.schema -ne "gate_summary_archive_index_v1") {
    $violations += "Invalid index schema (expected gate_summary_archive_index_v1)."
}

$maxFiles = 0
try {
    $maxFiles = [int]$index.metadata.max_files
} catch {
    $maxFiles = 0
}
if ($maxFiles -lt 1) {
    $violations += "metadata.max_files must be >= 1."
}

$entries = @()
if ($index.entries) {
    $entries = @($index.entries)
}

if ($maxFiles -ge 1 -and $entries.Count -gt $maxFiles) {
    $violations += ("entries count {0} exceeds max_files {1}." -f $entries.Count, $maxFiles)
}

$latestFile = ""
if ($index.latest -and $index.latest.file) {
    $latestFile = [string]$index.latest.file
}
if (-not $latestFile) {
    $violations += "latest.file is missing."
} else {
    $latestPath = Join-Path $ArchiveDir $latestFile
    if (-not (Test-Path -Path $latestPath -PathType Leaf)) {
        $violations += ("latest.file does not exist in archive dir: {0}" -f $latestFile)
    }
}

$parseErrorCount = 0
$entriesChecked = 0
$missingFiles = 0
$summarySchemaMismatches = 0
$lastModified = $null
$orderViolationCount = 0

foreach ($entry in $entries) {
    $entriesChecked += 1
    $fileName = [string]$entry.file
    if (-not $fileName) {
        $violations += "entry.file missing."
        continue
    }

    $filePath = Join-Path $ArchiveDir $fileName
    if (-not (Test-Path -Path $filePath -PathType Leaf)) {
        $missingFiles += 1
        $violations += ("Missing archive file: {0}" -f $fileName)
        continue
    }

    # Validate descending modified order in index entries.
    $modifiedRaw = [string]$entry.modified
    if ($modifiedRaw) {
        try {
            $modifiedTs = [datetime]$modifiedRaw
            if ($lastModified -ne $null -and $modifiedTs -gt $lastModified) {
                $orderViolationCount += 1
                $violations += ("Entries are not sorted by modified desc (file {0})." -f $fileName)
            }
            $lastModified = $modifiedTs
        } catch {
            $warnings += ("entry.modified parse failed for file {0}." -f $fileName)
        }
    }

    try {
        $summary = Get-Content -Path $filePath -Raw -Encoding UTF8 | ConvertFrom-Json
        $summarySchema = if ($summary.metadata) { [string]$summary.metadata.schema } else { "" }
        if ($summarySchema -ne "gate_all_summary_v1") {
            $summarySchemaMismatches += 1
            $violations += ("Summary schema mismatch in {0}: {1}" -f $fileName, $summarySchema)
        }
    } catch {
        $parseErrorCount += 1
        $msg = ("Failed to parse summary {0}: {1}" -f $fileName, $_.Exception.Message)
        if ($FailOnParseError) {
            $violations += $msg
        } else {
            $warnings += $msg
        }
    }

    if ($entry.parse_error) {
        $parseErrorCount += 1
        $msg = ("Index entry parse_error in {0}: {1}" -f $fileName, [string]$entry.parse_error)
        if ($FailOnParseError) {
            $violations += $msg
        } else {
            $warnings += $msg
        }
    }
}

$validation = @{
    metadata = @{
        generated_at = (Get-Date).ToString("s")
        schema = "gate_summary_archive_validation_v1"
        archive_dir = $ArchiveDir
        index_json = $IndexJson
        fail_on_parse_error = [bool]$FailOnParseError
    }
    summary = @{
        entries_checked = $entriesChecked
        max_files = $maxFiles
        missing_files = $missingFiles
        parse_error_count = $parseErrorCount
        summary_schema_mismatches = $summarySchemaMismatches
        order_violations = $orderViolationCount
        violation_count = @($violations).Count
        warning_count = @($warnings).Count
        status = if (@($violations).Count -eq 0) { "PASS" } else { "FAIL" }
    }
    violations = @($violations)
    warnings = @($warnings)
}

if ($JsonOut) {
    $validation | ConvertTo-Json -Depth 10 | Out-File -FilePath $JsonOut -Encoding UTF8
    Write-Host "JSON written: $JsonOut"
}

Write-Host "=== Gate Summary Archive Validation ===" -ForegroundColor Cyan
Write-Host ("Entries checked: {0}" -f $entriesChecked)
Write-Host ("Violations: {0}" -f @($violations).Count)
Write-Host ("Warnings: {0}" -f @($warnings).Count)
Write-Host ("Status: {0}" -f $validation.summary.status)
Write-Host ("Exit Code: {0}" -f $(if (@($violations).Count -eq 0) { 0 } else { 1 }))

if (@($violations).Count -gt 0) {
    foreach ($v in $violations) {
        Write-Host ("  - {0}" -f $v) -ForegroundColor Red
    }
    exit 1
}

if (@($warnings).Count -gt 0) {
    foreach ($w in $warnings) {
        Write-Host ("  - {0}" -f $w) -ForegroundColor Yellow
    }
}

exit 0
