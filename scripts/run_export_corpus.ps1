<#
.SYNOPSIS
    MashCAD Export Corpus Runner
    
.DESCRIPTION
    Runs all corpus models through the export pipeline and validates results.
    This script is designed for CI integration and regression testing.
    
.PARAMETER OutputDir
    Directory to store export outputs. Default: test_output/corpus
    
.PARAMETER Format
    Export format to test. Options: stl, step, all. Default: all
    
.PARAMETER Verbose
    Enable verbose output
    
.EXAMPLE
    ./scripts/run_export_corpus.ps1
    Run all corpus models with default settings
    
.EXAMPLE
    ./scripts/run_export_corpus.ps1 -Format stl -Verbose
    Run only STL export tests with verbose output

Author: MashCAD Team
Date: 2026-02-20
Branch: feature/v1-roadmap-execution
#>

param(
    [string]$OutputDir = "test_output/corpus",
    [ValidateSet("stl", "step", "all")]
    [string]$Format = "all",
    [switch]$Verbose = $false,
    [switch]$GenerateGolden = $false
)

# Configuration
$CorpusDir = "test/corpus"
$Categories = @("primitives", "operations", "features", "regression")
$PassCount = 0
$FailCount = 0
$SkipCount = 0
$Results = @()

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    if ($Level -eq "ERROR" -or $Verbose) {
        Write-Host "[$timestamp] [$Level] $Message"
    } elseif ($Level -ne "DEBUG") {
        Write-Host "[$timestamp] [$Level] $Message"
    }
}

function Test-CorpusModel {
    param(
        [string]$Category,
        [string]$ModelName,
        [string]$ModelPath
    )
    
    $result = @{
        Category = $Category
        Model = $ModelName
        Status = "UNKNOWN"
        ExportSTL = "SKIP"
        ExportSTEP = "SKIP"
        Validation = "SKIP"
        Errors = @()
    }
    
    Write-Log "Testing model: $Category/$ModelName" "INFO"
    
    # Run pytest for this specific model
    $testArgs = @(
        "test/test_export_corpus.py",
        "-v" if $Verbose,
        "-k", "$ModelName",
        "--tb=short",
        "--corpus-output=$OutputDir",
        "--corpus-format=$Format"
    ) | Where-Object { $_ }
    
    $pytestOutput = & pytest @testArgs 2>&1
    $pytestExit = $LASTEXITCODE
    
    if ($pytestExit -eq 0) {
        $result.Status = "PASS"
        $result.ExportSTL = "OK"
        $result.ExportSTEP = "OK"
        $result.Validation = "OK"
        $script:PassCount++
        Write-Log "  ✓ PASSED" "INFO"
    } else {
        $result.Status = "FAIL"
        $result.Errors += "pytest exit code: $pytestExit"
        $script:FailCount++
        Write-Log "  ✗ FAILED" "ERROR"
        
        if ($Verbose) {
            Write-Log "  Pytest output:" "DEBUG"
            Write-Log ($pytestOutput | Out-String) "DEBUG"
        }
    }
    
    return $result
}

# Main execution
Write-Log "========================================" "INFO"
Write-Log "MashCAD Export Corpus Runner" "INFO"
Write-Log "========================================" "INFO"
Write-Log "Output Directory: $OutputDir" "INFO"
Write-Log "Export Format: $Format" "INFO"
Write-Log "Generate Golden: $GenerateGolden" "INFO"
Write-Log "" "INFO"

# Create output directory
if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
    Write-Log "Created output directory: $OutputDir" "INFO"
}

# Find and test all corpus models
foreach ($category in $Categories) {
    $categoryPath = Join-Path $CorpusDir $category
    
    if (-not (Test-Path $categoryPath)) {
        Write-Log "Category directory not found: $categoryPath" "WARN"
        continue
    }
    
    Write-Log "" "INFO"
    Write-Log "Category: $category" "INFO"
    Write-Log "----------------------------------------" "INFO"
    
    $modelFiles = Get-ChildItem -Path $categoryPath -Filter "*.py" -File
    
    foreach ($modelFile in $modelFiles) {
        $modelName = $modelFile.BaseName
        $result = Test-CorpusModel -Category $category -ModelName $modelName -ModelPath $modelFile.FullName
        $Results += $result
    }
}

# Summary
Write-Log "" "INFO"
Write-Log "========================================" "INFO"
Write-Log "SUMMARY" "INFO"
Write-Log "========================================" "INFO"
Write-Log "Total:  $($PassCount + $FailCount + $SkipCount)" "INFO"
Write-Log "Passed: $PassCount" "INFO"
Write-Log "Failed: $FailCount" "INFO"
Write-Log "Skipped: $SkipCount" "INFO"
Write-Log "" "INFO"

# Generate report
$reportPath = Join-Path $OutputDir "corpus_report.json"
$report = @{
    timestamp = (Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ")
    format = $Format
    summary = @{
        total = $PassCount + $FailCount + $SkipCount
        passed = $PassCount
        failed = $FailCount
        skipped = $SkipCount
    }
    results = $Results
}

$report | ConvertTo-Json -Depth 10 | Out-File -FilePath $reportPath -Encoding UTF8
Write-Log "Report saved to: $reportPath" "INFO"

# Exit with appropriate code
if ($FailCount -gt 0) {
    Write-Log "Some tests failed. Exit code: 1" "ERROR"
    exit 1
} else {
    Write-Log "All tests passed. Exit code: 0" "INFO"
    exit 0
}
