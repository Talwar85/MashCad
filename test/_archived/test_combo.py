"""Test Circle + Rectangle Combo"""
import sys
sys.path.insert(0, 'c:/LiteCad')

from modeling import Body, Document, ExtrudeFeature, Sketch

sketch = Sketch('Combo Test')
lines = sketch.add_rectangle(9, 85, 77, 53)
arc = sketch.add_arc(47.5, 138, 23.0, 180, 360)

print('Rectangle elements:', len(lines))
print('Arc native_ocp_data:', hasattr(arc, 'native_ocp_data'))

doc = Document('TestDoc')
body = Body('TestBody', document=doc)
doc.add_body(body)

feature = ExtrudeFeature(sketch=sketch, distance=30.0, operation='New Body')
body.add_feature(feature)

solid = body._build123d_solid
if solid is None:
    print('[FAIL] Solid ist None')
else:
    bbox = solid.bounding_box()
    print(f'Bounding Box: Z=[{bbox.min.Z:.1f}, {bbox.max.Z:.1f}]')

    z_min_ok = abs(bbox.min.Z) < 1.0
    z_max_ok = abs(bbox.max.Z - 30.0) < 1.0

    if z_min_ok and z_max_ok:
        print('[OK] Z-Range korrekt')
    else:
        print(f'[FAIL] Z-Range falsch! Erwartet [0, 30], got [{bbox.min.Z:.1f}, {bbox.max.Z:.1f}]')
