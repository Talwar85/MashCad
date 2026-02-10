"""Quick visual comparison test"""
import sys
sys.path.insert(0, 'c:/LiteCad')

import pyvista as pv
from meshconverter import SimpleConverter, CurrentConverter, CurrentMode

# Load mesh
mesh = pv.read('stl/V1.stl')
print(f"Mesh: {mesh.n_points} points, {mesh.n_cells} faces")
print()

# SimpleConverter
print("="*60)
print("SIMPLE CONVERTER")
print("="*60)
simple = SimpleConverter()
result_simple = simple.convert_async(mesh)
print(f"Status: {result_simple.status.value if result_simple.status else 'N/A'}")
print(f"Face-Count: {result_simple.face_count}")
print()

# CurrentConverter V10
print("="*60)
print("CURRENT CONVERTER (V10)")
print("="*60)
current_v10 = CurrentConverter(mode=CurrentMode.V10)
result_v10 = current_v10.convert_async(mesh)
print(f"Status: {result_v10.status.value if result_v10.status else 'N/A'}")
print(f"Face-Count: {result_v10.face_count}")
print()

# Summary
print("="*60)
print("SUMMARY")
print("="*60)
print(f"{'Converter':<20} {'Faces':>10}")
print("-"*60)
print(f"{'Simple':<20} {result_simple.face_count:>10}")
print(f"{'Current V10':<20} {result_v10.face_count:>10}")
