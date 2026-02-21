# MashCAD Test Diagnostic Script
# Runs each test file with timeout to identify stalling/failing tests
#
# Usage:
#   ./run_test_diagnostics.ps1 [-TimeoutSeconds 60] [-OutputFile "results.log"] [-Quick]
#
# Parameters:
#   -TimeoutSeconds : Maximum time per test file (default: 60)
#   -OutputFile     : Output log file name (default: test_diagnostic_results.log)
#   -Quick          : Use shorter timeout (30s) for quick scan

param(
    [int]$TimeoutSeconds = 60,
    [string]$OutputFile = "test_diagnostic_results.log",
    [switch]$Quick
)

if ($Quick) {
    $TimeoutSeconds = 30
}

$ErrorActionPreference = "Continue"

# Initialize results file
$timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
"=== MashCAD Test Diagnostic Results ===" | Out-File -FilePath $OutputFile -Force
"Run started: $timestamp" | Out-File -FilePath $OutputFile -Append
"Timeout per test: $TimeoutSeconds seconds" | Out-File -FilePath $OutputFile -Append
"Mode: $(if ($Quick) { 'Quick' } else { 'Full' })" | Out-File -FilePath $OutputFile -Append
"" | Out-File -FilePath $OutputFile -Append

# Get all test files (excluding _archived)
$testFiles = Get-ChildItem -Path "test" -Filter "test_*.py" | 
    Where-Object { $_.FullName -notlike "*\_archived\*" } | 
    Sort-Object Name

$results = @{
    Passed = @()
    Failed = @()
    Timeout = @()
    Error = @()
}

$totalTests = $testFiles.Count
$currentTest = 0

Write-Host "Found $totalTests test files to analyze" -ForegroundColor Cyan
Write-Host "Timeout: $TimeoutSeconds seconds per file" -ForegroundColor Cyan
Write-Host "Output: $OutputFile" -ForegroundColor Cyan
Write-Host ""

foreach ($file in $testFiles) {
    $currentTest++
    $testName = $file.Name
    $progress = [math]::Round(($currentTest / $totalTests) * 100, 1)
    
    Write-Host "[$currentTest/$totalTests] Testing: $testName ... " -NoNewline
    
    "[$currentTest/$totalTests] $testName" | Out-File -FilePath $OutputFile -Append
    
    $testPath = "test/$testName"
    $startTime = Get-Date
    
    # Run test in background job
    $job = Start-Job -ScriptBlock {
        param($workDir, $testFile)
        Set-Location $workDir
        # Try conda first, fallback to plain pytest
        if (Get-Command conda -ErrorAction SilentlyContinue) {
            conda run -n cad_env pytest $testFile -v --tb=short 2>&1
        } else {
            python -m pytest $testFile -v --tb=short 2>&1
        }
    } -ArgumentList $PWD.Path, $testPath
    
    # Wait with timeout
    $completed = Wait-Job -Job $job -Timeout $TimeoutSeconds
    $elapsed = ((Get-Date) - $startTime).TotalSeconds
    
    if ($completed) {
        $output = Receive-Job -Job $job | Out-String
        Remove-Job -Job $job -Force
        
        # Parse results
        if ($output -match "(\d+)\s+passed" -and $output -notmatch "failed") {
            $passCount = $matches[1]
            Write-Host "PASSED ($passCount tests, $([math]::Round($elapsed, 1))s)" -ForegroundColor Green
            "  Result: PASSED ($passCount tests, $([math]::Round($elapsed, 1))s)" | Out-File -FilePath $OutputFile -Append
            $results.Passed += $testName
        }
        elseif ($output -match "(\d+)\s+passed.*(\d+)\s+failed") {
            $passCount = $matches[1]
            $failCount = $matches[2]
            Write-Host "FAILED ($passCount passed, $failCount failed, $([math]::Round($elapsed, 1))s)" -ForegroundColor Red
            "  Result: FAILED ($passCount passed, $failCount failed, $([math]::Round($elapsed, 1))s)" | Out-File -FilePath $OutputFile -Append
            $results.Failed += $testName
        }
        elseif ($output -match "no tests ran" -or $output -match "collected 0 items") {
            Write-Host "NO TESTS" -ForegroundColor Yellow
            "  Result: NO TESTS COLLECTED" | Out-File -FilePath $OutputFile -Append
            $results.Error += $testName
        }
        elseif ($output -match "passed") {
            Write-Host "PASSED ($([math]::Round($elapsed, 1))s)" -ForegroundColor Green
            "  Result: PASSED ($([math]::Round($elapsed, 1))s)" | Out-File -FilePath $OutputFile -Append
            $results.Passed += $testName
        }
        else {
            Write-Host "UNKNOWN ($([math]::Round($elapsed, 1))s)" -ForegroundColor Yellow
            "  Result: UNKNOWN ($([math]::Round($elapsed, 1))s)" | Out-File -FilePath $OutputFile -Append
            "  Output: $($output.Substring(0, [Math]::Min(300, $output.Length)))" | Out-File -FilePath $OutputFile -Append
            $results.Error += $testName
        }
    }
    else {
        Write-Host "TIMEOUT (>${TimeoutSeconds}s)" -ForegroundColor Magenta
        "  Result: TIMEOUT (>${TimeoutSeconds}s)" | Out-File -FilePath $OutputFile -Append
        $results.Timeout += $testName
        
        # Kill the job
        Stop-Job -Job $job -ErrorAction SilentlyContinue
        Remove-Job -Job $job -Force -ErrorAction SilentlyContinue
    }
    
    "" | Out-File -FilePath $OutputFile -Append
}

# Summary
Write-Host ""
Write-Host "=== SUMMARY ===" -ForegroundColor Cyan
"" | Out-File -FilePath $OutputFile -Append
"=== SUMMARY ===" | Out-File -FilePath $OutputFile -Append
"Run completed: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Out-File -FilePath $OutputFile -Append
"" | Out-File -FilePath $OutputFile -Append

Write-Host "PASSED: $($results.Passed.Count)" -ForegroundColor Green
"PASSED ($($results.Passed.Count)):" | Out-File -FilePath $OutputFile -Append
$results.Passed | ForEach-Object { "  - $_" | Out-File -FilePath $OutputFile -Append }

Write-Host "FAILED: $($results.Failed.Count)" -ForegroundColor Red
"" | Out-File -FilePath $OutputFile -Append
"FAILED ($($results.Failed.Count)):" | Out-File -FilePath $OutputFile -Append
$results.Failed | ForEach-Object { "  - $_" | Out-File -FilePath $OutputFile -Append }

Write-Host "TIMEOUT: $($results.Timeout.Count)" -ForegroundColor Magenta
"" | Out-File -FilePath $OutputFile -Append
"TIMEOUT ($($results.Timeout.Count)):" | Out-File -FilePath $OutputFile -Append
$results.Timeout | ForEach-Object { "  - $_" | Out-File -FilePath $OutputFile -Append }

Write-Host "ERROR: $($results.Error.Count)" -ForegroundColor Yellow
"" | Out-File -FilePath $OutputFile -Append
"ERROR/UNKNOWN ($($results.Error.Count)):" | Out-File -FilePath $OutputFile -Append
$results.Error | ForEach-Object { "  - $_" | Out-File -FilePath $OutputFile -Append }

Write-Host ""
Write-Host "Results saved to: $OutputFile" -ForegroundColor Cyan

# Return summary for programmatic use
return $results
