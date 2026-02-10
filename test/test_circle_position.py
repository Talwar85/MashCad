"""Test Circle Position Fix"""
import sys
sys.path.insert(0, 'c:/LiteCad')

# Logging aktivieren für Debug-Info wie im GUI
from config.feature_flags import set_flag
set_flag("tnp_debug_logging", True)
set_flag("extrude_debug", True)

from modeling import Body, Document, ExtrudeFeature, Sketch

# Test: Circle Position
print("="*60)
print("TEST: Circle Position")
print("="*60)

sketch = Sketch('Position Test')
circle = sketch.add_circle(50, 30, 20)

print('Circle im Sketch:')
print(f'  Circle Center: ({circle.center.x}, {circle.center.y})')
print(f'  Circle Radius: {circle.radius}')

# Native OCP Data prüfen
if hasattr(circle, 'native_ocp_data') and circle.native_ocp_data:
    print(f'  native_ocp_data: {circle.native_ocp_data}')

# Closed profiles prüfen
profiles = sketch.closed_profiles
print(f'  Closed Profiles: {len(profiles)}')
for i, prof in enumerate(profiles):
    print(f'    Profile {i}: {len(prof.elements)} elements')

doc = Document('TestDoc')
body = Body('TestBody', document=doc)
doc.add_body(body)

feature = ExtrudeFeature(sketch=sketch, distance=10.0, operation='New Body')
body.add_feature(feature)

solid = body._build123d_solid
if solid is None:
    print('[FAIL] Solid ist None')
else:
    center = solid.center()
    bbox = solid.bounding_box()
    print(f'\nSolid nach Extrusion:')
    print(f'  Center: X={center.X:.2f}, Y={center.Y:.2f}, Z={center.Z:.2f}')
    print(f'  BoundingBox: X=[{bbox.min.X:.1f}, {bbox.max.X:.1f}], Y=[{bbox.min.Y:.1f}, {bbox.max.Y:.1f}]')

    x_ok = abs(center.X - 50) < 2.0
    y_ok = abs(center.Y - 30) < 2.0

    if x_ok and y_ok:
        print(f'\n[OK] Position korrekt!')
    else:
        print(f'\n[FAIL] Position falsch! Erwartet (50, 30), got ({center.X:.2f}, {center.Y:.2f})')
