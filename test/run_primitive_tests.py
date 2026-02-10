"""Simple primitive feature test runner"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import test module directly
import importlib.util
spec = importlib.util.spec_from_file_location("test_primitive_feature", os.path.join(os.path.dirname(__file__), "test_primitive_feature.py"))
test_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(test_module)

success = test_module.run_all_primitive_feature_tests()
sys.exit(0 if success else 1)
