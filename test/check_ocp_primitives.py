"""Check OCP native primitive face counts"""
import build123d as bd

# OCP nativer Zylinder
cyl = bd.Solid.make_cylinder(10, 20)
print(f'Native Zylinder Faces: {len(list(cyl.faces()))}')
print(f'Face-Types:')
for i, f in enumerate(cyl.faces()):
    geom = f.geom_type  # property, not method
    print(f'  Face {i}: {geom}')

# OCP nativer Cone (Frustum - mit Deckel oben und unten)
cone_frustum = bd.Solid.make_cone(10, 5, 20)  # base_radius, top_radius, height
print(f'\nNative Cone (Frustum, r_top=5) Faces: {len(list(cone_frustum.faces()))}')
for i, f in enumerate(cone_frustum.faces()):
    print(f'  Face {i}: {f.geom_type}')

# OCP nativer Cone (Pointed - spitzer Kegel)
cone_pointed = bd.Solid.make_cone(10, 0, 20)  # base_radius, top_radius=0, height
print(f'\nNative Cone (Pointed, r_top=0) Faces: {len(list(cone_pointed.faces()))}')
for i, f in enumerate(cone_pointed.faces()):
    print(f'  Face {i}: {f.geom_type}')

# OCP nativer Torus
torus = bd.Solid.make_torus(10, 2)
print(f'Native Torus Faces: {len(list(torus.faces()))}')

# OCP nativer Sphere
sphere = bd.Solid.make_sphere(10)
print(f'Native Sphere Faces: {len(list(sphere.faces()))}')

# OCP nativer Box
box = bd.Solid.make_box(10, 10, 10)
print(f'Native Box Faces: {len(list(box.faces()))}')

# Polygon-approximierter Zylinder (über Sketch)
from shapely.geometry import Polygon
import math

n_pts = 12
radius = 10.0
coords = [
    (radius * math.cos(2 * math.pi * i / n_pts),
     radius * math.sin(2 * math.pi * i / n_pts))
    for i in range(n_pts)
]
poly = Polygon(coords)
print(f'\nPolygon (12-Punkte) hat {len(list(poly.exterior.coords))} Koordinaten')
