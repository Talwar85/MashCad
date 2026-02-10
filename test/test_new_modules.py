"""Test new modules - Test Runner and Design Library"""
import sys
sys.path.insert(0, 'c:/LiteCad')

# Test imports
from sketching import TestRunner, DesignLibrary, create_design_library

print('=== Test Runner ===')
runner = TestRunner()
result = runner.run_stress_test(count=5, complexity='simple')
print(f'Stress Test: {result.success_rate:.1%} Success')
print(f'Avg Duration: {result.avg_duration_ms:.2f}ms')
print(f'Memory: {result.memory_mb:.2f}MB')

print()
print('=== Design Library ===')
library = create_design_library(seed=42)
print(f'Patterns: {library.list_patterns()}')

for pattern in library.list_patterns():
    solid = library.generate_from_pattern(pattern)
    if solid:
        face_count = len(list(solid.faces()))
        print(f'  {pattern}: OK ({face_count} faces)')
    else:
        print(f'  {pattern}: FAILED')

print()
print('ALL TESTS COMPLETE')
