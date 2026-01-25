"""
Smart Mesh Converter - Ersetzt erkannte Primitive durch analytische Flächen.

Workflow:
1. Erkenne Zylinder/Kugeln auf dem Mesh
2. Erstelle analytische Surfaces für erkannte Primitive
3. Erstelle planare Faces für den Rest
4. Sew alles zusammen
"""

import numpy as np
from typing import List, Tuple, Optional, Dict, Set
from dataclasses import dataclass
from loguru import logger

try:
    from OCP.TopoDS import TopoDS, TopoDS_Face, TopoDS_Solid, TopoDS_Shell, TopoDS_Compound
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_FACE
    from OCP.BRep import BRep_Builder
    from OCP.gp import gp_Pnt, gp_Vec, gp_Dir, gp_Ax3, gp_Pln
    from OCP.Geom import Geom_CylindricalSurface, Geom_SphericalSurface, Geom_Plane
    from OCP.BRepBuilderAPI import (
        BRepBuilderAPI_MakeFace, BRepBuilderAPI_Sewing, BRepBuilderAPI_MakeSolid,
        BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire
    )
    from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
    from OCP.ShapeFix import ShapeFix_Solid
    HAS_OCP = True
except ImportError:
    HAS_OCP = False

try:
    import pyvista as pv
    HAS_PYVISTA = True
except ImportError:
    HAS_PYVISTA = False

from .mesh_primitive_detector import MeshPrimitiveDetector, CylinderFit, SphereFit


@dataclass
class ConversionResult:
    """Ergebnis der Konvertierung."""
    solid: Optional['TopoDS_Solid']
    status: str
    stats: Dict


class SmartMeshConverter:
    """
    Konvertiert Mesh zu BREP mit intelligenter Primitiv-Erkennung.

    Unterschied zum DirectMeshConverter:
    - Erkennt Zylinder/Kugeln VOR der Konvertierung
    - Ersetzt diese durch echte analytische Surfaces
    - Reduziert Face-Anzahl drastisch
    """

    def __init__(
        self,
        angle_threshold: float = 12.0,
        min_primitive_faces: int = 12,
        cylinder_tolerance: float = 0.5,
        sphere_tolerance: float = 0.5,
        sewing_tolerance: float = 0.1
    ):
        self.angle_thresh = angle_threshold
        self.min_prim_faces = min_primitive_faces
        self.cyl_tol = cylinder_tolerance
        self.sphere_tol = sphere_tolerance
        self.sew_tol = sewing_tolerance

        self.detector = MeshPrimitiveDetector(
            angle_threshold=angle_threshold,
            min_region_faces=min_primitive_faces,
            cylinder_tolerance=cylinder_tolerance,
            sphere_tolerance=sphere_tolerance
        )

    def convert(self, mesh: 'pv.PolyData', replace_primitives: bool = False) -> ConversionResult:
        """
        Konvertiert PyVista Mesh zu BREP mit Primitiv-Erkennung.

        Args:
            mesh: PyVista Mesh
            replace_primitives: Wenn True, werden erkannte Primitive durch
                               analytische Surfaces ersetzt. ACHTUNG: Dies kann
                               zu Lücken im Modell führen wenn die Kanten nicht
                               übereinstimmen. Standard ist False.
        """
        if not HAS_OCP or not HAS_PYVISTA:
            return ConversionResult(None, "FAILED", {"error": "Missing dependencies"})

        stats = {
            'mesh_faces': mesh.n_cells,
            'cylinders_detected': 0,
            'spheres_detected': 0,
            'cylinder_faces_replaced': 0,
            'sphere_faces_replaced': 0,
            'triangular_faces': 0,
            'brep_faces': 0
        }

        logger.info("=== Smart Mesh Converter ===")
        logger.info(f"Mesh: {mesh.n_points} Punkte, {mesh.n_cells} Faces")

        # 1. Erkenne Primitive (nur für Info/Statistik)
        logger.info("Erkenne Primitive...")
        cylinders, spheres = self.detector.detect_from_mesh(mesh)
        stats['cylinders_detected'] = len(cylinders)
        stats['spheres_detected'] = len(spheres)
        logger.info(f"  Gefunden: {len(cylinders)} Zylinder, {len(spheres)} Kugeln")

        # 2. Erstelle BREP Faces
        faces = mesh.faces.reshape(-1, 4)[:, 1:4]
        points = mesh.points

        brep_faces = []
        primitive_faces = set()

        if replace_primitives:
            # EXPERIMENTELL: Ersetze Primitive durch analytische Surfaces
            # ACHTUNG: Kann Lücken verursachen!
            logger.warning("EXPERIMENTELL: Ersetze Primitive (kann Lücken verursachen)")

            for cyl in cylinders:
                primitive_faces.update(cyl.face_indices)
                stats['cylinder_faces_replaced'] += len(cyl.face_indices)
            for sph in spheres:
                primitive_faces.update(sph.face_indices)
                stats['sphere_faces_replaced'] += len(sph.face_indices)

            logger.info(f"  {len(primitive_faces)} Mesh-Faces werden durch Primitive ersetzt")

            # Erstelle Zylinder-Faces
            logger.info("Erstelle Zylinder-Faces...")
            for cyl in cylinders:
                cyl_face = self._create_cylinder_face(cyl, faces, points)
                if cyl_face is not None:
                    brep_faces.append(cyl_face)
                    logger.info(f"    Zylinder R={cyl.radius:.2f}mm erstellt")
                else:
                    logger.warning(f"    Zylinder R={cyl.radius:.2f}mm fehlgeschlagen, nutze Triangles")
                    for f_idx in cyl.face_indices:
                        tri_face = self._create_triangle_face(faces[f_idx], points)
                        if tri_face is not None:
                            brep_faces.append(tri_face)
                    primitive_faces -= set(cyl.face_indices)

            # Erstelle Kugel-Faces
            logger.info("Erstelle Kugel-Faces...")
            for sph in spheres:
                sph_face = self._create_sphere_face(sph, faces, points)
                if sph_face is not None:
                    brep_faces.append(sph_face)
                    logger.info(f"    Kugel R={sph.radius:.2f}mm erstellt")
                else:
                    logger.warning(f"    Kugel R={sph.radius:.2f}mm fehlgeschlagen, nutze Triangles")
                    for f_idx in sph.face_indices:
                        tri_face = self._create_triangle_face(faces[f_idx], points)
                        if tri_face is not None:
                            brep_faces.append(tri_face)
                    primitive_faces -= set(sph.face_indices)
        else:
            # Standard-Modus: Nur Info über Primitive, aber keine Ersetzung
            logger.info("  Primitive werden NICHT ersetzt (nur triangulierte Faces)")
            logger.info("  UnifySameDomain wird für Optimierung verwendet")

        # 3. Erstelle triangulierte Faces für alle (oder nur nicht-primitive)
        logger.info("Erstelle triangulierte Faces...")
        triangular_count = 0
        for f_idx in range(len(faces)):
            if f_idx in primitive_faces:
                continue  # Bereits durch Primitiv ersetzt

            tri_face = self._create_triangle_face(faces[f_idx], points)
            if tri_face is not None:
                brep_faces.append(tri_face)
                triangular_count += 1

        stats['triangular_faces'] = triangular_count
        logger.info(f"  {triangular_count} triangulierte Faces erstellt")

        # 4. Sewing
        logger.info(f"Sewing {len(brep_faces)} Faces...")
        sewer = BRepBuilderAPI_Sewing(self.sew_tol)
        for face in brep_faces:
            sewer.Add(face)

        sewer.Perform()
        sewed = sewer.SewedShape()

        if sewed.IsNull():
            return ConversionResult(None, "SEWING_FAILED", stats)

        # 5. Solid erstellen
        logger.info("Erstelle Solid...")
        result_shape = self._create_solid(sewed)

        if result_shape is None:
            return ConversionResult(None, "SOLID_FAILED", stats)

        # 6. UnifySameDomain für Optimierung
        # Bei trianguliertem Mesh: Aggressivere Toleranzen um Zylinder/Kugeln zu erkennen
        logger.info("Optimiere mit UnifySameDomain...")
        try:
            # Erste Runde: Konservative Toleranzen
            upgrader = ShapeUpgrade_UnifySameDomain(result_shape, True, True, True)
            upgrader.SetLinearTolerance(0.1)  # 0.1mm - erkennt leichte Abweichungen
            upgrader.SetAngularTolerance(np.radians(1.0))  # 1° - für planare Faces
            upgrader.Build()
            optimized = upgrader.Shape()

            if not optimized.IsNull():
                result_shape = optimized

                # Zweite Runde mit noch lockereren Toleranzen falls noch viele Faces
                face_count_temp = 0
                exp = TopExp_Explorer(result_shape, TopAbs_FACE)
                while exp.More():
                    face_count_temp += 1
                    exp.Next()

                if face_count_temp > 500:
                    logger.info(f"  Zweite UnifySameDomain Runde ({face_count_temp} Faces)...")
                    upgrader2 = ShapeUpgrade_UnifySameDomain(result_shape, True, True, True)
                    upgrader2.SetLinearTolerance(0.5)  # Lockerer
                    upgrader2.SetAngularTolerance(np.radians(2.0))
                    upgrader2.Build()
                    optimized2 = upgrader2.Shape()

                    if not optimized2.IsNull():
                        result_shape = optimized2

        except Exception as e:
            logger.warning(f"UnifySameDomain fehlgeschlagen: {e}")

        # Zähle finale Faces
        face_count = 0
        exp = TopExp_Explorer(result_shape, TopAbs_FACE)
        while exp.More():
            face_count += 1
            exp.Next()

        stats['brep_faces'] = face_count
        logger.success(f"Konvertierung erfolgreich: {face_count} BREP Faces")

        return ConversionResult(result_shape, "SUCCESS", stats)

    def _create_cylinder_face(
        self,
        cyl: CylinderFit,
        faces: np.ndarray,
        points: np.ndarray
    ) -> Optional[TopoDS_Face]:
        """
        Erstellt eine zylindrische Face aus CylinderFit.

        Verwendet kreisförmige Boundary-Wires für besseres Sewing.
        """
        try:
            from OCP.GC import GC_MakeCircle
            from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire

            center = cyl.center
            axis = cyl.axis
            radius = cyl.radius

            # Sammle alle Boundary-Punkte
            boundary_points = []
            for f_idx in cyl.face_indices:
                for v_idx in faces[f_idx]:
                    boundary_points.append(points[v_idx])

            boundary_points = np.array(boundary_points)
            boundary_points = np.unique(np.round(boundary_points, decimals=5), axis=0)

            if len(boundary_points) < 3:
                return None

            # Berechne V Bounds (Projektion auf Achse)
            to_center = boundary_points - center
            proj = np.dot(to_center, axis)
            v_min_rel, v_max_rel = proj.min(), proj.max()

            # Basis des Zylinders am unteren Ende
            base_point = center + axis * v_min_rel
            top_point = center + axis * v_max_rel
            height = v_max_rel - v_min_rel

            if height < 0.1:
                return None

            # Lokale X/Y Achsen
            z_axis = axis
            if abs(z_axis[2]) < 0.9:
                x_axis = np.cross(z_axis, [0, 0, 1])
            else:
                x_axis = np.cross(z_axis, [1, 0, 0])
            x_axis = x_axis / np.linalg.norm(x_axis)

            # Erstelle OCP Objekte
            gp_base = gp_Pnt(float(base_point[0]), float(base_point[1]), float(base_point[2]))
            gp_top = gp_Pnt(float(top_point[0]), float(top_point[1]), float(top_point[2]))
            gp_axis = gp_Dir(float(axis[0]), float(axis[1]), float(axis[2]))
            gp_xdir = gp_Dir(float(x_axis[0]), float(x_axis[1]), float(x_axis[2]))

            # Erstelle Zylinder-Surface
            ax3 = gp_Ax3(gp_base, gp_axis, gp_xdir)
            cylinder_surface = Geom_CylindricalSurface(ax3, float(radius))

            # Erstelle kreisförmige Boundary-Kanten (oben und unten)
            from OCP.gp import gp_Ax2, gp_Circ
            from OCP.Geom import Geom_Circle

            # Unterer Kreis
            ax2_bottom = gp_Ax2(gp_base, gp_axis)
            circle_bottom = gp_Circ(ax2_bottom, float(radius))
            edge_bottom = BRepBuilderAPI_MakeEdge(circle_bottom).Edge()

            # Oberer Kreis
            ax2_top = gp_Ax2(gp_top, gp_axis)
            circle_top = gp_Circ(ax2_top, float(radius))
            edge_top = BRepBuilderAPI_MakeEdge(circle_top).Edge()

            # Erstelle Wires
            wire_bottom = BRepBuilderAPI_MakeWire(edge_bottom).Wire()
            wire_top = BRepBuilderAPI_MakeWire(edge_top).Wire()

            # Erstelle Face mit den Wires als Boundaries
            # Erst die Surface, dann trimmen mit Wires
            face_builder = BRepBuilderAPI_MakeFace(
                cylinder_surface,
                0.0, 2 * np.pi,  # Vollständiger Umfang
                0.0, float(height),
                1e-6
            )

            if face_builder.IsDone():
                logger.debug(f"    Zylinder-Face erstellt: R={radius:.2f}mm, H={height:.2f}mm")
                return face_builder.Face()

            logger.warning(f"    MakeFace fehlgeschlagen")
            return None

        except Exception as e:
            logger.debug(f"Zylinder-Face Erstellung fehlgeschlagen: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _create_sphere_face(
        self,
        sph: SphereFit,
        faces: np.ndarray,
        points: np.ndarray
    ) -> Optional[TopoDS_Face]:
        """Erstellt eine sphärische Face aus SphereFit."""
        try:
            center = sph.center
            radius = sph.radius

            # Sammle alle Boundary-Punkte
            boundary_points = []
            for f_idx in sph.face_indices:
                for v_idx in faces[f_idx]:
                    boundary_points.append(points[v_idx])

            boundary_points = np.array(boundary_points)
            boundary_points = np.unique(np.round(boundary_points, decimals=5), axis=0)

            if len(boundary_points) < 3:
                return None

            # Berechne sphärische Koordinaten für Bounds
            to_center = boundary_points - center
            distances = np.linalg.norm(to_center, axis=1)
            normalized = to_center / (distances[:, np.newaxis] + 1e-10)

            # Theta (azimuth) und Phi (polar)
            theta = np.arctan2(normalized[:, 1], normalized[:, 0])
            phi = np.arccos(np.clip(normalized[:, 2], -1, 1))

            # U/V Bounds für Kugel
            # U = theta (-pi bis pi), V = phi (0 bis pi)
            u_min, u_max = theta.min(), theta.max()
            v_min, v_max = phi.min(), phi.max()

            # Prüfe ob fast vollständige Kugel
            if (u_max - u_min) > 1.8 * np.pi:
                u_min = -np.pi
                u_max = np.pi

            # Erstelle OCP Kugel
            gp_center = gp_Pnt(float(center[0]), float(center[1]), float(center[2]))
            ax3 = gp_Ax3(gp_center, gp_Dir(0, 0, 1), gp_Dir(1, 0, 0))
            sphere_surface = Geom_SphericalSurface(ax3, float(radius))

            # Margin
            margin = 0.02

            face_builder = BRepBuilderAPI_MakeFace(
                sphere_surface,
                float(u_min - margin), float(u_max + margin),
                float(v_min - margin), float(v_max + margin),
                1e-6
            )

            if face_builder.IsDone():
                return face_builder.Face()

            return None

        except Exception as e:
            logger.debug(f"Kugel-Face Erstellung fehlgeschlagen: {e}")
            return None

    def _create_triangle_face(
        self,
        face_vertices: np.ndarray,
        points: np.ndarray
    ) -> Optional[TopoDS_Face]:
        """Erstellt eine planare Face aus Dreieck."""
        try:
            v0, v1, v2 = face_vertices
            p0 = points[v0]
            p1 = points[v1]
            p2 = points[v2]

            # Prüfe auf degeneriertes Dreieck
            e1 = p1 - p0
            e2 = p2 - p0
            normal = np.cross(e1, e2)
            area = np.linalg.norm(normal)

            if area < 1e-10:
                return None

            normal = normal / area

            # Erstelle Wire
            gp0 = gp_Pnt(float(p0[0]), float(p0[1]), float(p0[2]))
            gp1 = gp_Pnt(float(p1[0]), float(p1[1]), float(p1[2]))
            gp2 = gp_Pnt(float(p2[0]), float(p2[1]), float(p2[2]))

            edge1 = BRepBuilderAPI_MakeEdge(gp0, gp1).Edge()
            edge2 = BRepBuilderAPI_MakeEdge(gp1, gp2).Edge()
            edge3 = BRepBuilderAPI_MakeEdge(gp2, gp0).Edge()

            wire_builder = BRepBuilderAPI_MakeWire()
            wire_builder.Add(edge1)
            wire_builder.Add(edge2)
            wire_builder.Add(edge3)

            if not wire_builder.IsDone():
                return None

            wire = wire_builder.Wire()

            # Erstelle Face
            face_builder = BRepBuilderAPI_MakeFace(wire, True)

            if face_builder.IsDone():
                return face_builder.Face()

            return None

        except Exception:
            return None

    def _create_solid(self, sewed_shape) -> Optional['TopoDS_Solid']:
        """Erstellt Solid aus gesewter Shape."""
        try:
            from OCP.TopAbs import TopAbs_SHELL, TopAbs_SOLID, TopAbs_COMPOUND

            shape_type = sewed_shape.ShapeType()

            if shape_type == TopAbs_SOLID:
                return TopoDS.Solid_s(sewed_shape)

            if shape_type == TopAbs_SHELL:
                shell = TopoDS.Shell_s(sewed_shape)
                solid_builder = BRepBuilderAPI_MakeSolid(shell)

                if solid_builder.IsDone():
                    return solid_builder.Solid()

                # Versuche ShapeFix
                fixer = ShapeFix_Solid()
                fixer.Init(shell)
                fixer.Perform()

                if not fixer.Solid().IsNull():
                    return fixer.Solid()

            if shape_type == TopAbs_COMPOUND:
                # Bei Compound: Versuche jede Shell einzeln
                builder = BRep_Builder()
                compound = TopoDS_Compound()
                builder.MakeCompound(compound)

                exp = TopExp_Explorer(sewed_shape, TopAbs_SHELL)
                while exp.More():
                    shell = TopoDS.Shell_s(exp.Current())
                    solid_builder = BRepBuilderAPI_MakeSolid(shell)

                    if solid_builder.IsDone():
                        builder.Add(compound, solid_builder.Solid())
                    else:
                        builder.Add(compound, shell)

                    exp.Next()

                return compound

            return sewed_shape

        except Exception as e:
            logger.warning(f"Solid-Erstellung fehlgeschlagen: {e}")
            return None
