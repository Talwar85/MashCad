"""Test Circle y_dir Nullvektor-Fix"""
import sys
sys.path.insert(0, 'c:/LiteCad')

# Logging aktivieren
from config.feature_flags import set_flag
set_flag('tnp_debug_logging', True)
set_flag('extrude_debug', True)

from modeling import Body, Document, ExtrudeFeature, Sketch

print('='*60)
print('TEST: Circle Position mit y_dir Nullvektor-Fix')
print('='*60)

sketch = Sketch('Test')
circle = sketch.add_circle(50, 30, 20)

# Simuliere den Bug: plane_y_dir auf (0, 0, 0) setzen
sketch.plane_y_dir = (0, 0, 0)
print(f'Sketch plane_y_dir gesetzt auf: {sketch.plane_y_dir}')

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
    print(f'Solid Center: X={center.X:.2f}, Y={center.Y:.2f}, Z={center.Z:.2f}')
    print(f'BoundingBox: X=[{bbox.min.X:.1f}, {bbox.max.X:.1f}], Y=[{bbox.min.Y:.1f}, {bbox.max.Y:.1f}]')

    x_ok = abs(center.X - 50) < 2.0
    y_ok = abs(center.Y - 30) < 2.0

    if x_ok and y_ok:
        print('[OK] Position korrekt!')
    else:
        print(f'[FAIL] Position falsch! Erwartet (50, 30), got ({center.X:.2f}, {center.Y:.2f})')
