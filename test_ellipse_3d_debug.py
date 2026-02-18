#!/usr/bin/env python
"""Debug für 3D Ellipse Visualisierung"""

import sys
sys.path.insert(0, '.')

try:
    from sketcher.geometry import Ellipse2D, Point2D
    import math
    
    print("=== Testing Ellipse.point_at_angle ===")
    ellipse = Ellipse2D(
        center=Point2D(0, 0),
        radius_x=10.0,
        radius_y=5.0,
        rotation=0.0
    )
    
    # Test point_at_angle
    pt0 = ellipse.point_at_angle(0)
    pt90 = ellipse.point_at_angle(90)
    print(f"point_at_angle(0): ({pt0.x}, {pt0.y})")
    print(f"point_at_angle(90): ({pt90.x}, {pt90.y})")
    
    # Test get_curve_points
    pts = ellipse.get_curve_points(8)
    print(f"\nget_curve_points(8) returns {len(pts)} points")
    for i, (x, y) in enumerate(pts[:5]):
        print(f"  Point {i}: ({x:.2f}, {y:.2f})")
    
    print("\n=== Ellipse Methods Available ===")
    print(f"has point_at_angle: {hasattr(ellipse, 'point_at_angle')}")
    print(f"has get_curve_points: {hasattr(ellipse, 'get_curve_points')}")
    print(f"has native_ocp_data: {hasattr(ellipse, 'native_ocp_data')}")
    
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()

print("\n=== Done ===")
