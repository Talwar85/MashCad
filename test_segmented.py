"""Test Segmented Konvertierung mit verschiedenen Toleranzen."""
from loguru import logger
import sys

logger.remove()
logger.add(sys.stderr, format="<level>{level: <8}</level> | {message}", level="INFO")

from meshconverter.mesh_converter_v10 import MeshToBREPConverterV10, MeshLoader, ConversionStatus

print("=" * 60)
print("SEGMENTED KONVERTIERUNG - V1.stl mit verschiedenen Toleranzen")
print("=" * 60)

filepath = 'stl/V1.stl'

# Teste verschiedene Winkel-Toleranzen
tolerances = [5, 10, 15, 20, 30, 45]

for angle_tol in tolerances:
    print(f"\n--- Winkeltoleranz: {angle_tol}° ---")

    converter = MeshToBREPConverterV10(
        angle_tolerance=angle_tol,
        sewing_tolerance=0.5,
        max_sewing_tolerance=5.0
    )

    result = converter.convert(filepath)

    status = "SUCCESS" if result.status == ConversionStatus.SUCCESS else result.status.name
    regions = result.stats.get('regions', '?')
    faces = result.stats.get('faces_created', '?')
    free_edges = result.stats.get('free_edges', '?')

    print(f"  Status: {status}")
    print(f"  Regionen: {regions}")
    print(f"  Faces: {faces}")
    print(f"  Free Edges: {free_edges}")
    if result.message:
        print(f"  Message: {result.message}")
