"""Debug-Test für Zylinder-Winkelberechnung."""
from loguru import logger
import sys
import numpy as np

logger.remove()
logger.add(sys.stderr, format="<level>{level: <8}</level> | {message}", level="DEBUG")

from meshconverter.mesh_converter_v10 import MeshLoader
from meshconverter.mesh_primitive_detector import MeshPrimitiveDetector

# Teste V1
stl_path = 'stl/V1.stl'
print(f"Teste: {stl_path}")

load_result = MeshLoader.load(stl_path, repair=True)
mesh = load_result.mesh
print(f"Mesh: {mesh.n_points} Punkte, {mesh.n_cells} Faces")

# Erkenne Primitive
detector = MeshPrimitiveDetector(
    angle_threshold=12.0,
    min_region_faces=12,
    cylinder_tolerance=0.5,
    sphere_tolerance=0.5,
    min_inlier_ratio=0.85
)

cylinders, spheres = detector.detect_from_mesh(mesh)
print(f"\n{len(cylinders)} Zylinder gefunden")

# Analysiere jeden Zylinder
faces = mesh.faces.reshape(-1, 4)[:, 1:4]
points = mesh.points

for i, cyl in enumerate(cylinders):
    print(f"\n=== Zylinder {i+1} ===")
    print(f"Radius: {cyl.radius:.2f}mm")
    print(f"Höhe: {cyl.height:.2f}mm")
    print(f"Faces: {len(cyl.face_indices)}")
    print(f"Center: {cyl.center}")
    print(f"Axis: {cyl.axis}")

    # Sammle Punkte
    vertex_set = set()
    for f_idx in cyl.face_indices:
        for v_idx in faces[f_idx]:
            vertex_set.add(v_idx)

    region_points = points[list(vertex_set)]
    print(f"Punkte: {len(region_points)}")

    # Berechne Winkel
    center = cyl.center
    axis = cyl.axis

    to_center = region_points - center
    proj = np.dot(to_center, axis)

    # Lokale X/Y Achsen
    z_axis = axis
    if abs(z_axis[2]) < 0.9:
        x_axis = np.cross(z_axis, [0, 0, 1])
    else:
        x_axis = np.cross(z_axis, [1, 0, 0])
    x_axis = x_axis / np.linalg.norm(x_axis)
    y_axis = np.cross(z_axis, x_axis)

    # Radiale Vektoren
    radial = to_center - np.outer(proj, axis)
    x_comp = np.dot(radial, x_axis)
    y_comp = np.dot(radial, y_axis)
    angles = np.arctan2(y_comp, x_comp)

    print(f"\nWinkel-Statistik:")
    print(f"  Min: {np.degrees(angles.min()):.1f}°")
    print(f"  Max: {np.degrees(angles.max()):.1f}°")
    print(f"  Bereich: {np.degrees(angles.max() - angles.min()):.1f}°")

    # Sortierte Analyse
    sorted_angles = np.sort(angles)
    angle_diffs = np.diff(sorted_angles)

    print(f"\nLücken-Analyse:")
    print(f"  Anzahl Winkel: {len(sorted_angles)}")

    if len(angle_diffs) > 0:
        print(f"  Max interne Lücke: {np.degrees(np.max(angle_diffs)):.1f}°")

    wrap_diff = (2 * np.pi) - (sorted_angles[-1] - sorted_angles[0])
    print(f"  Wrap-Around Lücke: {np.degrees(wrap_diff):.1f}°")

    max_gap = max(wrap_diff, np.max(angle_diffs) if len(angle_diffs) > 0 else 0)
    print(f"  Größte Lücke: {np.degrees(max_gap):.1f}°")

    if max_gap < np.radians(45):
        print(f"  => VOLLSTÄNDIGER Zylinder (Lücke < 45°)")
    else:
        print(f"  => PARTIELLER Zylinder (Lücke >= 45°)")

    # Zeige Winkel-Histogramm
    print(f"\nWinkel-Verteilung (alle 30°):")
    bins = np.arange(-180, 181, 30)
    hist, _ = np.histogram(np.degrees(angles), bins=bins)
    for j in range(len(hist)):
        bar = "█" * (hist[j] // 2)
        print(f"  {bins[j]:4d}° bis {bins[j+1]:4d}°: {hist[j]:3d} {bar}")
