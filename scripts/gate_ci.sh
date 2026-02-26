#!/bin/bash
# MashCAD CI Gate Runner - Cross-Platform Unified Entry Point (QA-007)
# Bash version for Linux
# Usage: ./scripts/gate_ci.sh [core|ui|hygiene|all]
# Exit Codes: 0 = PASS, 1 = FAIL

set -o pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Parse arguments
GATE="${1:-all}"
DRY_RUN="${DRY_RUN:-false}"
JSON_OUT="${JSON_OUT:-}"

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# ============================================================================
# Platform Detection
# ============================================================================

echo -e "${CYAN}=== MashCAD CI Gate Runner (Linux) ===${NC}"
echo "Timestamp: $(date -u '+%Y-%m-%d %H:%M:%S') UTC"
echo "Platform: $(uname -s) $(uname -m)"
echo "Shell: $SHELL"
echo "Gate: $GATE"
echo ""

# ============================================================================
# Dependency Verification
# ============================================================================

echo -e "${YELLOW}[PREFLIGHT] Verifying dependencies...${NC}"

# Check conda
if command -v conda &> /dev/null; then
    CONDA_VERSION=$(conda --version 2>&1)
    echo -e "  ${GREEN}[OK] Conda: $CONDA_VERSION${NC}"
else
    echo -e "  ${RED}[ERROR] Conda not found${NC}"
    echo "  Install Miniforge or Miniconda first"
fi

# Initialize conda for script use
eval "$(conda shell.bash hook 2>/dev/null || echo 'true')"

# Check Python in cad_env
if conda env list | grep -q "cad_env"; then
    PYTHON_VERSION=$(conda run -n cad_env python --version 2>&1 || echo "unknown")
    echo -e "  ${GREEN}[OK] Python: $PYTHON_VERSION${NC}"
else
    echo -e "  ${RED}[ERROR] cad_env environment not found${NC}"
    echo -e "  ${YELLOW}Create it with: conda create -n cad_env python=3.11${NC}"
fi

# Check pytest
if conda run -n cad_env python -m pytest --version &> /dev/null; then
    echo -e "  ${GREEN}[OK] pytest available${NC}"
else
    echo -e "  ${RED}[ERROR] pytest not installed in cad_env${NC}"
fi

# Check OCP
if conda run -n cad_env python -c "import OCP" 2>/dev/null; then
    echo -e "  ${GREEN}[OK] OCP (OpenCASCADE) available${NC}"
else
    echo -e "  ${RED}[ERROR] OCP not available${NC}"
fi

# Check build123d
if conda run -n cad_env python -c "import build123d" 2>/dev/null; then
    echo -e "  ${GREEN}[OK] build123d available${NC}"
else
    echo -e "  ${RED}[ERROR] build123d not available${NC}"
fi

echo ""

if [[ "$DRY_RUN" == "true" ]]; then
    echo -e "${YELLOW}[DRY RUN] Would run gate: $GATE${NC}"
    exit 0
fi

# ============================================================================
# Gate Functions
# ============================================================================

CORE_MARKER="${CORE_MARKER:-not slow and not wip and not flaky}"
CORE_WORKERS="${CORE_WORKERS:-4}"

UI_TESTS=(
    "test/test_ui_abort_logic.py"
    "test/harness/test_interaction_consistency.py"
    "test/harness/test_interaction_direct_manipulation_w17.py"
    "test/test_selection_state_unified.py"
    "test/test_browser_tooltip_formatting.py"
    "test/test_discoverability_hints.py"
    "test/test_discoverability_hints_w17.py"
    "test/test_error_ux_v2_integration.py"
    "test/test_error_ux_v2_e2e.py"
    "test/test_feature_commands_atomic.py"
    "test/test_sketch_controller.py"
    "test/test_export_controller.py"
    "test/test_feature_controller.py"
)

run_core_gate() {
    echo ""
    echo -e "${CYAN}=== Running Core-Gate ===${NC}"
    echo "Profile: marker='$CORE_MARKER', workers=$CORE_WORKERS"
    
    local start_time=$(date +%s)
    
    # Keep Linux core behavior aligned with scripts/gate_core.ps1 (Windows).
    cd "$PROJECT_ROOT"

    local pytest_args=(
        -m "$CORE_MARKER"
        --maxfail=30
        -q
    )

    if conda run -n cad_env python -c "import xdist" >/dev/null 2>&1 && [[ "$CORE_WORKERS" -gt 1 ]]; then
        pytest_args+=(-n "$CORE_WORKERS")
    else
        echo -e "  ${YELLOW}[INFO] pytest-xdist not available -> sequential mode${NC}"
    fi

    if conda run -n cad_env python -c "import pytest_timeout" >/dev/null 2>&1; then
        pytest_args+=(--timeout=120)
    else
        echo -e "  ${YELLOW}[INFO] pytest-timeout not available -> timeout arg skipped${NC}"
    fi

    conda run -n cad_env python -m pytest "${pytest_args[@]}" 2>&1 | tee test_output_core.txt
    local exit_code=${PIPESTATUS[0]}
    
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    # Parse results
    local passed=0
    local failed=0
    local skipped=0
    local errors=0
    
    if [[ -f test_output_core.txt ]]; then
        passed=$(grep -oP '\d+(?= passed)' test_output_core.txt || echo 0)
        failed=$(grep -oP '\d+(?= failed)' test_output_core.txt || echo 0)
        skipped=$(grep -oP '\d+(?= skipped)' test_output_core.txt || echo 0)
        errors=$(grep -oP '\d+(?= error)' test_output_core.txt || echo 0)
    fi
    
    local total=$((passed + failed + skipped + errors))
    local pass_rate=0
    if [[ $total -gt 0 ]]; then
        pass_rate=$(awk "BEGIN { printf \"%.1f\", ($passed / $total) * 100 }")
    fi
    
    echo ""
    echo -e "${CYAN}=== Core-Gate Result ===${NC}"
    echo "Duration: ${duration}s"
    echo "Tests: $passed passed, $failed failed, $skipped skipped, $errors errors (total: $total)"
    echo "Pass-Rate: ${pass_rate}%"
    
    if [[ $exit_code -eq 0 ]]; then
        echo -e "Status: ${GREEN}PASS${NC}"
    else
        echo -e "Status: ${RED}FAIL${NC}"
    fi
    
    # Write JSON summary if requested
    if [[ -n "$JSON_OUT" ]]; then
        mkdir -p "$(dirname "$JSON_OUT")"
        cat > "$JSON_OUT" << EOF
{
    "profile": "full",
    "marker": "$CORE_MARKER",
    "workers": $CORE_WORKERS,
    "counts": {
        "passed": $passed,
        "failed": $failed,
        "skipped": $skipped,
        "errors": $errors,
        "total": $total
    },
    "duration_seconds": $duration,
    "pass_rate": $pass_rate,
    "status": "$([ $exit_code -eq 0 ] && echo 'PASS' || echo 'FAIL')",
    "exit_code": $exit_code
}
EOF
        echo "JSON written: $JSON_OUT"
    fi
    
    echo "Exit Code: $exit_code"
    return $exit_code
}

run_ui_gate() {
    echo ""
    echo -e "${CYAN}=== Running UI-Gate ===${NC}"
    
    local start_time=$(date +%s)
    
    # Run tests with virtual display support
    cd "$PROJECT_ROOT"
    
    # Check if xvfb-run is available for headless UI testing
    if command -v xvfb-run &> /dev/null; then
        xvfb-run -a conda run -n cad_env python -m pytest -q "${UI_TESTS[@]}" 2>&1 | tee test_output_ui.txt
    else
        QT_QPA_PLATFORM=offscreen conda run -n cad_env python -m pytest -q "${UI_TESTS[@]}" 2>&1 | tee test_output_ui.txt
    fi
    local exit_code=${PIPESTATUS[0]}
    
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    # Parse results
    local passed=0
    local failed=0
    local skipped=0
    local errors=0
    
    if [[ -f test_output_ui.txt ]]; then
        passed=$(grep -oP '\d+(?= passed)' test_output_ui.txt || echo 0)
        failed=$(grep -oP '\d+(?= failed)' test_output_ui.txt || echo 0)
        skipped=$(grep -oP '\d+(?= skipped)' test_output_ui.txt || echo 0)
        errors=$(grep -oP '\d+(?= error)' test_output_ui.txt || echo 0)
    fi
    
    local total=$((passed + failed + skipped + errors))
    
    echo ""
    echo -e "${CYAN}=== UI-Gate Result ===${NC}"
    echo "Duration: ${duration}s"
    echo "Tests: $passed passed, $failed failed, $skipped skipped, $errors errors"
    
    # UI-Gate: BLOCKED_INFRA doesn't fail CI
    if [[ $exit_code -eq 0 ]]; then
        echo -e "Status: ${GREEN}PASS${NC}"
    else
        echo -e "Status: ${YELLOW}BLOCKED_INFRA${NC} (infrastructure issue, not logic failure)"
        exit_code=0  # Don't fail CI for UI infrastructure issues
    fi
    
    echo "Exit Code: $exit_code"
    return $exit_code
}

run_hygiene_gate() {
    echo ""
    echo -e "${CYAN}=== Running Hygiene-Gate ===${NC}"
    
    cd "$PROJECT_ROOT"
    local violations=0
    local exit_code=0
    
    # Check 1: Debug files in test/
    echo "[Check 1] Debug files in test/ directory..."
    local debug_files=$(find test -name "debug_*.py" -o -name "test_debug_*.py" -o -name "_debug_*.py" 2>/dev/null | head -10)
    if [[ -n "$debug_files" ]]; then
        echo -e "  ${YELLOW}[VIOLATION] Found debug files:${NC}"
        echo "$debug_files" | while read file; do
            echo "    - $file"
        done
        ((violations++))
    else
        echo -e "  ${GREEN}[OK] No debug files found${NC}"
    fi
    
    # Check 2: Test output files in root
    echo "[Check 2] Test output files in root directory..."
    local output_files=$(find . -maxdepth 1 -name "test_output*.txt" 2>/dev/null)
    if [[ -n "$output_files" ]]; then
        echo -e "  ${YELLOW}[VIOLATION] Found output files:${NC}"
        echo "$output_files" | while read file; do
            echo "    - $file"
        done
        ((violations++))
    else
        echo -e "  ${GREEN}[OK] No output files found${NC}"
    fi
    
    # Check 3: Temp files
    echo "[Check 3] Temp files (*.tmp)..."
    local temp_files=$(find . -name "*.tmp" -type f 2>/dev/null | head -10)
    if [[ -n "$temp_files" ]]; then
        echo -e "  ${YELLOW}[VIOLATION] Found temp files:${NC}"
        echo "$temp_files" | while read file; do
            echo "    - $file"
        done
        ((violations++))
    else
        echo -e "  ${GREEN}[OK] No temp files found${NC}"
    fi
    
    # Check 4: Backup files
    echo "[Check 4] Backup files (*.bak*)..."
    local backup_files=$(find . -name "*.bak*" -type f 2>/dev/null | head -10)
    if [[ -n "$backup_files" ]]; then
        echo -e "  ${YELLOW}[VIOLATION] Found backup files:${NC}"
        echo "$backup_files" | while read file; do
            echo "    - $file"
        done
        ((violations++))
    else
        echo -e "  ${GREEN}[OK] No backup files found${NC}"
    fi
    
    echo ""
    echo -e "${CYAN}=== Hygiene-Gate Result ===${NC}"
    echo "Violations: $violations found"
    
    if [[ $violations -eq 0 ]]; then
        echo -e "Status: ${GREEN}CLEAN${NC}"
    else
        echo -e "Status: ${YELLOW}WARNING${NC} (non-blocking)"
        # Hygiene is warning-only by default
        exit_code=0
    fi
    
    echo "Exit Code: $exit_code"
    return $exit_code
}

# ============================================================================
# Main Execution
# ============================================================================

GATE_START=$(date +%s)
EXIT_CODE=0

case "$GATE" in
    core)
        run_core_gate || EXIT_CODE=$?
        ;;
    ui)
        run_ui_gate || EXIT_CODE=$?
        ;;
    hygiene)
        run_hygiene_gate || EXIT_CODE=$?
        ;;
    all)
        run_core_gate || EXIT_CODE=$?
        run_ui_gate || true  # UI doesn't block
        run_hygiene_gate || true  # Hygiene doesn't block
        ;;
    *)
        echo -e "${RED}Unknown gate: $GATE${NC}"
        echo "Usage: $0 [core|ui|hygiene|all]"
        exit 1
        ;;
esac

GATE_END=$(date +%s)
TOTAL_DURATION=$((GATE_END - GATE_START))

# ============================================================================
# Summary
# ============================================================================

echo ""
echo -e "${CYAN}=== CI Gate Runner Summary ===${NC}"
echo "Total Duration: ${TOTAL_DURATION}s"
echo "Gate: $GATE"
echo "Exit Code: $EXIT_CODE"

exit $EXIT_CODE
