#!/usr/bin/env powershell
# Performance-Gate Runner - QA-006
# Usage: .\scripts\gate_performance.ps1
# Exit Codes: 0 = PASS, 1 = FAIL (regressions detected)

param(
    [switch]$UpdateBaselines = $false,
    [switch]$DryRun = $false,
    [string]$JsonOut = "",
    [int]$Iterations = 3
)

$ErrorActionPreference = "Continue"

Write-Host "=== Performance-Gate Started ===" -ForegroundColor Cyan
Write-Host "Timestamp: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host "UpdateBaselines: $UpdateBaselines"
Write-Host "DryRun: $DryRun"
Write-Host "Iterations: $Iterations"
Write-Host ""

# Performance Targets (QA-006)
# These are the expected maximum times for each operation
$PerformanceTargets = @{
    "simple_extrude" = @{ Target = 100; Max = 200 }
    "boolean_union" = @{ Target = 200; Max = 500 }
    "fillet_10_edges" = @{ Target = 150; Max = 300 }
    "stl_export" = @{ Target = 500; Max = 1000 }
    "full_rebuild" = @{ Target = 1000; Max = 2000 }
}

# Regression threshold: 20% slower than target = regression
$RegressionThreshold = 1.20

function Test-PerformanceFeatureFlag {
    <#
    .SYNOPSIS
    Check if performance_regression_gate feature flag is enabled
    #>
    $flagCheckScript = @'
from config.feature_flags import is_enabled
print("ENABLED" if is_enabled("performance_regression_gate") else "DISABLED")
'@
    
    $result = conda run -n cad_env python -c $flagCheckScript 2>&1
    return ($result -match "ENABLED")
}

function Invoke-PerformanceBenchmarks {
    <#
    .SYNOPSIS
    Run the Python performance benchmark module
    #>
    param(
        [int]$Iterations,
        [string]$OutputFile
    )
    
    $benchmarkScript = @"
import json
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from modeling.performance_benchmark import (
    PerformanceBenchmark, 
    BenchmarkReport,
    PERFORMANCE_TARGETS,
    REGRESSION_THRESHOLD
)

def run_gate():
    benchmark = PerformanceBenchmark()
    report = benchmark.run_all_benchmarks(iterations=$Iterations)
    
    # Print summary
    report.print_summary()
    
    # Output JSON if requested
    output = {
        "timestamp": report.timestamp,
        "has_regressions": report.has_regressions,
        "has_failures": report.has_failures,
        "regression_count": len(report.regression_details),
        "regressions": report.regression_details,
        "results": [r.to_dict() for r in report.results],
        "baseline_file": report.baseline_file,
        "exit_code": 1 if report.has_failures else 0
    }
    
    print("")
    print("=== JSON OUTPUT ===")
    print(json.dumps(output, indent=2))
    
    return 1 if report.has_failures else 0

if __name__ == "__main__":
    sys.exit(run_gate())
"@
    
    $scriptFile = "$env:TEMP\run_benchmark_$($PID).py"
    $benchmarkScript | Out-File -FilePath $scriptFile -Encoding UTF8
    
    try {
        $output = conda run -n cad_env python $scriptFile 2>&1
        return $output
    }
    finally {
        if (Test-Path $scriptFile) {
            Remove-Item $scriptFile -Force
        }
    }
}

function Parse-BenchmarkOutput {
    <#
    .SYNOPSIS
    Parse the JSON output from the benchmark script
    #>
    param(
        [string]$Output
    )
    
    # Find JSON section
    $jsonStart = $Output.IndexOf("=== JSON OUTPUT ===")
    if ($jsonStart -ge 0) {
        $jsonContent = $Output.Substring($jsonStart + 19).Trim()
        try {
            return $jsonContent | ConvertFrom-Json
        }
        catch {
            Write-Warning "Failed to parse JSON output: $_"
            return $null
        }
    }
    return $null
}

# Main execution
# ==============

Write-Host "=== Checking Feature Flag ===" -ForegroundColor Yellow
$featureEnabled = Test-PerformanceFeatureFlag

if (-not $featureEnabled) {
    Write-Host "WARNING: performance_regression_gate feature flag is DISABLED" -ForegroundColor Yellow
    Write-Host "         Performance gate will run but results are informational only" -ForegroundColor Yellow
}
else {
    Write-Host "Feature flag: ENABLED" -ForegroundColor Green
}
Write-Host ""

if ($DryRun) {
    Write-Host "=== DRY RUN - Performance Targets ===" -ForegroundColor Cyan
    foreach ($target in $PerformanceTargets.GetEnumerator()) {
        Write-Host ("  {0,-20} Target: {1,4}ms  Max: {2,4}ms" -f $target.Key, $target.Value.Target, $target.Value.Max)
    }
    Write-Host ""
    Write-Host "Regression Threshold: $($RegressionThreshold)x (20% slower)"
    Write-Host ""
    
    if ($JsonOut) {
        $dryResult = @{
            dry_run = $true
            feature_enabled = $featureEnabled
            targets = $PerformanceTargets
            regression_threshold = $RegressionThreshold
            timestamp = (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
        }
        $dryResult | ConvertTo-Json -Depth 3 | Out-File -FilePath $JsonOut -Encoding UTF8
        Write-Host "Dry run results written to: $JsonOut"
    }
    
    Write-Host "=== Performance-Gate DRY RUN Complete ===" -ForegroundColor Cyan
    exit 0
}

Write-Host "=== Running Benchmarks ===" -ForegroundColor Yellow
$benchmarkOutput = Invoke-PerformanceBenchmarks -Iterations $Iterations

# Display raw output for debugging
Write-Host $benchmarkOutput

# Parse results
$results = Parse-BenchmarkOutput -Output $benchmarkOutput

if ($null -eq $results) {
    Write-Host ""
    Write-Host "=== Performance-Gate FAILED ===" -ForegroundColor Red
    Write-Host "Failed to parse benchmark results" -ForegroundColor Red
    exit 1
}

# Write JSON output if requested
if ($JsonOut) {
    $results | ConvertTo-Json -Depth 4 | Out-File -FilePath $JsonOut -Encoding UTF8
    Write-Host ""
    Write-Host "Results written to: $JsonOut" -ForegroundColor Green
}

# Determine exit code
$exitCode = 0

if ($results.has_failures) {
    Write-Host ""
    Write-Host "=== Performance-Gate FAILED ===" -ForegroundColor Red
    Write-Host "One or more operations exceeded maximum acceptable time" -ForegroundColor Red
    $exitCode = 1
}
elseif ($results.has_regressions) {
    Write-Host ""
    Write-Host "=== Performance-Gate WARNING ===" -ForegroundColor Yellow
    Write-Host "Performance regressions detected but within acceptable limits" -ForegroundColor Yellow
    Write-Host "Consider investigating: $($results.regressions -join ', ')" -ForegroundColor Yellow
    # Regressions are warnings, not failures
    $exitCode = 0
}
else {
    Write-Host ""
    Write-Host "=== Performance-Gate PASSED ===" -ForegroundColor Green
    Write-Host "All operations within target performance" -ForegroundColor Green
}

# Update baselines if requested
if ($UpdateBaselines -and $exitCode -eq 0) {
    Write-Host ""
    Write-Host "=== Updating Baselines ===" -ForegroundColor Yellow
    
    $updateScript = @"
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from modeling.performance_benchmark import PerformanceBenchmark

benchmark = PerformanceBenchmark()
report = benchmark.run_all_benchmarks(iterations=$Iterations)
benchmark.update_baselines(report)
print("Baselines updated successfully")
"@
    
    $scriptFile = "$env:TEMP\update_baselines_$($PID).py"
    $updateScript | Out-File -FilePath $scriptFile -Encoding UTF8
    
    try {
        conda run -n cad_env python $scriptFile
        Write-Host "Baselines updated in test/performance_baselines.json" -ForegroundColor Green
    }
    finally {
        if (Test-Path $scriptFile) {
            Remove-Item $scriptFile -Force
        }
    }
}

Write-Host ""
Write-Host "=== Performance-Gate Complete ===" -ForegroundColor Cyan
Write-Host "Exit Code: $exitCode"

exit $exitCode
