"""Test Rectangle Only Sketch"""
import sys
sys.path.insert(0, 'c:/LiteCad')

from modeling import Body, Document, ExtrudeFeature, Sketch

sketch = Sketch('PushPull Test')
lines = sketch.add_rectangle(0, 0, 50, 50)

print('Rectangle:', len(lines), 'lines')
print('Closed profiles:', len(sketch.closed_profiles))

doc = Document('TestDoc')
body = Body('TestBody', document=doc)
doc.add_body(body)

feature = ExtrudeFeature(sketch=sketch, distance=20.0, operation='New Body')
body.add_feature(feature)

solid = body._build123d_solid
if solid is None:
    print('[FAIL] Solid ist None')
else:
    print(f'[OK] Volume: {solid.volume:.2f}')
