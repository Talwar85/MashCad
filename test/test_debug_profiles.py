"""Debug closed profiles"""
import sys
sys.path.insert(0, 'c:/LiteCad')

from modeling import Body, Document, ExtrudeFeature, Sketch

sketch = Sketch('PushPull Test')
lines = sketch.add_rectangle(0, 0, 50, 50)

print('Lines:', len(lines))
print('sketch.closed_profiles:', len(sketch.closed_profiles))

doc = Document('TestDoc')
body = Body('TestBody', document=doc)
doc.add_body(body)

feature = ExtrudeFeature(sketch=sketch, distance=20.0, operation='New Body')

# Debug: was sieht der Legacy-Code?
sketch_profiles = getattr(sketch, 'closed_profiles', [])
print('Legacy sketch_profiles:', len(sketch_profiles))

profile_selector = getattr(feature, 'profile_selector', [])
print('profile_selector:', profile_selector)
