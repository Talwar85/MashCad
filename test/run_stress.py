"""Stress-Runner: Setzt CAD_TRUST_ITERATIONS und startet pytest."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["CAD_TRUST_ITERATIONS"] = sys.argv[1] if len(sys.argv) > 1 else "100"
n = os.environ["CAD_TRUST_ITERATIONS"]
print(f"Running stress test with {n} iterations...")

import pytest
sys.exit(pytest.main([
    "test/test_cad_workflow_trust.py",
    "-v", "--tb=short", "-q",
    f"--rootdir={os.path.dirname(os.path.dirname(os.path.abspath(__file__)))}",
]))
