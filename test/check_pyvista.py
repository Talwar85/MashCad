import pyvista as pv
mesh = pv.read('stl/V1.stl')
print(f'n_points: {mesh.n_points}')
print(f'n_cells: {mesh.n_cells}')
print(f'faces shape: {mesh.faces.shape}')
print(f'faces[0]: {mesh.faces[0]}')
print(f'faces[:3]:\n{mesh.faces[:3]}')
