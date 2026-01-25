"""
Test für Direct Mesh Converter & Topology-Preserving Converter
"""
from loguru import logger
import sys

# Logger-Format
logger.remove()
logger.add(sys.stderr, format="<level>{level: <8}</level> | {message}", level="DEBUG")

print("=" * 60)
print("Mesh-to-BREP Converter - Test")
print("=" * 60)

from meshconverter.direct_mesh_converter import convert_direct_mesh
from meshconverter.topology_preserver import convert_topology_preserving
from meshconverter.mesh_converter_v10 import convert_stl_to_brep, ConversionStatus


def test_file(filepath, mode="direct"):
    """
    Testet Konvertierung mit verschiedenen Modi.

    Args:
        mode: "direct", "topology", "standard"
    """
    print(f"\n{'=' * 60}")
    print(f"Testing: {filepath}")
    print(f"Mode: {mode}")
    print("=" * 60)

    if mode == "direct":
        result = convert_direct_mesh(filepath)
    elif mode == "topology":
        result = convert_topology_preserving(filepath, angle_tolerance=15.0)
    else:
        result = convert_stl_to_brep(filepath)

    status_ok = result.status == ConversionStatus.SUCCESS
    status_icon = "OK" if status_ok else "PARTIAL" if result.status == ConversionStatus.PARTIAL else "FAILED"

    print(f"\nStatus: {status_icon}")
    if result.message:
        print(f"Message: {result.message}")
    print(f"Stats: {result.stats}")

    if result.solid:
        try:
            # Volume und Area berechnen via BRepGProp
            from OCP.GProp import GProp_GProps
            from OCP.BRepGProp import BRepGProp

            props = GProp_GProps()
            BRepGProp.VolumeProperties_s(result.solid, props)
            vol = props.Mass()

            props2 = GProp_GProps()
            BRepGProp.SurfaceProperties_s(result.solid, props2)
            area = props2.Mass()

            print(f"Volume: {vol:.2f} mm3")
            print(f"Area: {area:.2f} mm2")

            # Positives Volumen?
            if vol > 0:
                print("Volume: POSITIV (gut)")
            else:
                print("Volume: NEGATIV (invertierte Normalen!)")
        except Exception as e:
            print(f"Volume/Area Error: {e}")

    return status_ok


# Test alle Dateien
test_files = ['stl/rechteck.stl', 'stl/V1.stl', 'stl/V2.stl']

# Test Direct Mesh Converter (neuer Ansatz)
print("\n" + "=" * 60)
print("DIRECT MESH CONVERTER MODE")
print("=" * 60)

results_direct = {}
for f in test_files:
    results_direct[f] = test_file(f, mode="direct")

print("\n" + "=" * 60)
print("ZUSAMMENFASSUNG - Direct Mesh")
print("=" * 60)
for f, ok in results_direct.items():
    status = "SUCCESS" if ok else "FAILED"
    print(f"  {f}: {status}")

# Auch Topology-Preserving testen zum Vergleich
print("\n" + "=" * 60)
print("TOPOLOGY-PRESERVING MODE (zum Vergleich)")
print("=" * 60)

results_tp = {}
for f in test_files:
    results_tp[f] = test_file(f, mode="topology")

print("\n" + "=" * 60)
print("ZUSAMMENFASSUNG - Topology-Preserving")
print("=" * 60)
for f, ok in results_tp.items():
    status = "SUCCESS" if ok else "FAILED"
    print(f"  {f}: {status}")

# Finale Zusammenfassung
print("\n" + "=" * 60)
print("FINALE ZUSAMMENFASSUNG")
print("=" * 60)
print("\nDirect Mesh:")
direct_success = sum(1 for ok in results_direct.values() if ok)
print(f"  {direct_success}/{len(results_direct)} erfolgreich")

print("\nTopology-Preserving:")
tp_success = sum(1 for ok in results_tp.values() if ok)
print(f"  {tp_success}/{len(results_tp)} erfolgreich")
