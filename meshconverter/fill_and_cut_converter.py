"""
Fill-and-Cut Converter - Füllt Löcher und schneidet sie neu.

Strategie für saubere zylindrische Löcher:
1. Konvertiere Mesh zu BREP (trianguliert, mit triangulierten Löchern)
2. Erkenne Zylinder-Löcher auf dem Mesh
3. Für jedes Loch:
   a. Erstelle Zylinder-Solid das Loch FÜLLT (Boolean FUSE)
   b. Erstelle Zylinder-Solid zum SCHNEIDEN (Boolean CUT)
   → Ergebnis: Saubere zylindrische Oberfläche

Warum das funktioniert:
- Boolean FUSE füllt das triangulierte Loch
- Boolean CUT erzeugt saubere analytische Zylinder-Kanten
"""

import numpy as np
from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass
from loguru import logger

try:
    from OCP.TopoDS import TopoDS, TopoDS_Shape, TopoDS_Solid, TopoDS_Compound, TopoDS_Shell
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_FACE, TopAbs_SOLID, TopAbs_SHELL, TopAbs_COMPOUND
    from OCP.gp import gp_Pnt, gp_Dir, gp_Ax2
    from OCP.BRep import BRep_Builder
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.ShapeFix import ShapeFix_Shape
    from OCP.BRepBndLib import BRepBndLib
    from OCP.Bnd import Bnd_Box
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
class FillCutResult:
    """Ergebnis der Fill-and-Cut Konvertierung."""
    solid: Optional[TopoDS_Shape]
    status: str
    stats: Dict


class FillAndCutConverter:
    """
    Konvertiert Mesh zu BREP mit sauberen Zylinder-Löchern.

    Der Trick: Erst füllen (FUSE), dann schneiden (CUT).
    """

    def __init__(
        self,
        # Zylinder-Erkennung
        angle_threshold: float = 12.0,
        min_cylinder_faces: int = 20,
        cylinder_fit_tolerance: float = 0.3,
        min_inlier_ratio: float = 0.88,
        # Größen-Filter
        min_cylinder_radius: float = 1.0,
        max_cylinder_radius: float = 20.0,
        # Fill-Cut Einstellungen
        fill_margin: float = 0.1,   # mm - Füll-Zylinder größer
        cut_margin: float = 0.0,    # mm - Schnitt-Zylinder exakt
        height_extension: float = 2.0  # mm - Zylinder verlängern
    ):
        self.angle_thresh = angle_threshold
        self.min_cyl_faces = min_cylinder_faces
        self.cyl_fit_tol = cylinder_fit_tolerance
        self.min_inlier = min_inlier_ratio
        self.min_radius = min_cylinder_radius
        self.max_radius = max_cylinder_radius
        self.fill_margin = fill_margin
        self.cut_margin = cut_margin
        self.height_ext = height_extension

    def convert(self, mesh: 'pv.PolyData') -> FillCutResult:
        """Konvertiert Mesh mit Fill-and-Cut für Zylinder-Löcher."""
        if not HAS_OCP or not HAS_PYVISTA:
            return FillCutResult(None, "FAILED", {"error": "Dependencies missing"})

        stats = {
            'mesh_faces': mesh.n_cells,
            'cylinders_detected': 0,
            'holes_detected': 0,
            'holes_processed': 0,
            'brep_faces_final': 0
        }

        logger.info("=== Fill-and-Cut Converter ===")
        logger.info(f"Mesh: {mesh.n_points} Punkte, {mesh.n_cells} Faces")

        # 1. Erkenne Zylinder
        logger.info("Schritt 1: Erkenne Zylinder-Löcher...")
        detector = MeshPrimitiveDetector(
            angle_threshold=self.angle_thresh,
            min_region_faces=self.min_cyl_faces,
            cylinder_tolerance=self.cyl_fit_tol,
            min_inlier_ratio=self.min_inlier
        )

        cylinders, _ = detector.detect_from_mesh(mesh)
        stats['cylinders_detected'] = len(cylinders)

        # Filtere nach Löchern
        faces = mesh.faces.reshape(-1, 4)[:, 1:4]
        points = mesh.points

        hole_cylinders = []
        for cyl in cylinders:
            if cyl.radius < self.min_radius or cyl.radius > self.max_radius:
                continue
            if self._is_hole(cyl, faces, points):
                hole_cylinders.append(cyl)
                logger.info(f"    Loch: R={cyl.radius:.2f}mm, H={cyl.height:.2f}mm")

        stats['holes_detected'] = len(hole_cylinders)
        logger.info(f"  {len(hole_cylinders)} Zylinder-Löcher erkannt")

        # 2. Konvertiere Mesh zu BREP
        logger.info("Schritt 2: Konvertiere Mesh zu BREP...")
        converter = DirectMeshConverter(
            sewing_tolerance=1e-6,
            unify_faces=True,
            unify_linear_tolerance=0.1,
            unify_angular_tolerance=0.5
        )

        base_result = converter.convert(mesh)
        if base_result.status != ConversionStatus.SUCCESS or base_result.solid is None:
            return FillCutResult(None, "BASE_FAILED", stats)

        result_solid = base_result.solid

        # Prüfe ob Compound (mehrere Solids)
        is_compound = result_solid.ShapeType() == TopAbs_COMPOUND

        # 3. Fill-and-Cut für jedes Loch (nur für einzelne Solids)
        if hole_cylinders:
            if is_compound:
                logger.warning("Schritt 3: ÜBERSPRUNGEN - Compound (mehrere Solids)")
                logger.warning("  Fill-and-Cut funktioniert nur für einzelne Solids")
                logger.info("  Verwende triangulierte Basis-BREP")
            else:
                logger.info("Schritt 3: Fill-and-Cut für Löcher...")

                for i, cyl in enumerate(hole_cylinders):
                    logger.info(f"    Loch {i+1}/{len(hole_cylinders)}: R={cyl.radius:.2f}mm")

                    # Prüfe dass Zylinder innerhalb des Solids liegt
                    if not self._cylinder_intersects_solid(result_solid, cyl):
                        logger.warning(f"      Zylinder außerhalb Solid, überspringe")
                        continue

                    processed = self._process_hole(result_solid, cyl)
                    if processed is not None:
                        # Validiere dass Ergebnis noch genug Faces hat
                        new_count = self._count_faces(processed)
                        old_count = self._count_faces(result_solid)

                        if new_count < old_count * 0.5:  # Mehr als 50% verloren
                            logger.warning(f"      Zu viele Faces verloren ({old_count} → {new_count}), überspringe")
                            continue

                        result_solid = processed
                        stats['holes_processed'] += 1
                        logger.success(f"      OK ({new_count} Faces)")
                    else:
                        logger.warning(f"      Fehlgeschlagen")

        # Zähle finale Faces
        stats['brep_faces_final'] = self._count_faces(result_solid)
        logger.success(f"Fertig: {stats['brep_faces_final']} Faces, {stats['holes_processed']} Löcher verarbeitet")

        return FillCutResult(result_solid, "SUCCESS", stats)

    def _is_hole(self, cyl: CylinderFit, faces: np.ndarray, points: np.ndarray) -> bool:
        """Bestimmt ob Zylinder ein Loch ist (Normalen nach innen)."""
        inward = 0
        outward = 0

        for f_idx in cyl.face_indices:
            v0, v1, v2 = faces[f_idx]
            p0, p1, p2 = points[v0], points[v1], points[v2]

            # Normal
            e1 = p1 - p0
            e2 = p2 - p0
            normal = np.cross(e1, e2)
            n_len = np.linalg.norm(normal)
            if n_len < 1e-10:
                continue
            normal /= n_len

            # Radiale Richtung
            centroid = (p0 + p1 + p2) / 3
            to_center = centroid - cyl.center
            proj = np.dot(to_center, cyl.axis) * cyl.axis
            radial = to_center - proj
            r_len = np.linalg.norm(radial)
            if r_len < 1e-10:
                continue
            radial /= r_len

            dot = np.dot(normal, radial)
            if dot > 0.1:
                outward += 1
            elif dot < -0.1:
                inward += 1

        return inward > outward

    def _process_hole(self, solid: TopoDS_Shape, cyl: CylinderFit) -> Optional[TopoDS_Shape]:
        """Verarbeitet ein Loch: Füllen, dann Schneiden."""
        try:
            # Normalisiere Achse
            axis = np.array(cyl.axis, dtype=float)
            axis_len = np.linalg.norm(axis)
            if axis_len < 1e-10:
                return None
            axis /= axis_len

            center = np.array(cyl.center, dtype=float)
            half_height = cyl.height / 2 + self.height_ext

            # Basis-Punkt
            base = center - axis * half_height
            height = cyl.height + 2 * self.height_ext

            # 1. FUSE: Füll-Zylinder (größer)
            fill_radius = cyl.radius + self.fill_margin
            fill_cyl = self._make_cylinder(base, axis, fill_radius, height)

            if fill_cyl is None:
                logger.debug("      Fill-Zylinder fehlgeschlagen")
                return None

            fuse_op = BRepAlgoAPI_Fuse(solid, fill_cyl)
            fuse_op.Build()

            if not fuse_op.IsDone():
                logger.debug("      FUSE fehlgeschlagen")
                return None

            filled = fuse_op.Shape()
            if filled.IsNull():
                logger.debug("      FUSE Ergebnis Null")
                return None

            # 2. CUT: Schnitt-Zylinder (exakt)
            cut_radius = cyl.radius + self.cut_margin
            cut_cyl = self._make_cylinder(base, axis, cut_radius, height)

            if cut_cyl is None:
                logger.debug("      Cut-Zylinder fehlgeschlagen")
                return None

            cut_op = BRepAlgoAPI_Cut(filled, cut_cyl)
            cut_op.Build()

            if not cut_op.IsDone():
                logger.debug("      CUT fehlgeschlagen")
                return None

            result = cut_op.Shape()
            if result.IsNull():
                logger.debug("      CUT Ergebnis Null")
                return None

            # Validiere
            analyzer = BRepCheck_Analyzer(result)
            if not analyzer.IsValid():
                fixer = ShapeFix_Shape(result)
                fixer.Perform()
                result = fixer.Shape()

            return result

        except Exception as e:
            logger.debug(f"      Exception: {e}")
            return None

    def _make_cylinder(self, base: np.ndarray, axis: np.ndarray,
                       radius: float, height: float) -> Optional[TopoDS_Solid]:
        """Erstellt Zylinder-Solid."""
        try:
            gp_base = gp_Pnt(float(base[0]), float(base[1]), float(base[2]))
            gp_axis = gp_Dir(float(axis[0]), float(axis[1]), float(axis[2]))
            ax2 = gp_Ax2(gp_base, gp_axis)

            maker = BRepPrimAPI_MakeCylinder(ax2, float(radius), float(height))
            maker.Build()

            if maker.IsDone():
                return maker.Solid()
            return None

        except Exception:
            return None

    def _count_faces(self, shape: TopoDS_Shape) -> int:
        """Zählt Faces."""
        count = 0
        exp = TopExp_Explorer(shape, TopAbs_FACE)
        while exp.More():
            count += 1
            exp.Next()
        return count
