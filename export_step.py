"""Exportiert konvertierte STL-Dateien als STEP."""
from loguru import logger
import sys
import os

logger.remove()
logger.add(sys.stderr, format="<level>{level: <8}</level> | {message}", level="INFO")

from meshconverter.hybrid_mesh_converter import convert_hybrid_mesh
from meshconverter.mesh_converter_v10 import ConversionStatus

try:
    from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
    from OCP.IFSelect import IFSelect_RetDone
    HAS_STEP = True
except ImportError:
    HAS_STEP = False
    print("STEP Export nicht verfügbar (OCP fehlt)")

def export_to_step(solid, filepath):
    """Exportiert Solid als STEP-Datei."""
    if not HAS_STEP:
        return False

    try:
        # Handle build123d Solid vs raw TopoDS_Solid
        from OCP.TopoDS import TopoDS_Shape
        if hasattr(solid, 'wrapped'):
            # build123d Solid - extrahiere wrapped TopoDS_Solid
            shape = solid.wrapped
        elif isinstance(solid, TopoDS_Shape):
            shape = solid
        else:
            logger.error(f"Unbekannter Solid-Typ: {type(solid)}")
            return False

        writer = STEPControl_Writer()
        writer.Transfer(shape, STEPControl_AsIs)
        status = writer.Write(filepath)
        return status == IFSelect_RetDone
    except Exception as e:
        logger.error(f"STEP Export fehlgeschlagen: {e}")
        return False


test_files = ['stl/rechteck.stl', 'stl/V1.stl', 'stl/V2.stl']
output_dir = 'step_output'

# Output-Verzeichnis erstellen
os.makedirs(output_dir, exist_ok=True)

print("=" * 60)
print("STL zu STEP Konvertierung")
print("=" * 60)

for stl_file in test_files:
    print(f"\nKonvertiere: {stl_file}")

    result = convert_hybrid_mesh(stl_file)

    if result.status == ConversionStatus.SUCCESS and result.solid:
        # STEP-Dateiname generieren
        base_name = os.path.splitext(os.path.basename(stl_file))[0]
        step_file = os.path.join(output_dir, f"{base_name}.step")

        # Exportieren
        success = export_to_step(result.solid, step_file)

        if success:
            faces = result.stats.get('faces_after_unify', result.stats.get('faces_created', '?'))
            print(f"  OK: {step_file}")
            print(f"  Faces: {faces}")
        else:
            print(f"  FEHLER: Export fehlgeschlagen")
    else:
        print(f"  FEHLER: Konvertierung fehlgeschlagen - {result.message}")

print("\n" + "=" * 60)
print(f"STEP-Dateien in: {os.path.abspath(output_dir)}")
print("=" * 60)
