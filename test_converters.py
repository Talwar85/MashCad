"""
Quick Test Script für Mesh Converter
Testet V6, V7 und Hybrid mit den Beispiel-STLs
"""

import sys
import pyvista as pv
from loguru import logger

# Test V6 - Smart Planar
def test_v6(stl_path):
    logger.info("\n=== TEST V6: Smart Planar ===")
    try:
        from modeling.mesh_converter_v6 import SmartMeshConverter
        mesh = pv.read(stl_path)
        logger.info(f"Mesh geladen: {mesh.n_points} Punkte, {mesh.n_cells} Faces")

        converter = SmartMeshConverter()
        solid = converter.convert(mesh, method="smart")

        if solid:
            logger.success("✅ V6 erfolgreich")
            return True
        else:
            logger.error("❌ V6 fehlgeschlagen")
            return False
    except Exception as e:
        logger.error(f"❌ V6 Exception: {e}")
        return False


# Test V7 - RANSAC Primitives
def test_v7(stl_path):
    logger.info("\n=== TEST V7: RANSAC Primitives ===")
    try:
        from modeling.mesh_converter_primitives import RANSACPrimitiveConverter
        mesh = pv.read(stl_path)

        converter = RANSACPrimitiveConverter()
        solid = converter.convert(mesh)

        if solid:
            logger.success("✅ V7 erfolgreich")
            return True
        else:
            logger.error("❌ V7 fehlgeschlagen")
            return False
    except Exception as e:
        logger.error(f"❌ V7 Exception: {e}")
        import traceback
        traceback.print_exc()
        return False


# Test Hybrid
def test_hybrid(stl_path):
    logger.info("\n=== TEST HYBRID: Automatische Wahl ===")
    try:
        from modeling.mesh_converter_hybrid import HybridMeshConverter
        mesh = pv.read(stl_path)

        converter = HybridMeshConverter()
        solid = converter.convert(mesh)

        if solid:
            logger.success("✅ Hybrid erfolgreich")
            return True
        else:
            logger.error("❌ Hybrid fehlgeschlagen")
            return False
    except Exception as e:
        logger.error(f"❌ Hybrid Exception: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    # Test mit beiden STLs
    test_files = [
        "stl/V1.stl",
        "stl/V2.stl"
    ]

    for stl_file in test_files:
        logger.info(f"\n{'='*60}")
        logger.info(f"Testing: {stl_file}")
        logger.info(f"{'='*60}")

        # Test alle 3 Converter
        v6_ok = test_v6(stl_file)
        v7_ok = test_v7(stl_file)
        hybrid_ok = test_hybrid(stl_file)

        logger.info(f"\nErgebnisse für {stl_file}:")
        logger.info(f"  V6 (Smart):     {'✅' if v6_ok else '❌'}")
        logger.info(f"  V7 (Primitives): {'✅' if v7_ok else '❌'}")
        logger.info(f"  Hybrid (Auto):   {'✅' if hybrid_ok else '❌'}")

    logger.info("\n" + "="*60)
    logger.info("Test abgeschlossen")
