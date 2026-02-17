#!/usr/bin/env powershell
# Gate-Evidence Schema Validator (W29 RELEASE OPS TIMEOUT-PROOF)
# Usage:
#   .\scripts\validate_gate_evidence.ps1
#   .\scripts\validate_gate_evidence.ps1 -EvidenceDir roadmap_ctp -Pattern "QA_EVIDENCE_W*.json"
#   .\scripts\validate_gate_evidence.ps1 -EvidencePath roadmap_ctp/QA_EVIDENCE_W5_20260216.json
# Exit Codes:
#   0 = PASS (or WARN when -FailOnWarning is not set)
#   1 = FAIL (schema/data violations) or WARN with -FailOnWarning
# W27: Added validation for delivery_metrics section
# W28: Robust validation for old and new payloads, clearer error output
# W29: Extended semantic checks, suite count validation, timeout-safe operations

param(
    [string]$EvidencePath = "",
    [string]$EvidenceDir = "roadmap_ctp",
    [string]$Pattern = "QA_EVIDENCE_W*.json",
    [switch]$FailOnWarning = $false
)

$ErrorActionPreference = "Continue"

function Add-Issue {
    param(
        [ref]$Issues,
        [string]$Severity,
        [string]$Code,
        [string]$Message
    )
    $Issues.Value += @(
        [pscustomobject]@{
            severity = $Severity
            code = $Code
            message = $Message
        }
    )
}

function Has-Prop {
    param(
        $Obj,
        [string]$Name
    )
    if ($null -eq $Obj) {
        return $false
    }
    return $Obj.PSObject.Properties.Name -contains $Name
}

function Get-StatusText {
    param($Gate)

    if (Has-Prop -Obj $Gate -Name "status_class") {
        return [string]$Gate.status_class
    }
    if (Has-Prop -Obj $Gate -Name "status") {
        return [string]$Gate.status
    }
    return ""
}

function Test-NonNegativeNumber {
    param($Value)
    try {
        $parsed = [double]$Value
        return $parsed -ge 0
    } catch {
        return $false
    }
}

function Test-NonNegativeInt {
    param($Value)
    try {
        $parsed = [int]$Value
        return $parsed -ge 0
    } catch {
        return $false
    }
}

function Validate-GateCommon {
    param(
        [string]$GateName,
        $Gate,
        [ref]$Issues,
        [bool]$RequireTestCounters = $true
    )

    if ($null -eq $Gate) {
        Add-Issue -Issues $Issues -Severity "FAIL" -Code "gate_missing" -Message "$GateName is missing"
        return
    }

    $allowedStatus = @(
        "PASS",
        "FAIL",
        "ERROR",
        "UNKNOWN",
        "BLOCKED",
        "BLOCKED_INFRA",
        "WARNING",
        "CLEAN",
        "VIOLATIONS"
    )

    $status = (Get-StatusText -Gate $Gate).Trim()
    if (-not $status) {
        Add-Issue -Issues $Issues -Severity "FAIL" -Code "gate_status_missing" -Message "$GateName has no status/status_class"
    } elseif ($allowedStatus -notcontains $status) {
        Add-Issue -Issues $Issues -Severity "FAIL" -Code "gate_status_invalid" -Message "$GateName has invalid status '$status'"
    }

    if (Has-Prop -Obj $Gate -Name "duration_seconds") {
        if (-not (Test-NonNegativeNumber -Value $Gate.duration_seconds)) {
            Add-Issue -Issues $Issues -Severity "FAIL" -Code "gate_duration_invalid" -Message "$GateName.duration_seconds must be >= 0"
        }
    }

    if ($RequireTestCounters) {
        foreach ($field in @("passed", "failed", "skipped", "errors")) {
            if (Has-Prop -Obj $Gate -Name $field) {
                if (-not (Test-NonNegativeInt -Value $Gate.$field)) {
                    Add-Issue -Issues $Issues -Severity "FAIL" -Code "gate_counter_invalid" -Message "$GateName.$field must be a non-negative integer"
                }
            } else {
                Add-Issue -Issues $Issues -Severity "WARN" -Code "gate_counter_missing" -Message "$GateName.$field missing"
            }
        }

        # Basic semantic consistency check.
        if ($status -eq "PASS") {
            $failed = $(if (Has-Prop -Obj $Gate -Name "failed") { [int]$Gate.failed } else { 0 })
            $errors = $(if (Has-Prop -Obj $Gate -Name "errors") { [int]$Gate.errors } else { 0 })
            if ($failed -gt 0 -or $errors -gt 0) {
                Add-Issue -Issues $Issues -Severity "FAIL" -Code "gate_semantics_invalid" -Message "$GateName is PASS but failed/errors > 0"
            }
        }
    }

    if ($GateName -eq "ui_gate" -and ($status -eq "BLOCKED" -or $status -eq "BLOCKED_INFRA")) {
        $hasBlocker = (Has-Prop -Obj $Gate -Name "blocker") -or (Has-Prop -Obj $Gate -Name "blocker_type")
        if (-not $hasBlocker) {
            Add-Issue -Issues $Issues -Severity "WARN" -Code "ui_blocker_missing" -Message "ui_gate is blocked but blocker metadata is missing"
        }
    }

    if ($GateName -eq "hygiene_gate") {
        if (Has-Prop -Obj $Gate -Name "violations_count") {
            if (-not (Test-NonNegativeInt -Value $Gate.violations_count)) {
                Add-Issue -Issues $Issues -Severity "FAIL" -Code "hygiene_violations_invalid" -Message "hygiene_gate.violations_count must be a non-negative integer"
            }
        } else {
            Add-Issue -Issues $Issues -Severity "WARN" -Code "hygiene_violations_missing" -Message "hygiene_gate.violations_count missing"
        }
    }
}

function Validate-DeliveryMetrics {
    param(
        $Metrics,
        [ref]$Issues
    )

    if ($null -eq $Metrics) {
        Add-Issue -Issues $Issues -Severity "WARN" -Code "delivery_metrics_missing" -Message "delivery_metrics section is missing (W27+)"
        return
    }

    # W27: Validate delivery_completion_ratio (0.0 to 1.0)
    if (Has-Prop -Obj $Metrics -Name "delivery_completion_ratio") {
        try {
            $ratio = [double]$Metrics.delivery_completion_ratio
            if ($ratio -lt 0 -or $ratio -gt 1) {
                Add-Issue -Issues $Issues -Severity "FAIL" -Code "delivery_ratio_invalid" -Message "delivery_completion_ratio must be between 0 and 1, got: $ratio"
            }
        } catch {
            Add-Issue -Issues $Issues -Severity "WARN" -Code "delivery_ratio_parse_error" -Message "delivery_completion_ratio is not a valid number"
        }
    } else {
        Add-Issue -Issues $Issues -Severity "WARN" -Code "delivery_ratio_missing" -Message "delivery_completion_ratio missing (W27+ field)"
    }

    # W27: Validate validation_runtime_seconds
    if (Has-Prop -Obj $Metrics -Name "validation_runtime_seconds") {
        if (-not (Test-NonNegativeNumber -Value $Metrics.validation_runtime_seconds)) {
            Add-Issue -Issues $Issues -Severity "FAIL" -Code "validation_runtime_invalid" -Message "validation_runtime_seconds must be >= 0"
        }
    } else {
        Add-Issue -Issues $Issues -Severity "WARN" -Code "validation_runtime_missing" -Message "validation_runtime_seconds missing (W27+ field)"
    }

    # W27: Validate blocker_type
    if (Has-Prop -Obj $Metrics -Name "blocker_type") {
        $allowedTypes = @("OPENGL_CONTEXT", "ACCESS_VIOLATION", "FATAL_ERROR", "IMPORT_ERROR", "LOCK_TEMP", "OPENCL_NOISE", $null, "")
        if ($Metrics.blocker_type -notin $allowedTypes) {
            Add-Issue -Issues $Issues -Severity "WARN" -Code "blocker_type_unknown" -Message "Unknown blocker_type: '$($Metrics.blocker_type)'"
        }
    }

    # W27: Validate failed_suite_count
    if (Has-Prop -Obj $Metrics -Name "failed_suite_count") {
        if (-not (Test-NonNegativeInt -Value $Metrics.failed_suite_count)) {
            Add-Issue -Issues $Issues -Severity "FAIL" -Code "failed_suite_count_invalid" -Message "failed_suite_count must be a non-negative integer"
        }
    } else {
        Add-Issue -Issues $Issues -Severity "WARN" -Code "failed_suite_count_missing" -Message "failed_suite_count missing (W27+ field)"
    }

    # W27: Validate error_suite_count
    if (Has-Prop -Obj $Metrics -Name "error_suite_count") {
        if (-not (Test-NonNegativeInt -Value $Metrics.error_suite_count)) {
            Add-Issue -Issues $Issues -Severity "FAIL" -Code "error_suite_count_invalid" -Message "error_suite_count must be a non-negative integer"
        }
    } else {
        Add-Issue -Issues $Issues -Severity "WARN" -Code "error_suite_count_missing" -Message "error_suite_count missing (W27+ field)"
    }

    # W28: Validate total_suite_count and passed_suite_count (optional, new)
    if (Has-Prop -Obj $Metrics -Name "total_suite_count") {
        if (-not (Test-NonNegativeInt -Value $Metrics.total_suite_count)) {
            Add-Issue -Issues $Issues -Severity "WARN" -Code "total_suite_count_invalid" -Message "total_suite_count must be a non-negative integer"
        }
    }

    if (Has-Prop -Obj $Metrics -Name "passed_suite_count") {
        if (-not (Test-NonNegativeInt -Value $Metrics.passed_suite_count)) {
            Add-Issue -Issues $Issues -Severity "WARN" -Code "passed_suite_count_invalid" -Message "passed_suite_count must be a non-negative integer"
        }
        # W28: Semantic check - passed cannot exceed total
        if (Has-Prop -Obj $Metrics -Name "total_suite_count") {
            $total = [int]$Metrics.total_suite_count
            $passed = [int]$Metrics.passed_suite_count
            if ($passed -gt $total -and $total -gt 0) {
                Add-Issue -Issues $Issues -Severity "FAIL" -Code "suite_count_semantic_error" -Message "passed_suite_count ($passed) cannot exceed total_suite_count ($total)"
            }
        }
    }
}

function Validate-EvidenceFile {
    param([System.IO.FileInfo]$File)

    $issues = @()

    $raw = $null
    $data = $null
    try {
        $raw = Get-Content -Path $File.FullName -Raw -Encoding UTF8
        $data = $raw | ConvertFrom-Json
    } catch {
        Add-Issue -Issues ([ref]$issues) -Severity "FAIL" -Code "json_parse_error" -Message "$($File.Name): $($_.Exception.Message)"
        return [pscustomobject]@{
            file = $File.Name
            path = $File.FullName
            status = "FAIL"
            fail_count = 1
            warn_count = 0
            issues = @($issues)
        }
    }

    if (-not (Has-Prop -Obj $data -Name "metadata")) {
        Add-Issue -Issues ([ref]$issues) -Severity "FAIL" -Code "metadata_missing" -Message "metadata is missing"
    } else {
        if (-not (Has-Prop -Obj $data.metadata -Name "date")) {
            Add-Issue -Issues ([ref]$issues) -Severity "FAIL" -Code "metadata_date_missing" -Message "metadata.date missing"
        }
        if (-not (Has-Prop -Obj $data.metadata -Name "time")) {
            Add-Issue -Issues ([ref]$issues) -Severity "FAIL" -Code "metadata_time_missing" -Message "metadata.time missing"
        }
    }

    if (-not (Has-Prop -Obj $data -Name "summary")) {
        Add-Issue -Issues ([ref]$issues) -Severity "FAIL" -Code "summary_missing" -Message "summary is missing"
    } else {
        Validate-GateCommon -GateName "core_gate" -Gate $data.summary.core_gate -Issues ([ref]$issues) -RequireTestCounters $true
        Validate-GateCommon -GateName "ui_gate" -Gate $data.summary.ui_gate -Issues ([ref]$issues) -RequireTestCounters $true
        Validate-GateCommon -GateName "pi010_gate" -Gate $data.summary.pi010_gate -Issues ([ref]$issues) -RequireTestCounters $true
        Validate-GateCommon -GateName "hygiene_gate" -Gate $data.summary.hygiene_gate -Issues ([ref]$issues) -RequireTestCounters $false
    }

    # W27: Validate delivery_metrics section
    if (Has-Prop -Obj $data -Name "delivery_metrics") {
        Validate-DeliveryMetrics -Metrics $data.delivery_metrics -Issues ([ref]$issues)
    } else {
        Add-Issue -Issues ([ref]$issues) -Severity "WARN" -Code "delivery_metrics_missing" -Message "delivery_metrics section missing (W27)"
    }

    $failCount = @($issues | Where-Object { $_.severity -eq "FAIL" }).Count
    $warnCount = @($issues | Where-Object { $_.severity -eq "WARN" }).Count
    $status = if ($failCount -gt 0) { "FAIL" } elseif ($warnCount -gt 0) { "WARN" } else { "PASS" }

    return [pscustomobject]@{
        file = $File.Name
        path = $File.FullName
        status = $status
        fail_count = $failCount
        warn_count = $warnCount
        issues = @($issues)
    }
}

Write-Host "=== Gate-Evidence Validator (W8) ===" -ForegroundColor Cyan
Write-Host "Timestamp: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host "FailOnWarning: $FailOnWarning"

$files = @()
if ($EvidencePath) {
    if (-not (Test-Path -Path $EvidencePath -PathType Leaf)) {
        Write-Host "Evidence file not found: $EvidencePath" -ForegroundColor Red
        exit 1
    }
    $files = @(Get-Item -Path $EvidencePath)
} else {
    $files = @(Get-ChildItem -Path $EvidenceDir -Filter $Pattern -File -ErrorAction SilentlyContinue | Sort-Object LastWriteTime)
}

if ($files.Count -eq 0) {
    Write-Host "No evidence files found." -ForegroundColor Red
    exit 1
}

Write-Host "Files: $($files.Count)"
if (-not $EvidencePath) {
    Write-Host "Source: $EvidenceDir/$Pattern"
}
Write-Host ""

$results = @()
foreach ($f in $files) {
    $r = Validate-EvidenceFile -File $f
    $results += @($r)

    $color = switch ($r.status) {
        "PASS" { "Green" }
        "WARN" { "Yellow" }
        default { "Red" }
    }

    Write-Host ("[{0}] {1} (fail={2}, warn={3})" -f $r.status, $r.file, $r.fail_count, $r.warn_count) -ForegroundColor $color
    foreach ($issue in $r.issues) {
        $issueColor = if ($issue.severity -eq "FAIL") { "Red" } else { "Yellow" }
        Write-Host ("  - {0}: {1} ({2})" -f $issue.severity, $issue.message, $issue.code) -ForegroundColor $issueColor
    }
}

$passCount = @($results | Where-Object { $_.status -eq "PASS" }).Count
$warnCount = @($results | Where-Object { $_.status -eq "WARN" }).Count
$failCount = @($results | Where-Object { $_.status -eq "FAIL" }).Count

$exitCode = 0
if ($failCount -gt 0) {
    $exitCode = 1
} elseif ($FailOnWarning -and $warnCount -gt 0) {
    $exitCode = 1
}

Write-Host ""
Write-Host "=== Validation Summary ===" -ForegroundColor Cyan
Write-Host "PASS: $passCount"
Write-Host "WARN: $warnCount"
Write-Host "FAIL: $failCount"
Write-Host "Exit Code: $exitCode"

exit $exitCode
