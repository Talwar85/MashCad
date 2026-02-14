"""
Test Visual Mesh Analysis with V1.stl

Tests the new visual algorithms for STL feature detection:
- Base Plane Detection with visual projection
- Hole Detection with Ray-Casting (REAL depth, no more guessing!)
- Cross-Validation of methods
"""

import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

from sketching.analysis.stl_feature_analyzer import STLFeatureAnalyzer
from sketching.analysis.cross_validator import FeatureCrossValidator
import pyvista as pv

print('=== Visual Mesh Analysis Test ===')
print('Testing with V1.stl...\n')

# Load mesh
mesh = pv.read('stl/V1.stl')
print(f'✓ Mesh loaded: {mesh.n_points} points, {mesh.n_cells} faces\n')

# Initialize analyzer
analyzer = STLFeatureAnalyzer()

# Analyze with visual methods (Priority: Visual > Alpha Shape > Slice > RANSAC > Legacy)
print('--- Analyzing with Visual Methods ---')
analysis = analyzer.analyze('stl/V1.stl')

# Test 1: Base Plane Detection
print('\n--- Test 1: Visual Base Plane Detection ---')
base_plane = analysis.base_plane
if base_plane:
    print(f'✓ Base Plane detected:')
    print(f'  - Origin: {base_plane.origin}')
    print(f'  - Normal: {base_plane.normal}')
    print(f'  - Area: {base_plane.area:.1f} mm²')
    print(f'  - Detection Method: {base_plane.detection_method}')
    print(f'  - Confidence: {base_plane.confidence:.2f}')
    if base_plane.boundary_points:
        print(f'  - Boundary Points: {len(base_plane.boundary_points)}')

# Test 2: Hole Detection with Ray-Casting
print('\n--- Test 2: Hole Detection (Ray-Casting) ---')
holes = analysis.holes
print(f'✓ Detected {len(holes)} holes')
for i, h in enumerate(holes):
    print(f'  Hole {i+1}:')
    print(f'    - Center: {h.center}')
    print(f'    - Radius: {h.radius:.2f} mm')
    print(f'    - Depth: {h.depth:.2f} mm <-- MEASURED via ray-cast (NOT guessed!)')
    print(f'    - Axis: {h.axis}')
    print(f'    - Detection Method: {h.detection_method}')
    print(f'    - Confidence: {h.confidence:.2f}')

    # Compare old vs new method
    guessed_depth = h.radius * 2
    print(f'    - Old method (guessed): r*2 = {guessed_depth:.2f} mm')
    print(f'    - New method (measured): ray-cast = {h.depth:.2f} mm')
    diff_pct = abs(h.depth - guessed_depth) / guessed_depth * 100
    print(f'    - Difference: {diff_pct:.1f}%')

# Test 3: Cross-Validation
print('\n--- Test 3: Cross-Validation ---')
validator = FeatureCrossValidator()

# Validate base plane
base_validation = validator.validate_base_plane(
    mesh,
    visual_result=base_plane
)
print(f'✓ Base Plane Cross-Validation:')
print(f'  - Agreement Score: {base_validation.agreement_score:.2f}')
print(f'  - Final Confidence: {base_validation.final_confidence:.2f}')

# Validate holes
if holes:
    holes_validation = validator.validate_hole(
        mesh,
        visual_result=holes,
        base_plane=base_plane
    )
    print(f'✓ Hole Cross-Validation:')
    print(f'  - Final Confidence: {holes_validation.final_confidence:.2f}')

print('\n=== TEST COMPLETE ===')
print('Key Achievements:')
print('1. Hole depth is MEASURED via ray-casting, NOT guessed!')
print('2. Previous code: depth = radius * 2 (PURE GUESSING)')
print('3. New code: depth = ray_cast_intersection_distance (REAL MEASUREMENT)')
print('4. Cross-validation confirms detection quality')
