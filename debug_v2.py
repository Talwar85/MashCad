"""Debug V2.stl - Welche Primitive werden erkannt?"""
from loguru import logger
import sys

logger.remove()
logger.add(sys.stderr, format="<level>{level: <8}</level> | {message}", level="DEBUG")

from meshconverter.mesh_converter_v10 import MeshLoader, MeshToBREPConverterV10

filepath = 'stl/V2.stl'

# Mesh laden
load_result = MeshLoader.load(filepath, repair=True)
mesh = load_result.mesh

print(f"Mesh: {mesh.n_points} Punkte, {mesh.n_cells} Faces")

# Segmentierung
from meshconverter.surface_segmenter import SurfaceSegmenter
segmenter = SurfaceSegmenter(angle_tolerance=5.0)
regions = segmenter.segment(mesh)

print(f"\n{len(regions)} Regionen gefunden")

# Primitive Fitting
from meshconverter.primitive_fitter import PrimitiveFitter
fitter = PrimitiveFitter(tolerance=0.5, min_confidence=0.5)  # Niedrigere Confidence für Debug

primitives_by_type = {}
no_fit_count = 0
for region in regions:
    primitive = fitter.fit_region(mesh, region)

    if primitive:
        ptype = primitive.type
        if ptype not in primitives_by_type:
            primitives_by_type[ptype] = []
        primitives_by_type[ptype].append({
            'region_id': region.region_id,
            'area': region.area,
            'confidence': primitive.confidence,
            'error': primitive.error,
            'params': primitive.params
        })
    else:
        no_fit_count += 1

print(f"\nRegionen ohne Primitiv-Fit: {no_fit_count}")

print("\nErkannte Primitive:")
for ptype, prims in primitives_by_type.items():
    print(f"\n  {ptype}: {len(prims)} Stück")
    # Zeige Details für Zylinder
    if ptype == 'cylinder':
        for p in prims[:5]:  # Erste 5
            print(f"    Region {p['region_id']}: r={p['params'].get('radius', '?'):.2f}mm, "
                  f"h={p['params'].get('height', '?'):.2f}mm, error={p['error']:.3f}mm")
