"""Debug STEP Export für MGN12H."""
from loguru import logger
import sys
import os

logger.remove()
logger.add(sys.stderr, format="<level>{level: <8}</level> | {message}", level="DEBUG")

from meshconverter.direct_mesh_converter import DirectMeshConverter
from meshconverter.mesh_converter_v10 import MeshLoader
from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
from OCP.IFSelect import IFSelect_RetDone
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE, TopAbs_VERTEX
from OCP.BRep import BRep_Tool
from OCP.TopoDS import TopoDS

print("=== DEBUG STEP EXPORT ===\n")

# 1. Lade STL
print("1. Lade STL...")
load_result = MeshLoader.load('stl/MGN12H_X_Carriage_Lite (1).stl', repair=True)
mesh = load_result.mesh
print(f"   STL Bounds: {mesh.bounds}")
print(f"   STL Punkte: {mesh.n_points}, Faces: {mesh.n_cells}")

# 2. Konvertiere
print("\n2. Konvertiere zu BREP...")
converter = DirectMeshConverter(unify_faces=False)
result = converter.convert(mesh)
print(f"   Status: {result.status.name}")
print(f"   Faces erstellt: {result.stats.get('faces_created', '?')}")

if result.solid:
    solid = result.solid

    # 3. Zähle Faces und Vertices im Solid
    print("\n3. Prüfe BREP Solid...")

    face_count = 0
    exp = TopExp_Explorer(solid, TopAbs_FACE)
    while exp.More():
        face_count += 1
        exp.Next()
    print(f"   BREP Faces: {face_count}")

    # Vertices zählen und Bounds ermitteln
    vertex_count = 0
    x_coords = []
    y_coords = []
    z_coords = []

    exp = TopExp_Explorer(solid, TopAbs_VERTEX)
    while exp.More():
        vertex = TopoDS.Vertex_s(exp.Current())
        pnt = BRep_Tool.Pnt_s(vertex)
        x_coords.append(pnt.X())
        y_coords.append(pnt.Y())
        z_coords.append(pnt.Z())
        vertex_count += 1
        exp.Next()

    print(f"   BREP Vertices: {vertex_count}")
    if x_coords:
        print(f"   BREP Bounds: X=[{min(x_coords):.2f}, {max(x_coords):.2f}]")
        print(f"                Y=[{min(y_coords):.2f}, {max(y_coords):.2f}]")
        print(f"                Z=[{min(z_coords):.2f}, {max(z_coords):.2f}]")
        print(f"   BREP Größe: {max(x_coords)-min(x_coords):.2f} x {max(y_coords)-min(y_coords):.2f} x {max(z_coords)-min(z_coords):.2f} mm")

    # 4. STEP Export
    print("\n4. STEP Export...")
    step_file = 'step_output/MGN12H_debug.step'

    writer = STEPControl_Writer()
    transfer_status = writer.Transfer(solid, STEPControl_AsIs)
    print(f"   Transfer Status: {transfer_status}")

    write_status = writer.Write(step_file)
    print(f"   Write Status: {write_status} (1=OK)")

    if write_status == IFSelect_RetDone:
        file_size = os.path.getsize(step_file) / 1024
        print(f"   Datei: {step_file} ({file_size:.0f} KB)")
else:
    print("   FEHLER: Kein Solid erstellt!")
