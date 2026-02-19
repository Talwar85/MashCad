#!/usr/bin/env python
"""
MashCAD Visual Acceptance Runner (W35)

Runs visual acceptance tests, collects results, and produces a JSON report
plus a colorized console summary.

Usage:
    conda run -n cad_env python scripts/run_visual_acceptance.py
"""

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


# ANSI color codes (Windows 10+ supports these via VT100)
GREEN = "\033[92m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"
CYAN = "\033[96m"


TEST_FILE = "test/harness/test_visual_acceptance_w35.py"
OUTPUT_DIR = Path("test_output")
REPORT_PATH = OUTPUT_DIR / "visual_acceptance_report.json"


def enable_windows_ansi():
    """Enable ANSI escape codes on Windows 10."""
    if sys.platform == "win32":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_ulong()
        kernel32.GetConsoleMode(handle, ctypes.byref(mode))
        kernel32.SetConsoleMode(handle, mode.value | 0x0004)


def classify_triage_tag(test_name: str) -> str:
    """Map test name patterns to triage tags."""
    lower = test_name.lower()
    if "constraint" in lower or "solve" in lower:
        return "solver"
    if "roundtrip" in lower or "persist" in lower:
        return "persistence"
    if "create" in lower:
        return "interaction"
    return "general"


def parse_test_identity(nodeid: str):
    """
    Parse a pytest nodeid into shape and checkpoint.

    Example:
        TestLineAcceptance::test_line_create -> ("Line", "create")
        TestCircleAcceptance::test_circle_radius_constraint -> ("Circle", "radius_constraint")
    """
    # Extract class and method from nodeid
    # nodeid looks like: test/harness/test_visual_acceptance_w35.py::TestLineAcceptance::test_line_create
    parts = nodeid.split("::")
    class_name = parts[-2] if len(parts) >= 2 else ""
    method_name = parts[-1] if len(parts) >= 1 else nodeid

    # Extract shape from class name: TestLineAcceptance -> Line
    shape_match = re.match(r"Test(\w+?)Acceptance", class_name)
    shape = shape_match.group(1) if shape_match else class_name

    # Extract checkpoint from method name: test_line_create -> create
    # Remove the "test_" prefix and the shape prefix
    checkpoint = method_name
    if checkpoint.startswith("test_"):
        checkpoint = checkpoint[5:]
    # Remove shape prefix (case-insensitive)
    shape_lower = shape.lower()
    if checkpoint.lower().startswith(shape_lower + "_"):
        checkpoint = checkpoint[len(shape_lower) + 1:]

    return shape, checkpoint


def run_pytest():
    """Run pytest on the visual acceptance test file and return output."""
    cmd = [
        sys.executable, "-m", "pytest",
        TEST_FILE,
        "-v",
        "--tb=short",
        "-q",
    ]

    start = time.monotonic()
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=os.getcwd(),
    )
    elapsed = time.monotonic() - start

    return result.stdout, result.stderr, result.returncode, elapsed


def parse_results(stdout: str):
    """
    Parse pytest -v output to extract per-test results.

    Lines look like:
        test/harness/test_visual_acceptance_w35.py::TestLineAcceptance::test_line_create PASSED
        test/harness/test_visual_acceptance_w35.py::TestCircleAcceptance::test_circle_create FAILED
    """
    results = []
    # Match lines with PASSED/FAILED and optional duration
    pattern = re.compile(
        r"^(.*?::.*?::.*?)\s+(PASSED|FAILED|ERROR|SKIPPED)"
        r"(?:\s+\[\s*\d+%\])?",
        re.MULTILINE,
    )

    for match in pattern.finditer(stdout):
        nodeid = match.group(1).strip()
        outcome = match.group(2).strip()

        shape, checkpoint = parse_test_identity(nodeid)
        triage_tag = classify_triage_tag(checkpoint)
        passed = outcome == "PASSED"

        # Try to extract duration from surrounding lines (best effort)
        duration_ms = 0.0

        error_msg = None
        if not passed:
            # Try to find a short error from the FAILURES section
            fail_pattern = re.compile(
                re.escape(nodeid) + r".*?\n(.*?)(?=\n\S|\Z)",
                re.DOTALL,
            )
            fail_match = fail_pattern.search(stdout)
            if fail_match:
                error_msg = fail_match.group(1).strip()[:200]

        results.append({
            "shape": shape,
            "checkpoint": checkpoint,
            "triage_tag": triage_tag,
            "passed": passed,
            "duration_ms": duration_ms,
            "error": error_msg,
        })

    return results


def build_summary_by_shape(results):
    """Aggregate results by shape."""
    summary = {}
    for r in results:
        shape = r["shape"]
        if shape not in summary:
            summary[shape] = {"passed": 0, "failed": 0, "total": 0}
        summary[shape]["total"] += 1
        if r["passed"]:
            summary[shape]["passed"] += 1
        else:
            summary[shape]["failed"] += 1
    return summary


def write_report(results, summary_by_shape):
    """Write JSON report to disk."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    passed = sum(1 for r in results if r["passed"])
    failed = sum(1 for r in results if not r["passed"])

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_tests": len(results),
        "passed": passed,
        "failed": failed,
        "results": results,
        "summary_by_shape": summary_by_shape,
    }

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    return report


def print_summary(report):
    """Print colorized console summary."""
    bar = "=" * 47
    total = report["total_tests"]
    passed = report["passed"]
    failed = report["failed"]

    print()
    print(f" {BOLD}{bar}{RESET}")
    print(f" {BOLD}{CYAN} MashCAD Visual Acceptance Report (W35){RESET}")
    print(f" {BOLD}{bar}{RESET}")

    summary = report["summary_by_shape"]
    results = report["results"]

    # Group checkpoints by shape in order of appearance
    shape_order = []
    seen = set()
    for r in results:
        if r["shape"] not in seen:
            shape_order.append(r["shape"])
            seen.add(r["shape"])

    for shape in shape_order:
        shape_results = [r for r in results if r["shape"] == shape]
        parts = []
        for r in shape_results:
            if r["passed"]:
                parts.append(f"{GREEN}+ {r['checkpoint']}{RESET}")
            else:
                parts.append(f"{RED}X {r['checkpoint']}{RESET}")
        line = "  ".join(parts)
        print(f"  {shape:<12}{line}")

    print(f" {BOLD}{bar}{RESET}")

    if failed == 0:
        color = GREEN
        label = "PASSED"
    else:
        color = RED
        label = "FAILED"

    print(f"  {BOLD}RESULT: {color}{passed}/{total} {label}{RESET}")
    print(f" {BOLD}{bar}{RESET}")
    print()
    print(f"  Report: {REPORT_PATH}")
    print()


def main():
    enable_windows_ansi()

    print(f"\n  Running visual acceptance tests: {TEST_FILE}")
    print(f"  Python: {sys.executable}\n")

    stdout, stderr, returncode, elapsed = run_pytest()

    results = parse_results(stdout)

    if not results:
        # If no results parsed, report raw output
        print(f"{RED}No test results parsed from pytest output.{RESET}")
        print("--- stdout ---")
        print(stdout)
        if stderr:
            print("--- stderr ---")
            print(stderr)
        sys.exit(1)

    summary_by_shape = build_summary_by_shape(results)
    report = write_report(results, summary_by_shape)
    print_summary(report)

    sys.exit(0 if report["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
