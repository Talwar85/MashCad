"""Simple performance/stress test runner"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import test module directly
import importlib.util
spec = importlib.util.spec_from_file_location("test_performance_stress", os.path.join(os.path.dirname(__file__), "test_performance_stress.py"))
test_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(test_module)

success = test_module.run_all_performance_stress_tests()
sys.exit(0 if success else 1)
