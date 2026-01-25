"""Final Validation Test für Mesh-zu-BREP Konverter"""
from loguru import logger
import sys

logger.remove()
logger.add(sys.stderr, format="<level>{level: <8}</level> | {message}", level="INFO")

from meshconverter.mesh_converter_v10 import convert_stl_to_brep, ConversionStatus

test_files = ['stl/rechteck.stl', 'stl/V1.stl', 'stl/V2.stl']

print("=" * 60)
print("FINAL VALIDATION - Auto Mode (Hybrid)")
print("=" * 60)

all_success = True
for f in test_files:
    print(f"\nTesting: {f}")
    result = convert_stl_to_brep(f, mode="auto")

    status = "OK" if result.status == ConversionStatus.SUCCESS else "FAIL"
    if result.status != ConversionStatus.SUCCESS:
        all_success = False

    faces_created = result.stats.get('faces_created', '?')
    faces_after = result.stats.get('faces_after_unify', faces_created)
    print(f"  Status: {status}")
    print(f"  Faces: {faces_after} (erstellt: {faces_created})")
    if result.message:
        print(f"  Message: {result.message}")

print("\n" + "=" * 60)
if all_success:
    print("ALL TESTS PASSED!")
else:
    print("SOME TESTS FAILED")
print("=" * 60)
