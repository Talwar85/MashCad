#!/usr/bin/env python
"""
Pylint Import Error Checker for MashCAD V1 Roadmap

This script performs directory-level import checking using Pylint.
It focuses exclusively on import-error detection to catch missing
or unresolved imports before they cause runtime failures.

Usage:
    python scripts/check_imports_pylint.py [--directories DIR1 DIR2 ...]

Exit codes:
    0 - No import errors found
    1 - Import errors detected
    2 - Execution error (e.g., Pylint not installed)
"""

import argparse
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple


# Default directories to check
DEFAULT_DIRECTORIES = ["modeling", "gui", "sketcher", "config"]

# Pylint flags for import-only checking
PYLINT_IMPORT_FLAGS = [
    "--disable=all",
    "--enable=import-error",
    "--reports=no",
    "--score=no",
]


def find_python_files(directory: Path) -> List[Path]:
    """Find all Python files in a directory recursively."""
    return list(directory.rglob("*.py"))


def run_pylint_import_check(target: str) -> Tuple[int, str, str]:
    """
    Run Pylint import check on a target (file or directory).
    
    Returns:
        Tuple of (return_code, stdout, stderr)
    """
    # Use python -m pylint to avoid PATH issues
    cmd = ["python", "-m", "pylint"] + PYLINT_IMPORT_FLAGS + [target]
    
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=Path(__file__).parent.parent,
        )
        return result.returncode, result.stdout.decode("utf-8", errors="replace"), result.stderr.decode("utf-8", errors="replace")
    except FileNotFoundError:
        return 2, "", "Pylint not found. Install with: pip install pylint"


def check_directory(directory_name: str) -> Tuple[List[str], str]:
    """
    Check a directory for import errors.
    
    Returns:
        Tuple of (list of import error messages, raw output for debugging)
    """
    project_root = Path(__file__).parent.parent
    target_path = project_root / directory_name
    
    if not target_path.exists():
        return [f"Directory not found: {directory_name}"], ""
    
    errors = []
    returncode, stdout, stderr = run_pylint_import_check(str(target_path))
    
    # Pylint exit codes:
    # 0 = no issues
    # 1 = fatal message issued
    # 2 = error message issued  
    # 4 = warning message issued
    # 8 = refactor message issued
    # 16 = convention message issued
    # Can be combined (e.g., 3 = fatal + error)
    
    # Check for execution failure (no output at all)
    if returncode == 2 and not stdout.strip() and not stderr.strip():
        return [f"Execution error for {directory_name}: Unknown error"], ""
    
    if returncode == 2 and stderr.strip() and "error" in stderr.lower():
        return [f"Execution error for {directory_name}: {stderr}"], stderr
    
    # Parse output for import errors (E0401)
    if stdout.strip():
        for line in stdout.split("\n"):
            # Look for E0401 (import-error) specifically
            if "E0401" in line or "import-error" in line.lower():
                errors.append(line.strip())
    
    return errors, stdout


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Check Python imports using Pylint"
    )
    parser.add_argument(
        "--directories",
        nargs="+",
        default=DEFAULT_DIRECTORIES,
        help=f"Directories to check (default: {' '.join(DEFAULT_DIRECTORIES)})",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show verbose output",
    )
    
    args = parser.parse_args()
    
    all_errors = []
    
    print("=" * 60)
    print("Pylint Import Error Check")
    print("=" * 60)
    print(f"Checking directories: {', '.join(args.directories)}")
    print()
    
    for directory in args.directories:
        print(f"Checking {directory}...", end=" ")
        errors, raw_output = check_directory(directory)
        
        if not errors:
            print("OK")
        else:
            print(f"FOUND {len(errors)} ERROR(S)")
            all_errors.extend([(directory, err) for err in errors])
            
            if args.verbose:
                for err in errors:
                    print(f"  [{directory}] {err}")
                if raw_output:
                    print(f"  Raw output preview: {raw_output[:200]}...")
    
    print()
    print("=" * 60)
    
    if all_errors:
        print(f"RESULT: {len(all_errors)} import error(s) found")
        print()
        print("Import errors:")
        for directory, error in all_errors:
            print(f"  [{directory}] {error}")
        print()
        print("Please fix the import errors above before committing.")
        return 1
    else:
        print("RESULT: All import checks passed!")
        return 0


if __name__ == "__main__":
    sys.exit(main())
