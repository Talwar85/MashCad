"""
Test-Skript für Mesh-zu-BREP Konverter V10
==========================================
"""
import os
import sys
from loguru import logger

# Logging Setup
logger.remove()
logger.add(sys.stderr, level="DEBUG", format="<level>{level: <8}</level> | {message}")

def test_single_stl(filepath: str):
    """Testet eine einzelne STL-Datei."""
    from meshconverter import convert_stl_to_brep, ConversionStatus

    print(f"\n{'='*60}")
    print(f"Testing: {filepath}")
    print(f"{'='*60}")

    if not os.path.exists(filepath):
        print(f"ERROR: File not found: {filepath}")
        return False

    # Konvertieren
    result = convert_stl_to_brep(filepath)

    # Ergebnis ausgeben
    print(f"\nStatus: {result.status.name}")
    print(f"Message: {result.message}")
    print(f"Stats: {result.stats}")

    if result.solid:
        solid = result.solid
        print(f"\nSolid erstellt: {type(solid).__name__}")

        # Build123d Solid Info
        try:
            print(f"  - Volume: {solid.volume:.2f} mm³")
            print(f"  - Area: {solid.area:.2f} mm²")
            print(f"  - Bounding Box: {solid.bounding_box()}")
        except Exception as e:
            print(f"  - Info error: {e}")

        return result.status == ConversionStatus.SUCCESS
    else:
        print("\nKein Solid erstellt!")
        return False

def main():
    """Hauptfunktion - testet alle STL-Dateien."""
    print("="*60)
    print("Mesh-zu-BREP Konverter V10 - Test Suite")
    print("="*60)

    # Test-Dateien
    stl_files = [
        "stl/rechteck.stl",
        "stl/V1.stl",
        "stl/V2.stl"
    ]

    results = {}

    for stl_file in stl_files:
        try:
            success = test_single_stl(stl_file)
            results[stl_file] = "✅ SUCCESS" if success else "❌ FAILED"
        except Exception as e:
            logger.exception(f"Exception bei {stl_file}")
            results[stl_file] = f"💥 EXCEPTION: {e}"

    # Zusammenfassung
    print("\n" + "="*60)
    print("ZUSAMMENFASSUNG")
    print("="*60)
    for file, status in results.items():
        print(f"  {file}: {status}")

if __name__ == "__main__":
    main()
