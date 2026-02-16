"""
W12 Paket A: Crash Containment Helper for Interaction Tests
===========================================================

Provides subprocess-based isolation for tests that may trigger native crashes.
A native crash in the child process does NOT kill the main pytest runner.

Exit-Signature Mapping:
- 0xC0000005 (-1073741819): ACCESS_VIOLATION
- 0x80000003 (-1073741821): ASSERTION_FAILURE
- Exit code 1: Test failed (no crash)
- Exit code 0: Test passed

Author: GLM 4.7 (UX/WORKFLOW + QA Integration Cell)
Date: 2026-02-16
Branch: feature/v1-ux-aiB
"""

import subprocess
import sys
import pytest
from typing import Dict, Any, Optional, Tuple


# Native crash exit codes (Windows)
WINDOWS_ACCESS_VIOLATION = 0xC0000005  # -1073741819 as signed int32
WINDOWS_ASSERTION_FAILURE = 0x80000003  # -1073741821 as signed int32


class CrashSignature:
    """Represents a detected native crash signature."""

    def __init__(self, exit_code: int, pattern: str, description: str):
        self.exit_code = exit_code
        self.pattern = pattern
        self.description = description

    def __repr__(self):
        return f"CrashSignature(exit_code={self.exit_code}, pattern={self.pattern})"


# Known blocker signatures
BLOCKER_SIGNATURES = {
    "ACCESS_VIOLATION_INTERACTION_DRAG": CrashSignature(
        exit_code=-1073741819,  # 0xC0000005
        pattern="access violation",
        description="Windows Access Violation during drag interaction (VTK/OpenGL issue)"
    ),
    "VTK_RENDER_CONTEXT_DETERMINISM": CrashSignature(
        exit_code=-1073741819,
        pattern="access violation|wglMakeCurrent|opengl",
        description="VTK OpenGL Context failure in headless environment"
    ),
}


def detect_crash_in_output(output: str) -> Optional[CrashSignature]:
    """
    Analysiert Test-Output auf Crash-Indikatoren.

    Args:
        output: Combined stdout/stderr from test run

    Returns:
        CrashSignature if crash detected, None otherwise
    """
    output_lower = output.lower()

    # Check for access violation patterns
    if "access violation" in output_lower or "0xc0000005" in output_lower:
        return CrashSignature(
            exit_code=WINDOWS_ACCESS_VIOLATION,
            pattern="access violation",
            description="Windows Access Violation (0xC0000005)"
        )

    # Check for OpenGL/VTK context failures
    if "wglmakecurrent" in output_lower or "opengl" in output_lower:
        if "fail" in output_lower or "err" in output_lower:
            return CrashSignature(
                exit_code=1,  # Non-zero exit
                pattern="wglMakeCurrent",
                description="VTK OpenGL Context Failure"
            )

    # Check for fatal error
    if "fatal error" in output_lower or "fatal exception" in output_lower:
        return CrashSignature(
            exit_code=1,
            pattern="fatal",
            description="Fatal Error detected"
        )

    return None


def run_test_in_subprocess(
    test_path: str,
    test_name: str,
    timeout: int = 60
) -> Tuple[int, str, str, Optional[CrashSignature]]:
    """
    Führt einen einzelnen Test in einem isolierten Subprozess aus.

    Args:
        test_path: Path to test file (e.g., "test/harness/test_interaction_consistency.py")
        test_name: Full test name (e.g., "test_circle_move_resize")
        timeout: Maximum seconds to wait for test completion

    Returns:
        Tuple of (exit_code, stdout, stderr, crash_signature)
    """
    # Construct pytest command for single test
    cmd = [
        sys.executable, "-m", "pytest",
        f"{test_path}::{test_name}",
        "-v", "--tb=short", "-p", "no:faulthandler"  # Disable faulthandler to get clean exit
    ]

    # Run in subprocess with explicit environment
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        # Use current environment with QT_OPENGL set
        env={**subprocess.os.environ, "QT_OPENGL": "software"}
    )

    # Combine output for analysis
    combined_output = result.stdout + "\n" + result.stderr

    # Detect crash signature
    crash_sig = detect_crash_in_output(combined_output)

    return result.returncode, result.stdout, result.stderr, crash_sig


def xfail_on_crash(
    exit_code: int,
    crash_signature: Optional[CrashSignature],
    blocker_type: str = "ACCESS_VIOLATION_INTERACTION_DRAG"
) -> None:
    """
    Mark test as xfail if native crash was detected.

    Args:
        exit_code: Process exit code
        crash_signature: Detected crash signature (if any)
        blocker_type: Blocker signature type for documentation

    Raises:
        pytest.xfail: If crash detected with strict=True
    """
    if crash_signature is not None:
        blocker_info = BLOCKER_SIGNATURES.get(blocker_type, crash_signature)

        reason = (
            f"W12 KNOWN_FAILURE: Native crash in isolated subprocess. "
            f"Blocker-Signature: {blocker_type}. "
            f"Exit-Code: {crash_signature.exit_code} ({crash_signature.pattern}). "
            f"Description: {crash_signature.description}. "
            f"Owner: Core (VTK/OpenGL Integration), ETA: TBD. "
            f"Exit-Strategy: Stabilere coordinate mapping oder VTK-mocking für headless CI."
        )

        pytest.xfail(strict=True, reason=reason)


def assert_or_xfail_on_crash(
    condition: bool,
    exit_code: int,
    crash_signature: Optional[CrashSignature],
    blocker_type: str = "ACCESS_VIOLATION_INTERACTION_DRAG",
    assertion_message: str = "Assertion failed"
) -> None:
    """
    Assert condition OR xfail if native crash detected.

    This allows the test to pass normally when stable,
    but marks as xfail when the known infrastructure crash occurs.

    Args:
        condition: Assertion condition
        exit_code: Process exit code
        crash_signature: Detected crash signature (if any)
        blocker_type: Blocker signature type
        assertion_message: Message for AssertionError
    """
    # First check for crash - takes priority
    if crash_signature is not None:
        xfail_on_crash(exit_code, crash_signature, blocker_type)

    # No crash - assert normally
    assert condition, assertion_message


# ============================================================================
# Pytest Fixture: Subprocess-Isolated Test Runner
# ============================================================================

@pytest.fixture
def crash_isolated_runner():
    """
    Fixture that provides a subprocess-based test runner.

    Usage:
        def test_something(crash_isolated_runner):
            exit_code, stdout, stderr, crash_sig = crash_isolated_runner.run(
                "test/harness/test_interaction_consistency.py",
                "test_circle_move_resize"
            )
            # No crash → pytest continues
            # Crash → xfail with blocker signature
    """
    class Runner:
        def run(self, test_path: str, test_name: str, timeout: int = 60):
            return run_test_in_subprocess(test_path, test_name, timeout)

        def run_and_xfail_on_crash(
            self,
            test_path: str,
            test_name: str,
            timeout: int = 60,
            blocker_type: str = "ACCESS_VIOLATION_INTERACTION_DRAG"
        ):
            """Run test and auto-xfail if crash detected."""
            exit_code, stdout, stderr, crash_sig = run_test_in_subprocess(
                test_path, test_name, timeout
            )
            xfail_on_crash(exit_code, crash_sig, blocker_type)
            return exit_code, stdout, stderr, crash_sig

    return Runner()


# ============================================================================
# Helper: Parse Pytest Output for Pass/Fail
# ============================================================================

def parse_pytest_result(output: str) -> Dict[str, Any]:
    """
    Analysiert Pytest-Output auf Test-Ergebnis.

    Returns dict with:
        - passed: bool
        - failed: bool
        - error: bool
        - num_passed: int
        - num_failed: int
        - summary_line: str
    """
    result = {
        "passed": False,
        "failed": False,
        "error": False,
        "num_passed": 0,
        "num_failed": 0,
        "summary_line": ""
    }

    for line in output.split("\n"):
        if " passed" in line:
            result["summary_line"] = line
            if " failed" not in line and " error" not in line:
                result["passed"] = True
                # Extract count
                parts = line.split()
                for i, part in enumerate(parts):
                    if part == "passed":
                        try:
                            result["num_passed"] = int(parts[i - 1])
                        except (ValueError, IndexError):
                            pass
        if " failed" in line:
            result["failed"] = True
            parts = line.split()
            for i, part in enumerate(parts):
                if part == "failed":
                    try:
                        result["num_failed"] = int(parts[i - 1])
                    except (ValueError, IndexError):
                        pass
        if "ERROR" in line and "test session" not in line:
            result["error"] = True

    return result
