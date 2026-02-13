"""
MashCad - Fillet-Aware Mesh-to-BREP Converter
==============================================

Uses V9 fillet/chamfer detection for proper analytical surfaces.
Creates CYLINDRICAL_SURFACE for fillets, PLANE for chamfers and main faces.

Strategy:
1. Use V9 detector to identify main faces, fillets, and chamfers
2. Create cylindrical faces for fillets
3. Create planar faces for chamfers and main surfaces
4. Sew everything together into a solid
"""

import sys
from pathlib import Path

# Add parent directory to path for imports when running directly
if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
from pathlib import Path
from typing import List, Optional, Tuple, Set
from dataclasses import dataclass
from collections import defaultdict
from loguru import logger

try:
    import pyvista as pv
    HAS_PYVISTA = True
except ImportError:
    HAS_PYVISTA = False

try:
    from OCP.gp import gp_Pnt, gp_Vec, gp_Dir, gp_Ax2, gp_Ax3, gp_Pln
    from OCP.Geom import Geom_CylindricalSurface
    from OCP.BRepBuilderAPI import (
        BRepBuilderAPI_MakeEdge,
        BRepBuilderAPI_MakeWire,
        BRepBuilderAPI_MakeFace,
        BRepBuilderAPI_Sewing
    )
    from OCP.TopoDS import TopoDS_Face, TopoDS_Wire, TopoDS_Shell, TopoDS
    from OCP.ShapeFix import ShapeFix_Solid
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
    HAS_OCP = True
except ImportError:
    HAS_OCP = False
    logger.warning("OCP nicht verfügbar")

try:
    from build123d import Solid, Shell, Shape, export_step
    HAS_BUILD123D = True
except ImportError:
    HAS_BUILD123D = False

try:
    from scipy.sparse import lil_matrix
    from scipy.sparse.csgraph import connected_components
    from sklearn.cluster import AgglomerativeClustering
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False
    logger.warning("Scipy/Sklearn nicht verfügbar (Mesh-Analyse eingeschränkt)")

# Import from same package or fallback to direct import
try:
    from meshconverter.mesh_converter_v10 import (
        ConversionStatus, ConversionResult, MeshLoader, LoadStatus
    )
except ImportError:
    from mesh_converter_v10 import (
        ConversionStatus, ConversionResult, MeshLoader, LoadStatus
    )


@dataclass
class FilletRegion:
    """Detected fillet region (cylindrical surface)."""
    face_ids: Set[int]
    axis: np.ndarray
    axis_point: np.ndarray
    radius: float
    arc_angle: float
    fit_error: float


@dataclass
class ChamferRegion:
    """Detected chamfer region (planar surface)."""
    face_ids: Set[int]
    normal: np.ndarray
    plane_point: np.ndarray
    width: float


@dataclass
class MainFaceRegion:
    """Main planar face region."""
    face_ids: Set[int]
    normal: np.ndarray
    centroid: np.ndarray
    area: float


class FilletAwareConverter:
    """
    Mesh-to-BREP converter with proper fillet detection.

    Uses V9-style detection algorithm to identify:
    - Main planar faces (large, flat regions)
    - Fillets (cylindrical strips)
    - Chamfers (planar bevels)
    """

    def __init__(
        self,
        min_main_area_ratio: float = 0.02,
        plane_tolerance: float = 1.0,
        cylinder_tolerance: float = 3.0,
        sewing_tolerance: float = 1.0
    ):
        self.min_main_ratio = min_main_area_ratio
        self.plane_tol = plane_tolerance
        self.cyl_tol = cylinder_tolerance
        self.sewing_tol = sewing_tolerance

    def convert(self, filepath: str) -> ConversionResult:
        """Convert mesh file to BREP with analytical surfaces."""

        logger.info(f"=== Fillet-Aware Converter ===")
        logger.info(f"Input: {filepath}")

        # 1. Load mesh
        load_result = MeshLoader.load(filepath, repair=True)
        if load_result.status == LoadStatus.FAILED:
            return ConversionResult(
                status=ConversionStatus.FAILED,
                message=f"Load failed: {load_result.message}"
            )

        mesh = load_result.mesh
        return self.convert_mesh(mesh)

    def convert_mesh(self, mesh: 'pv.PolyData') -> ConversionResult:
        """Convert PyVista mesh to BREP solid."""

        if not HAS_OCP:
            return ConversionResult(
                status=ConversionStatus.FAILED,
                message="OCP not available"
            )

        stats = {
            'input_faces': mesh.n_cells,
            'input_points': mesh.n_points
        }

        # Compute normals
        if 'Normals' not in mesh.cell_data:
            mesh = mesh.compute_normals(cell_normals=True, point_normals=False)

        cell_normals = mesh.cell_data['Normals']
        edge_to_faces = self._build_edge_face_map(mesh)

        # Compute areas
        mesh_with_areas = mesh.compute_cell_sizes()
        areas = mesh_with_areas.cell_data['Area']
        total_area = np.sum(areas)

        # === PHASE 1: Cluster faces by normal ===
        logger.info("Phase 1: Clustering faces by normal...")
        normal_clusters = self._cluster_by_normal(cell_normals, threshold_deg=30.0)
        logger.info(f"  → {len(normal_clusters)} normal clusters")

        # === PHASE 2: Identify planar main faces ===
        logger.info("Phase 2: Identifying main planar faces...")
        main_faces = []
        main_face_ids = set()

        for cluster_faces in normal_clusters.values():
            cluster_area = sum(areas[fid] for fid in cluster_faces)
            area_ratio = cluster_area / total_area

            if area_ratio < self.min_main_ratio:
                continue

            plane_fit = self._fit_plane(mesh, cluster_faces)
            if plane_fit is not None and plane_fit['error'] < self.plane_tol:
                main_face_ids.update(cluster_faces)
                main_faces.append(MainFaceRegion(
                    face_ids=cluster_faces,
                    normal=plane_fit['normal'],
                    centroid=plane_fit['centroid'],
                    area=cluster_area
                ))

        feature_face_ids = set(range(mesh.n_cells)) - main_face_ids
        logger.info(f"  → {len(main_faces)} main faces, {len(feature_face_ids)} feature faces")
        stats['main_faces'] = len(main_faces)
        stats['feature_faces'] = len(feature_face_ids)

        # === PHASE 3: Segment feature faces ===
        logger.info("Phase 3: Segmenting feature regions...")
        feature_regions = self._segment_faces(mesh, feature_face_ids, edge_to_faces, cell_normals, 30.0)
        logger.info(f"  → {len(feature_regions)} feature regions")

        # === PHASE 4: Classify features as fillets or chamfers ===
        logger.info("Phase 4: Classifying features...")
        fillets = []
        chamfers = []

        for region in feature_regions:
            if len(region) < 2:
                continue

            plane_fit = self._fit_plane(mesh, region)
            cyl_fit = self._fit_cylinder(mesh, region, cell_normals)

            plane_error = plane_fit['error'] if plane_fit else float('inf')
            cyl_error = cyl_fit['error'] if cyl_fit else float('inf')

            if cyl_fit and cyl_error < self.cyl_tol and cyl_error < plane_error * 0.8:
                fillets.append(FilletRegion(
                    face_ids=region,
                    axis=cyl_fit['axis'],
                    axis_point=cyl_fit['center'],
                    radius=cyl_fit['radius'],
                    arc_angle=cyl_fit['arc_angle'],
                    fit_error=cyl_error
                ))
                logger.debug(f"  Fillet: r={cyl_fit['radius']:.2f}mm, arc={np.degrees(cyl_fit['arc_angle']):.1f}°")
            elif plane_fit and plane_error < self.plane_tol:
                width = self._compute_region_width(mesh, region, plane_fit)
                chamfers.append(ChamferRegion(
                    face_ids=region,
                    normal=plane_fit['normal'],
                    plane_point=plane_fit['centroid'],
                    width=width
                ))
                logger.debug(f"  Chamfer: w={width:.2f}mm")

        logger.info(f"  → {len(fillets)} fillets (disabled), {len(chamfers)} chamfers")
        stats['fillets_detected'] = len(fillets)
        stats['fillets_converted'] = 0  # Disabled
        stats['chamfers'] = len(chamfers)

        # === PHASE 5: Create BREP faces ===
        logger.info("Phase 5: Creating BREP faces...")
        faces = []

        # NOTE: Fillet (cylindrical) face creation is disabled for now
        # The arc edges implementation needs further work
        # Fillets are skipped - only chamfers and main faces are converted
        if fillets:
            logger.warning(f"  ⚠ {len(fillets)} fillets detected but SKIPPED (disabled)")
            logger.warning(f"    Fillet conversion is disabled until arc edges are fixed")

        # Create planar faces for chamfers
        for chamfer in chamfers:
            face = self._create_planar_face(mesh, chamfer.face_ids, chamfer.normal, chamfer.plane_point)
            if face:
                faces.append(face)

        # Create planar faces for main faces
        for main_face in main_faces:
            face = self._create_planar_face(mesh, main_face.face_ids, main_face.normal, main_face.centroid)
            if face:
                faces.append(face)

        logger.info(f"  → {len(faces)} BREP faces created")
        stats['faces_created'] = len(faces)

        if len(faces) == 0:
            return ConversionResult(
                status=ConversionStatus.FAILED,
                message="No BREP faces created",
                stats=stats
            )

        # === PHASE 6: Sew faces into solid ===
        logger.info("Phase 6: Sewing faces into solid...")
        result = self._sew_faces(faces)
        result.stats.update(stats)

        logger.info(f"=== Result: {result.status.name} ===")
        return result

    def _build_edge_face_map(self, mesh: 'pv.PolyData') -> dict:
        """Build edge to face adjacency map."""
        edge_to_faces = defaultdict(list)
        for face_id in range(mesh.n_cells):
            cell = mesh.get_cell(face_id)
            pts = cell.point_ids
            for i in range(len(pts)):
                edge = tuple(sorted([pts[i], pts[(i + 1) % len(pts)]]))
                edge_to_faces[edge].append(face_id)
        return edge_to_faces

    def _cluster_by_normal(self, cell_normals: np.ndarray, threshold_deg: float) -> dict:
        """Cluster faces by normal similarity."""
        if not HAS_SCIPY:
            return {0: set(range(len(cell_normals)))}

        clustering = AgglomerativeClustering(
            n_clusters=None,
            distance_threshold=1 - np.cos(np.radians(threshold_deg)),
            metric='cosine',
            linkage='average'
        )
        labels = clustering.fit_predict(cell_normals)
        clusters = defaultdict(set)
        for face_id, label in enumerate(labels):
            clusters[label].add(face_id)
        return clusters

    def _segment_faces(self, mesh, face_ids: Set[int], edge_to_faces: dict,
                       cell_normals: np.ndarray, angle_threshold: float) -> List[Set[int]]:
        """Segment faces into connected regions."""
        if not HAS_SCIPY:
            return [face_ids]

        if not face_ids:
            return []

        face_list = list(face_ids)
        face_to_idx = {f: i for i, f in enumerate(face_list)}
        n = len(face_list)
        adjacency = lil_matrix((n, n), dtype=np.int8)
        angle_rad = np.radians(angle_threshold)

        for edge, faces in edge_to_faces.items():
            if len(faces) != 2:
                continue
            f1, f2 = faces
            if f1 not in face_ids or f2 not in face_ids:
                continue

            n1, n2 = cell_normals[f1], cell_normals[f2]
            dot = np.clip(np.dot(n1, n2), -1, 1)
            if np.arccos(dot) <= angle_rad:
                i1, i2 = face_to_idx[f1], face_to_idx[f2]
                adjacency[i1, i2] = 1
                adjacency[i2, i1] = 1

        n_components, labels = connected_components(adjacency.tocsr(), directed=False, return_labels=True)

        regions = []
        for label_id in range(n_components):
            indices = np.where(labels == label_id)[0]
            region = {face_list[i] for i in indices}
            regions.append(region)
        return regions

    def _fit_plane(self, mesh, face_ids: Set[int]) -> Optional[dict]:
        """Fit plane to face region using SVD."""
        if len(face_ids) < 1:
            return None
        try:
            points = []
            for fid in face_ids:
                cell = mesh.get_cell(fid)
                points.extend(cell.points)
            points = np.unique(np.array(points), axis=0)
            if len(points) < 3:
                return None

            centroid = np.mean(points, axis=0)
            centered = points - centroid
            U, S, Vt = np.linalg.svd(centered, full_matrices=False)
            normal = Vt[-1]
            error = np.mean(np.abs(np.dot(centered, normal)))

            return {'normal': normal, 'centroid': centroid, 'error': error, 'points': points}
        except Exception as e:
            logger.debug(f"[meshconverter] Fehler: {e}")
            return None

    def _fit_cylinder(self, mesh, face_ids: Set[int], cell_normals: np.ndarray) -> Optional[dict]:
        """Fit cylinder using 2D circle fit (V9 algorithm)."""
        if len(face_ids) < 3:
            return None

        try:
            points = []
            for fid in face_ids:
                cell = mesh.get_cell(fid)
                points.extend(cell.points)
            points_3d = np.unique(np.array(points), axis=0)

            if len(points_3d) < 6:
                return None

            # 1. Axis direction via PCA on points
            centroid = np.mean(points_3d, axis=0)
            centered = points_3d - centroid
            U, S, Vt = np.linalg.svd(centered, full_matrices=False)
            axis = Vt[0]

            # 2. Local coordinate system perpendicular to axis
            if abs(axis[2]) < 0.9:
                x_local = np.cross(axis, [0, 0, 1])
            else:
                x_local = np.cross(axis, [1, 0, 0])
            x_local = x_local / np.linalg.norm(x_local)
            y_local = np.cross(axis, x_local)

            # 3. Project points to 2D plane
            points_2d = np.column_stack([
                np.dot(centered, x_local),
                np.dot(centered, y_local)
            ])

            # 4. 2D algebraic circle fit
            x = points_2d[:, 0]
            y = points_2d[:, 1]
            A = np.column_stack([2*x, 2*y, np.ones(len(x))])
            b = x**2 + y**2
            result, _, _, _ = np.linalg.lstsq(A, b, rcond=None)
            cx, cy, d = result

            radius_sq = d + cx**2 + cy**2
            if radius_sq <= 0:
                return None
            radius = np.sqrt(radius_sq)
            center_2d = np.array([cx, cy])

            if radius < 0.5 or radius > 1000:
                return None

            # 5. Transform center back to 3D
            center_offset = center_2d[0] * x_local + center_2d[1] * y_local
            axis_point = centroid + center_offset

            # 6. Calculate 3D error
            axis_to_points = points_3d - axis_point
            proj_along_axis = np.dot(axis_to_points, axis)[:, np.newaxis] * axis
            perp = axis_to_points - proj_along_axis
            distances = np.linalg.norm(perp, axis=1)
            error = np.mean(np.abs(distances - radius))

            # 7. Calculate arc angle
            angles = []
            for p in points_3d:
                rel = p - axis_point
                h = np.dot(rel, axis)
                perp_vec = rel - h * axis
                if np.linalg.norm(perp_vec) > 1e-6:
                    pn = perp_vec / np.linalg.norm(perp_vec)
                    angle = np.arctan2(np.dot(pn, y_local), np.dot(pn, x_local))
                    angles.append(angle)

            arc_angle = 2 * np.pi
            if len(angles) >= 3:
                angles = np.array(angles)
                angles_sorted = np.sort(angles)
                gaps = np.diff(angles_sorted)
                gaps = np.append(gaps, angles_sorted[0] + 2*np.pi - angles_sorted[-1])
                arc_angle = 2*np.pi - np.max(gaps)

            # 8. Calculate height
            proj_lengths = np.dot(points_3d - axis_point, axis)
            height = np.max(proj_lengths) - np.min(proj_lengths)
            center = axis_point + ((np.min(proj_lengths) + np.max(proj_lengths)) / 2) * axis

            return {
                'axis': axis,
                'center': center,
                'axis_point': axis_point,
                'radius': radius,
                'height': height,
                'arc_angle': arc_angle,
                'error': error
            }

        except Exception as e:
            logger.debug(f"Cylinder fit failed: {e}")
            return None

    def _compute_region_width(self, mesh, face_ids: Set[int], plane_fit: dict) -> float:
        """Compute width of a planar region."""
        points = []
        for fid in face_ids:
            cell = mesh.get_cell(fid)
            points.extend(cell.points)
        points = np.array(points)

        normal = plane_fit['normal']
        u = np.cross(normal, [0, 0, 1]) if abs(normal[2]) < 0.9 else np.cross(normal, [1, 0, 0])
        u = u / np.linalg.norm(u)
        v = np.cross(normal, u)

        centered = points - plane_fit['centroid']
        return min(np.ptp(np.dot(centered, u)), np.ptp(np.dot(centered, v)))

    def _create_cylindrical_face(self, mesh, fillet: FilletRegion) -> Optional['TopoDS_Face']:
        """Create a cylindrical BREP face for a fillet."""
        try:
            center = fillet.axis_point
            axis = fillet.axis
            radius = fillet.radius
            arc_angle = fillet.arc_angle

            # Create coordinate system
            gp_center = gp_Pnt(float(center[0]), float(center[1]), float(center[2]))
            gp_axis = gp_Dir(float(axis[0]), float(axis[1]), float(axis[2]))

            if abs(axis[2]) < 0.9:
                x_dir = np.cross(axis, [0, 0, 1])
            else:
                x_dir = np.cross(axis, [1, 0, 0])
            x_dir = x_dir / (np.linalg.norm(x_dir) + 1e-10)
            gp_x_dir = gp_Dir(float(x_dir[0]), float(x_dir[1]), float(x_dir[2]))

            ax3 = gp_Ax3(gp_center, gp_axis, gp_x_dir)

            # Create cylindrical surface
            cylinder_surface = Geom_CylindricalSurface(ax3, radius)

            # Calculate height from face geometry
            face_points = []
            for fid in fillet.face_ids:
                cell = mesh.get_cell(fid)
                face_points.extend(cell.points)
            face_points = np.array(face_points)

            proj_lengths = np.dot(face_points - center, axis)
            height = np.max(proj_lengths) - np.min(proj_lengths)

            # U bounds (arc angle)
            u_min = -arc_angle / 2
            u_max = arc_angle / 2

            # V bounds (height)
            v_min = -height / 2
            v_max = height / 2

            face_builder = BRepBuilderAPI_MakeFace(
                cylinder_surface,
                u_min, u_max,
                v_min, v_max,
                1e-6
            )

            if face_builder.IsDone():
                return face_builder.Face()
            return None

        except Exception as e:
            logger.debug(f"Failed to create cylindrical face: {e}")
            return None

    def _create_planar_face(self, mesh, face_ids: Set[int],
                            normal: np.ndarray, centroid: np.ndarray) -> Optional['TopoDS_Face']:
        """Create a planar BREP face from mesh faces."""
        try:
            # Get boundary points
            points = []
            for fid in face_ids:
                cell = mesh.get_cell(fid)
                points.extend(cell.points)
            points = np.unique(np.array(points), axis=0)

            if len(points) < 3:
                return None

            # Create ordered boundary using convex hull
            boundary_points = points

            if HAS_SCIPY:
                from scipy.spatial import ConvexHull

                # Project to 2D for ordering
                u = np.cross(normal, [0, 0, 1]) if abs(normal[2]) < 0.9 else np.cross(normal, [1, 0, 0])
                u = u / np.linalg.norm(u)
                v = np.cross(normal, u)

                centered = points - centroid
                points_2d = np.column_stack([np.dot(centered, u), np.dot(centered, v)])

                try:
                    hull = ConvexHull(points_2d)
                    boundary_indices = hull.vertices
                    boundary_points = points[boundary_indices]
                except Exception as e:
                    logger.debug(f"[meshconverter] Fehler: {e}")
                    boundary_points = points

            # Normalize normal
            normal = normal / (np.linalg.norm(normal) + 1e-10)

            # Create plane
            gp_origin = gp_Pnt(float(centroid[0]), float(centroid[1]), float(centroid[2]))
            gp_normal = gp_Dir(float(normal[0]), float(normal[1]), float(normal[2]))
            plane = gp_Pln(gp_origin, gp_normal)

            # Create boundary wire
            wire = self._create_wire(boundary_points)
            if wire is None:
                return None

            face_builder = BRepBuilderAPI_MakeFace(plane, wire)
            if face_builder.IsDone():
                return face_builder.Face()
            return None

        except Exception as e:
            logger.debug(f"Failed to create planar face: {e}")
            return None

    def _create_wire(self, points: np.ndarray) -> Optional['TopoDS_Wire']:
        """Create closed wire from ordered points."""
        if len(points) < 3:
            return None

        try:
            wire_builder = BRepBuilderAPI_MakeWire()
            precision = 2
            rounded_points = np.round(points, precision)

            for i in range(len(rounded_points)):
                p1 = rounded_points[i]
                p2 = rounded_points[(i + 1) % len(rounded_points)]

                if np.linalg.norm(p2 - p1) < 1e-6:
                    continue

                gp_p1 = gp_Pnt(float(p1[0]), float(p1[1]), float(p1[2]))
                gp_p2 = gp_Pnt(float(p2[0]), float(p2[1]), float(p2[2]))

                edge_builder = BRepBuilderAPI_MakeEdge(gp_p1, gp_p2)
                if edge_builder.IsDone():
                    wire_builder.Add(edge_builder.Edge())

            if wire_builder.IsDone():
                return wire_builder.Wire()
            return None

        except Exception as e:
            logger.debug(f"Failed to create wire: {e}")
            return None

    def _sew_faces(self, faces: List['TopoDS_Face']) -> ConversionResult:
        """Sew faces together into a solid."""
        try:
            sewer = BRepBuilderAPI_Sewing(self.sewing_tol)

            for face in faces:
                if face and not face.IsNull():
                    sewer.Add(face)

            sewer.Perform()
            sewed_shape = sewer.SewedShape()

            if sewed_shape.IsNull():
                return ConversionResult(
                    status=ConversionStatus.FAILED,
                    message="Sewing failed"
                )

            # Try to create solid from shell
            try:
                shell = TopoDS.Shell_s(sewed_shape)
                from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeSolid
                solid_builder = BRepBuilderAPI_MakeSolid(shell)

                if solid_builder.IsDone():
                    solid = solid_builder.Solid()

                    # Wrap in build123d Solid
                    if HAS_BUILD123D:
                        b123d_solid = Solid.cast(solid)
                        return ConversionResult(
                            status=ConversionStatus.SUCCESS,
                            solid=b123d_solid,
                            stats={'solid_created': True}
                        )
                    else:
                        return ConversionResult(
                            status=ConversionStatus.SUCCESS,
                            solid=solid,
                            stats={'solid_created': True}
                        )

            except Exception as e:
                logger.warning(f"Could not create solid: {e}")

            # Return shell if solid creation failed
            if HAS_BUILD123D:
                try:
                    shell = TopoDS.Shell_s(sewed_shape)
                    b123d_shell = Shell.cast(shell)
                    return ConversionResult(
                        status=ConversionStatus.SHELL_ONLY,
                        solid=b123d_shell,
                        message="Shell created, not watertight",
                        stats={'shell_created': True}
                    )
                except Exception as e:
                    logger.debug(f"[meshconverter] Fehler: {e}")
                    pass

            return ConversionResult(
                status=ConversionStatus.SHELL_ONLY,
                solid=sewed_shape,
                message="Shell created, not watertight"
            )

        except Exception as e:
            return ConversionResult(
                status=ConversionStatus.FAILED,
                message=f"Sewing error: {e}"
            )


def convert_with_fillets(filepath: str, **kwargs) -> ConversionResult:
    """Convenience function for fillet-aware conversion."""
    converter = FilletAwareConverter(**kwargs)
    return converter.convert(filepath)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python fillet_aware_converter.py <file.stl>")
        sys.exit(1)

    filepath = sys.argv[1]
    result = convert_with_fillets(filepath)

    print(f"\nResult: {result.status.name}")
    print(f"Message: {result.message}")
    print(f"Stats: {result.stats}")

    if result.solid and result.status in [ConversionStatus.SUCCESS, ConversionStatus.SHELL_ONLY]:
        output_path = Path(filepath).with_suffix('.step')
        try:
            # Try to export via build123d
            export_step(result.solid, str(output_path))
            print(f"Exported to: {output_path}")
        except Exception as e:
            # Fallback: export raw OCP shape
            try:
                from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
                from OCP.IFSelect import IFSelect_RetDone

                writer = STEPControl_Writer()
                writer.Transfer(result.solid, STEPControl_AsIs)
                status = writer.Write(str(output_path))
                if status == IFSelect_RetDone:
                    print(f"Exported to: {output_path}")
                else:
                    print(f"Export failed with status: {status}")
            except Exception as e2:
                print(f"Export failed: {e2}")
