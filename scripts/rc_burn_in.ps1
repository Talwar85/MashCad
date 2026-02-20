#!/usr/bin/env powershell
# RC Burn-in Script - QA-010
# Runs extended stability tests for V1.0 Release Candidate
# Usage: .\scripts\rc_burn_in.ps1 [-Cycles 10] [-DurationDays 7] [-ReportDir "roadmap_ctp/burn_in"]
# Exit Codes: 0 = ALL PASS, 1 = BURN-IN FAILED

param(
    [int]$Cycles = 10,                    # Number of test cycles to run
    [int]$DurationDays = 7,               # Simulated burn-in period (for report metadata)
    [string]$ReportDir = "roadmap_ctp/burn_in",
    [ValidateSet("full", "fast", "stress")]
    [string]$Mode = "full",               # full = all gates, fast = core only, stress = extended stress tests
    [switch]$ContinueOnFailure = $false,  # Continue running cycles even if one fails
    [switch]$GenerateReport = $true,      # Generate final markdown report
    [switch]$DryRun = $false,             # Show what would be run without executing
    [string]$JsonOut = "",                # Output JSON summary to file
    [int]$StressTestIterations = 100      # Iterations for stress tests
)

$ErrorActionPreference = "Continue"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "    MashCAD RC Burn-in Test Suite      " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Timestamp: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host "Cycles: $Cycles"
Write-Host "Duration (simulated): $DurationDays days"
Write-Host "Mode: $Mode"
Write-Host "ContinueOnFailure: $ContinueOnFailure"
Write-Host "ReportDir: $ReportDir"
Write-Host "StressTestIterations: $StressTestIterations"
Write-Host ""

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir

# Ensure report directory exists
if (-not (Test-Path -Path $ReportDir)) {
    New-Item -ItemType Directory -Path $ReportDir -Force | Out-Null
    Write-Host "Created report directory: $ReportDir" -ForegroundColor Yellow
}

# Initialize cycle results tracking
$cycleResults = @()
$overallStart = Get-Date

# Gate scripts to run based on mode
$gateScripts = @()
if ($Mode -eq "full") {
    $gateScripts = @(
        @{ Name = "Core-Gate"; Script = "gate_core.ps1"; Args = @("-Profile", "full") },
        @{ Name = "UI-Gate"; Script = "gate_ui.ps1"; Args = @() },
        @{ Name = "Hygiene-Gate"; Script = "hygiene_check.ps1"; Args = @() }
    )
} elseif ($Mode -eq "fast") {
    $gateScripts = @(
        @{ Name = "Core-Gate"; Script = "gate_core.ps1"; Args = @("-Profile", "red_flag") }
    )
} elseif ($Mode -eq "stress") {
    $gateScripts = @(
        @{ Name = "Core-Gate"; Script = "gate_core.ps1"; Args = @("-Profile", "full") },
        @{ Name = "Stress-Tests"; Script = $null; Args = @() }  # Special handling
    )
}

if ($DryRun) {
    Write-Host "=== DRY RUN MODE ===" -ForegroundColor Yellow
    Write-Host "Would run $Cycles cycles of:"
    foreach ($gate in $gateScripts) {
        $argsStr = if ($gate.Args.Count -gt 0) { " " + ($gate.Args -join " ") } else { "" }
        Write-Host "  - $($gate.Name)$argsStr"
    }
    Write-Host ""
    Write-Host "Stress test iterations: $StressTestIterations"
    Write-Host "Report would be generated in: $ReportDir"
    exit 0
}

# Function to run a single gate and capture results
function Invoke-Gate {
    param(
        [string]$GateName,
        [string]$Script,
        [array]$Arguments
    )
    
    $startTime = Get-Date
    $result = & powershell -ExecutionPolicy Bypass -File "$scriptDir\$Script" @Arguments 2>&1
    $exitCode = $LASTEXITCODE
    $endTime = Get-Date
    $duration = ($endTime - $startTime).TotalSeconds
    
    # Parse status from output
    $status = "UNKNOWN"
    $passRate = $null
    $passed = 0
    $failed = 0
    $skipped = 0
    
    foreach ($line in $result) {
        $lineStr = $line.ToString()
        if ($lineStr -match "Status:\s+(PASS|FAIL|BLOCKED_INFRA|BLOCKED|CLEAN|VIOLATIONS)") {
            $status = $matches[1]
        }
        if ($lineStr -match "Pass-Rate:\s+([\d.]+)%") {
            $passRate = [double]$matches[1]
        }
        if ($lineStr -match "(\d+) passed") {
            $passed = [int]$matches[1]
        }
        if ($lineStr -match "(\d+) failed") {
            $failed = [int]$matches[1]
        }
        if ($lineStr -match "(\d+) skipped") {
            $skipped = [int]$matches[1]
        }
    }
    
    return @{
        Name = $GateName
        Status = $status
        ExitCode = $exitCode
        Duration = $duration
        PassRate = $passRate
        Passed = $passed
        Failed = $failed
        Skipped = $skipped
        Output = $result
    }
}

# Function to run stress tests
function Invoke-StressTests {
    param([int]$Iterations)
    
    Write-Host "  Running stress tests ($Iterations iterations)..." -ForegroundColor Yellow
    
    $startTime = Get-Date
    $stressArgs = @(
        "-m", "pytest",
        "test/test_rc_burn_in.py",
        "-v",
        "--tb=short",
        "-k", "stress",
        f"--iterations={Iterations}"
    )
    
    $result = & conda run -n cad_env python @stressArgs 2>&1
    $exitCode = $LASTEXITCODE
    $endTime = Get-Date
    $duration = ($endTime - $startTime).TotalSeconds
    
    # Parse results
    $passed = 0
    $failed = 0
    $skipped = 0
    foreach ($line in $result) {
        $lineStr = $line.ToString()
        if ($lineStr -match "(\d+) passed") {
            $passed = [int]$matches[1]
        }
        if ($lineStr -match "(\d+) failed") {
            $failed = [int]$matches[1]
        }
        if ($lineStr -match "(\d+) skipped") {
            $skipped = [int]$matches[1]
        }
    }
    
    $total = $passed + $failed + $skipped
    $passRate = if ($total -gt 0) { [math]::Round(($passed / $total) * 100, 1) } else { 0 }
    $status = if ($exitCode -eq 0) { "PASS" } else { "FAIL" }
    
    return @{
        Name = "Stress-Tests"
        Status = $status
        ExitCode = $exitCode
        Duration = $duration
        PassRate = $passRate
        Passed = $passed
        Failed = $failed
        Skipped = $skipped
        Output = $result
    }
}

# Main burn-in loop
$totalFailures = 0
$cycleFailures = 0

for ($cycle = 1; $cycle -le $Cycles; $cycle++) {
    Write-Host ""
    Write-Host "=== Cycle $cycle/$Cycles ===" -ForegroundColor Cyan
    Write-Host "Started: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
    
    $cycleStart = Get-Date
    $cycleGateResults = @()
    $cyclePassed = $true
    
    foreach ($gate in $gateScripts) {
        Write-Host ""
        Write-Host "Running $($gate.Name)..." -ForegroundColor Yellow
        
        if ($gate.Name -eq "Stress-Tests") {
            $gateResult = Invoke-StressTests -Iterations $StressTestIterations
        } else {
            $gateResult = Invoke-Gate -GateName $gate.Name -Script $gate.Script -Arguments $gate.Args
        }
        
        $cycleGateResults += $gateResult
        
        # Display result
        $statusColor = if ($gateResult.ExitCode -eq 0) { "Green" } else { "Red" }
        Write-Host "  Status: $($gateResult.Status)" -ForegroundColor $statusColor
        Write-Host "  Duration: $([math]::Round($gateResult.Duration, 2))s"
        if ($gateResult.PassRate -ne $null) {
            Write-Host "  Pass-Rate: $($gateResult.PassRate)%"
        }
        
        if ($gateResult.ExitCode -ne 0) {
            $cyclePassed = $false
            $totalFailures++
        }
    }
    
    $cycleEnd = Get-Date
    $cycleDuration = ($cycleEnd - $cycleStart).TotalSeconds
    
    # Record cycle result
    $cycleResult = @{
        Cycle = $cycle
        Timestamp = $cycleStart.ToString("s")
        Duration = $cycleDuration
        Passed = $cyclePassed
        Gates = $cycleGateResults
    }
    $cycleResults += $cycleResult
    
    # Cycle summary
    $cycleStatus = if ($cyclePassed) { "PASS" } else { "FAIL" }
    $cycleColor = if ($cyclePassed) { "Green" } else { "Red" }
    Write-Host ""
    Write-Host "Cycle $cycle Result: $cycleStatus" -ForegroundColor $cycleColor
    Write-Host "Cycle Duration: $([math]::Round($cycleDuration, 2))s"
    
    if (-not $cyclePassed) {
        $cycleFailures++
        if (-not $ContinueOnFailure) {
            Write-Host ""
            Write-Host "Stopping burn-in due to failure (use -ContinueOnFailure to continue)" -ForegroundColor Red
            break
        }
    }
    
    # Brief pause between cycles to allow system cleanup
    if ($cycle -lt $Cycles) {
        Start-Sleep -Milliseconds 500
    }
}

$overallEnd = Get-Date
$overallDuration = ($overallEnd - $overallStart).TotalSeconds

# Calculate statistics
$successfulCycles = $Cycles - $cycleFailures
$cyclePassRate = if ($Cycles -gt 0) { [math]::Round(($successfulCycles / $Cycles) * 100, 1) } else { 0 }

# Aggregate gate statistics
$gateStats = @{}
foreach ($cycle in $cycleResults) {
    foreach ($gate in $cycle.Gates) {
        if (-not $gateStats.ContainsKey($gate.Name)) {
            $gateStats[$gate.Name] = @{
                Runs = 0
                Passes = 0
                Failures = 0
                TotalDuration = 0
                TotalPassed = 0
                TotalFailed = 0
                TotalSkipped = 0
                PassRates = @()
            }
        }
        $stats = $gateStats[$gate.Name]
        $stats.Runs++
        $stats.TotalDuration += $gate.Duration
        if ($gate.ExitCode -eq 0) {
            $stats.Passes++
        } else {
            $stats.Failures++
        }
        if ($gate.Passed -ne $null) { $stats.TotalPassed += $gate.Passed }
        if ($gate.Failed -ne $null) { $stats.TotalFailed += $gate.Failed }
        if ($gate.Skipped -ne $null) { $stats.TotalSkipped += $gate.Skipped }
        if ($gate.PassRate -ne $null) { $stats.PassRates += $gate.PassRate }
    }
}

# Display final summary
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "       RC Burn-in Final Report         " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Completed: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host "Total Duration: $([math]::Round($overallDuration, 2))s"
Write-Host "Cycles Run: $($cycleResults.Count)/$Cycles"
Write-Host "Successful Cycles: $successfulCycles"
Write-Host "Failed Cycles: $cycleFailures"
Write-Host "Cycle Pass-Rate: $cyclePassRate%"
Write-Host ""

Write-Host "Gate Statistics:" -ForegroundColor Yellow
foreach ($gateName in $gateStats.Keys) {
    $stats = $gateStats[$gateName]
    $avgDuration = if ($stats.Runs -gt 0) { [math]::Round($stats.TotalDuration / $stats.Runs, 2) } else { 0 }
    $gatePassRate = if ($stats.Runs -gt 0) { [math]::Round(($stats.Passes / $stats.Runs) * 100, 1) } else { 0 }
    $avgPassRate = if ($stats.PassRates.Count -gt 0) { [math]::Round(($stats.PassRates | Measure-Object -Average).Average, 1) } else { "N/A" }
    
    $statusColor = if ($stats.Failures -eq 0) { "Green" } else { "Yellow" }
    Write-Host "  $gateName" -ForegroundColor $statusColor
    Write-Host "    Runs: $($stats.Runs) | Pass: $($stats.Passes) | Fail: $($stats.Failures)"
    Write-Host "    Gate Pass-Rate: $gatePassRate%"
    Write-Host "    Avg Duration: ${avgDuration}s"
    if ($avgPassRate -ne "N/A") {
        Write-Host "    Avg Test Pass-Rate: $avgPassRate%"
    }
}

# Build summary object
$summary = @{
    metadata = @{
        generated_at = (Get-Date).ToString("s")
        schema = "rc_burn_in_v1"
        mode = $Mode
        cycles_requested = $Cycles
        cycles_run = $cycleResults.Count
        duration_days_simulated = $DurationDays
    }
    summary = @{
        total_duration_seconds = [math]::Round($overallDuration, 2)
        successful_cycles = $successfulCycles
        failed_cycles = $cycleFailures
        cycle_pass_rate = $cyclePassRate
        overall_status = if ($cycleFailures -eq 0) { "PASS" } else { "FAIL" }
    }
    gate_statistics = @{}
    cycles = @($cycleResults | ForEach-Object {
        @{
            cycle = $_.Cycle
            timestamp = $_.Timestamp
            duration_seconds = [math]::Round($_.Duration, 2)
            passed = $_.Passed
            gates = @($_.Gates | ForEach-Object {
                @{
                    name = $_.Name
                    status = $_.Status
                    exit_code = $_.ExitCode
                    duration_seconds = [math]::Round($_.Duration, 2)
                    pass_rate = $_.PassRate
                    passed = $_.Passed
                    failed = $_.Failed
                    skipped = $_.Skipped
                }
            })
        }
    })
}

# Add gate statistics to summary
foreach ($gateName in $gateStats.Keys) {
    $stats = $gateStats[$gateName]
    $summary.gate_statistics[$gateName] = @{
        runs = $stats.Runs
        passes = $stats.Passes
        failures = $stats.Failures
        avg_duration_seconds = if ($stats.Runs -gt 0) { [math]::Round($stats.TotalDuration / $stats.Runs, 2) } else { 0 }
        total_passed = $stats.TotalPassed
        total_failed = $stats.TotalFailed
        total_skipped = $stats.TotalSkipped
        avg_pass_rate = if ($stats.PassRates.Count -gt 0) { [math]::Round(($stats.PassRates | Measure-Object -Average).Average, 1) } else { $null }
    }
}

# Save JSON summary
$jsonPath = Join-Path $ReportDir "burn_in_summary_$(Get-Date -Format 'yyyyMMdd_HHmmss').json"
$summary | ConvertTo-Json -Depth 10 | Out-File -FilePath $jsonPath -Encoding UTF8
Write-Host ""
Write-Host "JSON summary saved: $jsonPath"

if ($JsonOut) {
    $summary | ConvertTo-Json -Depth 10 | Out-File -FilePath $JsonOut -Encoding UTF8
    Write-Host "JSON output: $JsonOut"
}

# Generate markdown report
if ($GenerateReport) {
    Write-Host ""
    Write-Host "Generating markdown report..." -ForegroundColor Yellow
    
    $reportPath = Join-Path $ReportDir "RC_BURN_IN_REPORT.md"
    
    $reportContent = @"
# RC Burn-in Report

**Generated:** $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
**Mode:** $Mode
**Simulated Duration:** $DurationDays days

## Summary

| Metric | Value |
|--------|-------|
| Cycles Requested | $Cycles |
| Cycles Run | $($cycleResults.Count) |
| Successful Cycles | $successfulCycles |
| Failed Cycles | $cycleFailures |
| Cycle Pass-Rate | $cyclePassRate% |
| Total Duration | $([math]::Round($overallDuration, 2))s |
| Overall Status | **$(if ($cycleFailures -eq 0) { 'PASS' } else { 'FAIL' })** |

## Gate Statistics

| Gate | Runs | Pass | Fail | Pass-Rate | Avg Duration |
|------|------|------|------|-----------|--------------|
"@

    foreach ($gateName in $gateStats.Keys) {
        $stats = $gateStats[$gateName]
        $avgDuration = if ($stats.Runs -gt 0) { [math]::Round($stats.TotalDuration / $stats.Runs, 2) } else { 0 }
        $gatePassRate = if ($stats.Runs -gt 0) { [math]::Round(($stats.Passes / $stats.Runs) * 100, 1) } else { 0 }
        $reportContent += "`n| $gateName | $($stats.Runs) | $($stats.Passes) | $($stats.Failures) | $gatePassRate% | ${avgDuration}s |"
    }

    $reportContent += @"

## Cycle Details

"@

    foreach ($cycle in $cycleResults) {
        $cycleStatus = if ($cycle.Passed) { "✅ PASS" } else { "❌ FAIL" }
        $reportContent += @"
### Cycle $($cycle.Cycle) - $cycleStatus

- **Timestamp:** $($cycle.Timestamp)
- **Duration:** $([math]::Round($cycle.Duration, 2))s

| Gate | Status | Duration | Pass-Rate |
|------|--------|----------|-----------|
"@
        foreach ($gate in $cycle.Gates) {
            $gateStatus = if ($gate.ExitCode -eq 0) { "✅" } else { "❌" }
            $passRateStr = if ($gate.PassRate -ne $null) { "$($gate.PassRate)%" } else { "N/A" }
            $reportContent += "`n| $($gate.Name) | $gateStatus $($gate.Status) | $([math]::Round($gate.Duration, 2))s | $passRateStr |"
        }
        $reportContent += "`n`n"
    }

    $reportContent += @"
## Stability Assessment

"@

    if ($cycleFailures -eq 0) {
        $reportContent += @"
✅ **EXCELLENT** - All cycles passed without failures. The RC is stable and ready for release.
"@
    } elseif ($cyclePassRate -ge 90) {
        $reportContent += @"
⚠️ **GOOD** - $cyclePassRate% of cycles passed. Minor issues detected, review failures before release.
"@
    } elseif ($cyclePassRate -ge 75) {
        $reportContent += @"
⚠️ **FAIR** - $cyclePassRate% of cycles passed. Several issues detected, investigation recommended.
"@
    } else {
        $reportContent += @"
❌ **POOR** - Only $cyclePassRate% of cycles passed. Significant stability issues, RC not ready for release.
"@
    }

    $reportContent += "`n`n---`n*Report generated by rc_burn_in.ps1*"

    $reportContent | Out-File -FilePath $reportPath -Encoding UTF8
    Write-Host "Markdown report saved: $reportPath" -ForegroundColor Green
}

# Final status
Write-Host ""
$overallStatus = if ($cycleFailures -eq 0) { "BURN-IN PASSED" } else { "BURN-IN FAILED" }
$overallColor = if ($cycleFailures -eq 0) { "Green" } else { "Red" }
Write-Host "Overall: $overallStatus" -ForegroundColor $overallColor
Write-Host ""

$exitCode = if ($cycleFailures -eq 0) { 0 } else { 1 }
Write-Host "Exit Code: $exitCode"

exit $exitCode
