"""Debug rectangle extrude"""
import sys
sys.path.insert(0, 'c:/LiteCad')

from modeling import Body, Document, ExtrudeFeature, Sketch
from config.feature_flags import set_flag

# Enable debug logging
set_flag("extrude_debug", True)

sketch = Sketch('PushPull Test')
lines = sketch.add_rectangle(0, 0, 50, 50)

print('Lines:', len(lines))
print('sketch.closed_profiles:', len(sketch.closed_profiles))

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
