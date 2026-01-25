"""
Cylinder Hole Replacer - Ersetzt triangulierte Zylinder-Löcher durch echte.

Strategie:
1. Erstelle wasserdichtes BREP aus Mesh (trianguliert)
2. Erkenne Zylinder-Löcher auf dem Original-Mesh
3. Für jedes Loch: Erstelle einen GRÖSSEREN Zylinder
4. Boolean-Subtraktion → saubere zylindrische Oberfläche

Warum das funktioniert:
- Boolean-Operationen erzeugen saubere Schnitt-Kanten
- Kein Edge-Mismatch weil neue Kanten entstehen
- Der größere Zylinder "schneidet" durch das triangulierte Mesh
"""

import numpy as np
from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass
from loguru import logger

try:
    from OCP.TopoDS import TopoDS, TopoDS_Shape, TopoDS_Solid, TopoDS_Compound
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_FACE, TopAbs_SOLID
    from OCP.gp import gp_Pnt, gp_Dir, gp_Ax2, gp_Vec
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
    from OCP.BRep import BRep_Builder
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.ShapeFix import ShapeFix_Shape
    HAS_OCP = True
except ImportError:
    HAS_OCP = False

try:
    import pyvista as pv
    HAS_PYVISTA = True
except ImportError:
    HAS_PYVISTA = False

from .mesh_primitive_detector import MeshPrimitiveDetector, CylinderFit
from .direct_mesh_converter import DirectMeshConverter
from .mesh_converter_v10 import ConversionResult, ConversionStatus


@dataclass
class HoleReplacementResult:
    """Ergebnis der Loch-Ersetzung."""
    solid: Optional[TopoDS_Shape]
    status: str
    stats: Dict
    cylinders_replaced: int = 0


class CylinderHoleReplacer:
    """
    Ersetzt triangulierte Zylinder-Löcher durch echte zylindrische Surfaces.

    Workflow:
    1. Mesh → BREP (trianguliert, wasserdicht)
    2. Erkenne Zylinder auf Mesh
    3. Für jedes Zylinder-LOCH:
       - Erstelle Zylinder mit margin_radius größer
       - Erstelle Zylinder mit margin_height länger (beidseitig)
       - Boolean-Cut vom Haupt-Body
    """

    def __init__(
        self,
        # Mesh Converter Einstellungen
        sewing_tolerance: float = 1e-6,
        unify_tolerance: float = 0.1,
        # Zylinder-Erkennung
        angle_threshold: float = 12.0,
        min_cylinder_faces: int = 20,
        cylinder_fit_tolerance: float = 0.3,
        min_inlier_ratio: float = 0.90,
        # Boolean-Einstellungen
        radius_margin: float = 0.01,    # mm - Zylinder wird größer
        height_margin: float = 1.0,     # mm - Zylinder wird länger (pro Seite)
        min_cylinder_radius: float = 0.5,  # mm - Minimum Radius für Ersetzung
        max_cylinder_radius: float = 50.0  # mm - Maximum Radius
    ):
        self.sewing_tol = sewing_tolerance
        self.unify_tol = unify_tolerance

        self.angle_thresh = angle_threshold
        self.min_cyl_faces = min_cylinder_faces
        self.cyl_fit_tol = cylinder_fit_tolerance
        self.min_inlier = min_inlier_ratio

        self.radius_margin = radius_margin
        self.height_margin = height_margin
        self.min_radius = min_cylinder_radius
        self.max_radius = max_cylinder_radius

    def convert(self, mesh: 'pv.PolyData') -> HoleReplacementResult:
        """
        Konvertiert Mesh zu BREP mit echten Zylinder-Löchern.
        """
        if not HAS_OCP or not HAS_PYVISTA:
            return HoleReplacementResult(None, "FAILED", {"error": "Dependencies missing"})

        stats = {
            'mesh_faces': mesh.n_cells,
            'cylinders_detected': 0,
            'holes_detected': 0,
            'holes_replaced': 0,
            'brep_faces_before': 0,
            'brep_faces_after': 0
        }

        logger.info("=== Cylinder Hole Replacer ===")
        logger.info(f"Mesh: {mesh.n_points} Punkte, {mesh.n_cells} Faces")

        # 1. Erkenne Zylinder auf dem Mesh
        logger.info("Schritt 1: Erkenne Zylinder auf Mesh...")
        detector = MeshPrimitiveDetector(
            angle_threshold=self.angle_thresh,
            min_region_faces=self.min_cyl_faces,
            cylinder_tolerance=self.cyl_fit_tol,
            min_inlier_ratio=self.min_inlier
        )

        cylinders, spheres = detector.detect_from_mesh(mesh)
        stats['cylinders_detected'] = len(cylinders)
        logger.info(f"  {len(cylinders)} Zylinder gefunden")

        # 2. Filtere nach Löchern und Größe
        faces = mesh.faces.reshape(-1, 4)[:, 1:4]
        points = mesh.points

        hole_cylinders = []
        for cyl in cylinders:
            # Prüfe Größe
            if cyl.radius < self.min_radius or cyl.radius > self.max_radius:
                logger.debug(f"    Überspringe R={cyl.radius:.2f}mm (außerhalb Bereich)")
                continue

            # Prüfe ob Loch (Normalen zeigen nach innen)
            is_hole = self._is_cylinder_hole(cyl, faces, points)

            if is_hole:
                hole_cylinders.append(cyl)
                logger.info(f"    LOCH: R={cyl.radius:.2f}mm, H={cyl.height:.2f}mm")
            else:
                logger.debug(f"    Boss (kein Loch): R={cyl.radius:.2f}mm")

        stats['holes_detected'] = len(hole_cylinders)
        logger.info(f"  {len(hole_cylinders)} Zylinder-Löcher erkannt")

        # 3. Konvertiere Mesh zu BREP
        logger.info("Schritt 2: Konvertiere Mesh zu BREP...")
        converter = DirectMeshConverter(
            sewing_tolerance=self.sewing_tol,
            unify_faces=True,
            unify_linear_tolerance=self.unify_tol,
            unify_angular_tolerance=0.5
        )

        base_result = converter.convert(mesh)

        if base_result.status != ConversionStatus.SUCCESS or base_result.solid is None:
            logger.error("Basis-Konvertierung fehlgeschlagen")
            return HoleReplacementResult(None, "BASE_CONVERSION_FAILED", stats)

        base_solid = base_result.solid
        stats['brep_faces_before'] = self._count_faces(base_solid)
        logger.info(f"  Basis-BREP: {stats['brep_faces_before']} Faces")

        # 4. Boolean-Cut für jedes Loch
        if hole_cylinders:
            logger.info("Schritt 3: Ersetze Löcher durch Boolean-Cut...")
            result_solid, replaced_count = self._replace_holes_boolean(base_solid, hole_cylinders)

            stats['holes_replaced'] = replaced_count
            stats['brep_faces_after'] = self._count_faces(result_solid)

            if replaced_count > 0:
                logger.success(f"  {replaced_count}/{len(hole_cylinders)} Löcher ersetzt")
                logger.info(f"  Faces: {stats['brep_faces_before']} → {stats['brep_faces_after']}")

                return HoleReplacementResult(
                    result_solid,
                    "SUCCESS",
                    stats,
                    cylinders_replaced=replaced_count
                )
            else:
                logger.warning("Keine Löcher ersetzt, verwende Basis")

        stats['brep_faces_after'] = stats['brep_faces_before']
        return HoleReplacementResult(base_solid, "SUCCESS_NO_REPLACEMENT", stats, 0)

    def _is_cylinder_hole(
        self,
        cyl: CylinderFit,
        faces: np.ndarray,
        points: np.ndarray
    ) -> bool:
        """
        Bestimmt ob ein Zylinder ein Loch ist.

        Loch: Normalen zeigen zum Zylinder-Zentrum (inward)
        Boss: Normalen zeigen vom Zentrum weg (outward)
        """
        inward_count = 0
        outward_count = 0

        for f_idx in cyl.face_indices:
            v0, v1, v2 = faces[f_idx]
            p0, p1, p2 = points[v0], points[v1], points[v2]

            # Face-Normal
            e1 = p1 - p0
            e2 = p2 - p0
            normal = np.cross(e1, e2)
            norm_len = np.linalg.norm(normal)
            if norm_len < 1e-10:
                continue
            normal = normal / norm_len

            # Face-Zentroid
            centroid = (p0 + p1 + p2) / 3

            # Radiale Richtung (vom Zylinder-Achse zum Punkt)
            to_centroid = centroid - cyl.center
            # Entferne Komponente entlang der Achse
            proj_on_axis = np.dot(to_centroid, cyl.axis) * cyl.axis
            radial = to_centroid - proj_on_axis
            radial_len = np.linalg.norm(radial)
            if radial_len < 1e-10:
                continue
            radial = radial / radial_len

            # Prüfe ob Normal nach außen (wie radial) oder innen zeigt
            dot = np.dot(normal, radial)

            if dot > 0.1:  # Normal zeigt nach außen → Boss
                outward_count += 1
            elif dot < -0.1:  # Normal zeigt nach innen → Loch
                inward_count += 1

        # Mehrheitsentscheidung
        return inward_count > outward_count

    def _replace_holes_boolean(
        self,
        base_solid: TopoDS_Shape,
        hole_cylinders: List[CylinderFit]
    ) -> Tuple[Optional[TopoDS_Shape], int]:
        """
        Ersetzt triangulierte Löcher durch Boolean-Cut mit echten Zylindern.

        Returns:
            Tuple von (result_shape, anzahl_erfolgreich_ersetzt)
        """
        result = base_solid
        successful_count = 0

        for i, cyl in enumerate(hole_cylinders):
            logger.info(f"    Boolean-Cut {i+1}/{len(hole_cylinders)}: R={cyl.radius:.2f}mm")

            try:
                # Erstelle Zylinder mit Margin
                cut_cylinder = self._create_cutting_cylinder(cyl)

                if cut_cylinder is None:
                    logger.warning(f"      Zylinder-Erstellung fehlgeschlagen")
                    continue

                # Boolean-Cut
                cut_op = BRepAlgoAPI_Cut(result, cut_cylinder)
                cut_op.Build()

                if not cut_op.IsDone():
                    logger.warning(f"      Boolean-Cut fehlgeschlagen")
                    continue

                cut_result = cut_op.Shape()

                if cut_result.IsNull():
                    logger.warning(f"      Ergebnis ist Null")
                    continue

                # Validiere Ergebnis
                analyzer = BRepCheck_Analyzer(cut_result)
                if not analyzer.IsValid():
                    logger.warning(f"      Ergebnis nicht valide, versuche Reparatur...")
                    fixer = ShapeFix_Shape(cut_result)
                    fixer.Perform()
                    cut_result = fixer.Shape()

                    analyzer2 = BRepCheck_Analyzer(cut_result)
                    if not analyzer2.IsValid():
                        logger.warning(f"      Reparatur fehlgeschlagen, überspringe")
                        continue

                result = cut_result
                successful_count += 1
                logger.success(f"      Loch {i+1} erfolgreich ersetzt")

            except Exception as e:
                logger.warning(f"      Exception: {e}")
                continue

        return result, successful_count

    def _create_cutting_cylinder(self, cyl: CylinderFit) -> Optional[TopoDS_Solid]:
        """
        Erstellt einen Schnitt-Zylinder (größer als das erkannte Loch).
        """
        try:
            # Radius mit Margin (etwas größer)
            radius = float(cyl.radius + self.radius_margin)

            # Höhe mit Margin (beidseitig verlängern)
            height = float(cyl.height + 2 * self.height_margin)

            # Validiere
            if radius <= 0 or height <= 0:
                logger.warning(f"      Ungültige Maße: R={radius}, H={height}")
                return None

            # Normalisiere Achse
            axis = np.array(cyl.axis, dtype=float)
            axis_len = np.linalg.norm(axis)
            if axis_len < 1e-10:
                logger.warning(f"      Achse hat Länge 0")
                return None
            axis = axis / axis_len

            # Basis-Punkt (unterhalb des erkannten Zylinders)
            center = np.array(cyl.center, dtype=float)
            base_point = center - axis * (cyl.height / 2 + self.height_margin)

            logger.debug(f"      Zyl-Params: R={radius:.3f}, H={height:.3f}")
            logger.debug(f"      Base: [{base_point[0]:.2f}, {base_point[1]:.2f}, {base_point[2]:.2f}]")
            logger.debug(f"      Axis: [{axis[0]:.3f}, {axis[1]:.3f}, {axis[2]:.3f}]")

            # OCP Objekte
            gp_base = gp_Pnt(base_point[0], base_point[1], base_point[2])
            gp_axis = gp_Dir(axis[0], axis[1], axis[2])

            ax2 = gp_Ax2(gp_base, gp_axis)

            # Erstelle Zylinder
            cylinder_maker = BRepPrimAPI_MakeCylinder(ax2, radius, height)
            cylinder_maker.Build()

            if cylinder_maker.IsDone():
                solid = cylinder_maker.Solid()
                if solid is not None and not solid.IsNull():
                    logger.info(f"      Zylinder erstellt OK")
                    return solid
                else:
                    logger.warning(f"      Solid ist Null nach IsDone")
                    return None

            logger.warning(f"      MakeCylinder nicht IsDone")
            return None

        except Exception as e:
            logger.warning(f"      Zylinder-Exception: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _count_faces(self, shape: TopoDS_Shape) -> int:
        """Zählt Faces in einem Shape."""
        count = 0
        exp = TopExp_Explorer(shape, TopAbs_FACE)
        while exp.More():
            count += 1
            exp.Next()
        return count


def convert_with_cylinder_holes(filepath: str, **kwargs) -> HoleReplacementResult:
    """
    Convenience-Funktion für Konvertierung mit Zylinder-Loch-Ersetzung.
    """
    from .mesh_converter_v10 import MeshLoader

    load_result = MeshLoader.load(filepath, repair=True)
    if load_result.mesh is None:
        return HoleReplacementResult(None, "LOAD_FAILED", {})

    replacer = CylinderHoleReplacer(**kwargs)
    return replacer.convert(load_result.mesh)
