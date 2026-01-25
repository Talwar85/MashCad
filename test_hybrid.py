"""Test Hybrid Mesh Converter mit Zylinder-Erkennung."""
from loguru import logger
import sys

logger.remove()
logger.add(sys.stderr, format="<level>{level: <8}</level> | {message}", level="DEBUG")

from meshconverter.hybrid_mesh_converter import convert_hybrid_mesh
from meshconverter.mesh_converter_v10 import ConversionStatus

print("=" * 60)
print("HYBRID MESH CONVERTER TEST")
print("=" * 60)

test_files = ['stl/V2.stl', 'stl/V1.stl', 'stl/rechteck.stl']

for filepath in test_files:
    print(f"\n--- {filepath} ---")

    result = convert_hybrid_mesh(filepath)

    print(f"Status: {result.status.name}")
    print(f"Stats: {result.stats}")

    if result.message:
        print(f"Message: {result.message}")
