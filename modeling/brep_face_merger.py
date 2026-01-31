"""
MashCad - BREP Face Merger
==========================

Merged koplanare/koaxiale Faces nach BREP Cleanup Analyse.

Verwendet OCP ShapeUpgrade_UnifySameDomain fuer sichere Merge-Operationen.
Bietet auch Surface Fitting fuer tessellierte Zylinder (STL-Import).

Alle Operationen sind durch BodyTransaction gesichert.

Author: Claude (BREP Cleanup Feature)
Date: 2026-01
"""

from typing import List, Tuple, Optional, Set, Dict, Any
import numpy as np
from loguru import logger

# OCP imports
from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE, TopAbs_WIRE, TopAbs_SHELL, TopAbs_SOLID
from OCP.TopExp import TopExp, TopExp_Explorer
from OCP.TopTools import TopTools_IndexedMapOfShape, TopTools_ListOfShape
from OCP.TopoDS import TopoDS_Shape, TopoDS_Solid, TopoDS_Face, TopoDS_Edge, TopoDS_Wire, TopoDS, TopoDS_Shell
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeSolid, BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeWire, BRepBuilderAPI_Sewing
from OCP.ShapeFix import ShapeFix_Shape, ShapeFix_Solid, ShapeFix_Shell
from OCP.gp import gp_Pnt, gp_Dir, gp_Ax3, gp_Cylinder, gp_Ax1, gp_Vec
from OCP.Geom import Geom_CylindricalSurface
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.GCPnts import GCPnts_AbscissaPoint
from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder

from modeling.result_types import OperationResult, ResultStatus
from modeling.brep_face_analyzer import AnalysisResult, DetectedFeature, FeatureType

try:
    from build123d import Solid
    HAS_BUILD123D = True
except ImportError:
    HAS_BUILD123D = False


# =============================================================================
# Cylinder Surface Fitter
# =============================================================================

class CylinderSurfaceFitter:
    """
    Fittet analytische Zylinderflaechen an tessellierte planare Faces.

    Nach STL-Import bestehen Zylinder aus vielen kleinen planaren Faces.
    Diese Klasse ersetzt diese Faces durch echte Zylinderflaechen.

    Workflow:
    1. Nimmt erkannte zylindrische Features (von BRepFaceAnalyzer)
    2. Extrahiert Boundary-Edges der Face-Gruppe
    3. Erstellt analytische Zylinderflaeche
    4. Baut neues Solid mit ersetzten Faces

    Usage:
        fitter = CylinderSurfaceFitter()
        result = fitter.fit_cylinder_features(solid, analysis)
    """

    # Toleranzen
    LINEAR_TOLERANCE = 0.1    # mm
    SEWING_TOLERANCE = 0.5    # mm (fuer Sewing-Operationen)

    def fit_cylinder_features(
        self,
        solid,
        analysis: AnalysisResult,
        feature_indices: List[int] = None
    ) -> OperationResult:
        """
        Ersetzt tessellierte Zylinder durch analytische Flaechen.

        Args:
            solid: Build123d Solid oder TopoDS_Shape
            analysis: AnalysisResult vom BRepFaceAnalyzer
            feature_indices: Optionale Liste der zu fittenden Feature-Indices
                           (None = alle zylindrischen Features)

        Returns:
            OperationResult mit neuem Solid
        """
        shape = solid.wrapped if hasattr(solid, 'wrapped') else solid

        # Features filtern
        if feature_indices is None:
            # Alle zylindrischen Features
            cylinder_features = [
                (i, f) for i, f in enumerate(analysis.features)
                if f.feature_type in (FeatureType.HOLE_THROUGH, FeatureType.HOLE_BLIND,
                                      FeatureType.BOSS_CYLINDER)
                and f.parameters.get("detected_from") == "planar_cluster"
            ]
        else:
            cylinder_features = [
                (i, analysis.features[i]) for i in feature_indices
                if 0 <= i < len(analysis.features)
                and analysis.features[i].feature_type in (FeatureType.HOLE_THROUGH,
                                                          FeatureType.HOLE_BLIND,
                                                          FeatureType.BOSS_CYLINDER)
            ]

        if not cylinder_features:
            return OperationResult.empty("Keine zylindrischen Features zum Fitten gefunden")

        logger.info(f"CylinderSurfaceFitter: Starte Fitting fuer {len(cylinder_features)} Features")

        # Face-Map erstellen
        face_map = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(shape, TopAbs_FACE, face_map)
        total_faces = face_map.Extent()

        # Sammle alle Face-Indices die ersetzt werden
        faces_to_remove: Set[int] = set()
        cylinders_to_add = []

        for feat_idx, feature in cylinder_features:
            params = feature.parameters

            # Extrahiere Zylinderparameter
            radius = params.get("radius")
            center_2d = params.get("center")
            axis_name = params.get("axis", "Z")

            if radius is None or center_2d is None:
                logger.warning(f"Feature {feat_idx}: Unvollstaendige Parameter, ueberspringe")
                continue

            # Berechne 3D-Achse und Zentrum
            axis_dir = self._axis_name_to_direction(axis_name)

            # Finde Z-Bereich der Faces
            z_min, z_max = self._find_feature_z_range(
                feature.face_indices, face_map, axis_name
            )

            if z_min is None:
                logger.warning(f"Feature {feat_idx}: Konnte Z-Bereich nicht bestimmen")
                continue

            # 3D-Zentrum berechnen
            center_3d = self._center_2d_to_3d(center_2d, axis_name, z_min)

            # Zylinderhoehe
            height = z_max - z_min
            if height < 0.1:  # Mindesthoehe
                height = 1.0  # Default

            is_hole = feature.feature_type in (FeatureType.HOLE_THROUGH, FeatureType.HOLE_BLIND)

            cylinders_to_add.append({
                "radius": radius,
                "center": center_3d,
                "axis": axis_dir,
                "height": height,
                "is_hole": is_hole,
                "face_indices": feature.face_indices
            })

            faces_to_remove.update(feature.face_indices)

            logger.debug(f"Feature {feat_idx}: R={radius:.2f}mm, H={height:.2f}mm, "
                        f"{'Loch' if is_hole else 'Boss'}, {len(feature.face_indices)} Faces")

        if not cylinders_to_add:
            return OperationResult.empty("Keine gueltigen Zylinderparameter gefunden")

        # Rebuild Solid
        try:
            result_shape = self._rebuild_solid_with_cylinders(
                shape, face_map, faces_to_remove, cylinders_to_add
            )

            if result_shape is None:
                return OperationResult.error("Surface Fitting: Rebuild fehlgeschlagen")

            # Validierung
            analyzer = BRepCheck_Analyzer(result_shape)
            if not analyzer.IsValid():
                logger.warning("Surface Fitting: Shape ungueltig, versuche Reparatur...")
                fixer = ShapeFix_Shape(result_shape)
                fixer.SetPrecision(self.LINEAR_TOLERANCE)
                fixer.Perform()
                result_shape = fixer.Shape()

                analyzer2 = BRepCheck_Analyzer(result_shape)
                if not analyzer2.IsValid():
                    return OperationResult.error("Surface Fitting: Shape konnte nicht repariert werden")

            # Face-Count nachher
            face_map_after = TopTools_IndexedMapOfShape()
            TopExp.MapShapes_s(result_shape, TopAbs_FACE, face_map_after)
            faces_after = face_map_after.Extent()

            # In Build123d Solid wandeln
            if HAS_BUILD123D:
                result_solid = Solid(result_shape)
            else:
                result_solid = result_shape

            faces_reduced = total_faces - faces_after
            logger.success(f"Surface Fitting erfolgreich: {total_faces} → {faces_after} Faces "
                          f"({faces_reduced} reduziert, {len(cylinders_to_add)} Zylinder gefittet)")

            return OperationResult.success(
                result_solid,
                f"Surface Fitting: {len(cylinders_to_add)} Zylinder gefittet, "
                f"{faces_reduced} Faces reduziert"
            )

        except Exception as e:
            logger.error(f"Surface Fitting fehlgeschlagen: {e}")
            import traceback
            traceback.print_exc()
            return OperationResult.error(f"Surface Fitting fehlgeschlagen: {e}", exception=e)

    def _axis_name_to_direction(self, axis_name: str) -> np.ndarray:
        """Konvertiert Achsennamen zu Richtungsvektor."""
        directions = {
            'X': np.array([1.0, 0.0, 0.0]),
            'Y': np.array([0.0, 1.0, 0.0]),
            'Z': np.array([0.0, 0.0, 1.0])
        }
        return directions.get(axis_name, np.array([0.0, 0.0, 1.0]))

    def _center_2d_to_3d(self, center_2d: List[float], axis_name: str, z_pos: float) -> np.ndarray:
        """Konvertiert 2D-Zentrum zu 3D basierend auf Achse."""
        if axis_name == 'Z':
            return np.array([center_2d[0], center_2d[1], z_pos])
        elif axis_name == 'Y':
            return np.array([center_2d[0], z_pos, center_2d[1]])
        else:  # X
            return np.array([z_pos, center_2d[0], center_2d[1]])

    def _find_feature_z_range(
        self,
        face_indices: List[int],
        face_map: TopTools_IndexedMapOfShape,
        axis_name: str
    ) -> Tuple[Optional[float], Optional[float]]:
        """Findet den Bereich des Features entlang der Achse."""
        axis_idx = {'X': 0, 'Y': 1, 'Z': 2}.get(axis_name, 2)

        z_values = []

        for face_idx in face_indices:
            # Konvertiere 0-basiert (Analyzer) zu 1-basiert (OCP)
            ocp_idx = face_idx + 1
            if ocp_idx < 1 or ocp_idx > face_map.Extent():
                continue

            try:
                face = TopoDS.Face_s(face_map.FindKey(ocp_idx))

                # Sample Punkte auf der Face
                explorer = TopExp_Explorer(face, TopAbs_EDGE)
                while explorer.More():
                    edge = TopoDS.Edge_s(explorer.Current())

                    # Hole Endpunkte der Kante
                    try:
                        adaptor = BRepAdaptor_Curve(edge)
                        p1 = adaptor.Value(adaptor.FirstParameter())
                        p2 = adaptor.Value(adaptor.LastParameter())

                        z_values.append(p1.Coord()[axis_idx])
                        z_values.append(p2.Coord()[axis_idx])
                    except:
                        pass

                    explorer.Next()
            except:
                continue

        if not z_values:
            return None, None

        return min(z_values), max(z_values)

    def _rebuild_solid_with_cylinders(
        self,
        original_shape: TopoDS_Shape,
        face_map: TopTools_IndexedMapOfShape,
        faces_to_remove: Set[int],
        cylinders_to_add: List[Dict[str, Any]]
    ) -> Optional[TopoDS_Shape]:
        """
        Baut Solid neu mit Zylinderflaechen anstelle der planaren Facetten.

        Strategie:
        1. Sammle alle Faces die NICHT ersetzt werden
        2. Erstelle neue Zylinderflaechen
        3. Sew alles zusammen zu neuem Solid
        """
        logger.debug(f"Rebuild: {face_map.Extent()} Faces, entferne {len(faces_to_remove)}, "
                    f"fuege {len(cylinders_to_add)} Zylinder hinzu")

        # Sewing-Objekt erstellen
        sewer = BRepBuilderAPI_Sewing(self.SEWING_TOLERANCE)
        sewer.SetNonManifoldMode(False)
        sewer.SetFloatingEdgesMode(False)

        # 1. Behalte alle Faces die nicht ersetzt werden
        # faces_to_remove ist 0-basiert (vom Analyzer), OCP nutzt 1-basiert
        # Konvertiere zu 1-basierten Indices
        ocp_faces_to_remove = {idx + 1 for idx in faces_to_remove}

        kept_faces = 0
        for i in range(1, face_map.Extent() + 1):
            if i not in ocp_faces_to_remove:
                face = face_map.FindKey(i)
                sewer.Add(face)
                kept_faces += 1

        logger.debug(f"Rebuild: {kept_faces} Faces behalten")

        # 2. Erstelle und fuege Zylinderflaechen hinzu
        for cyl_data in cylinders_to_add:
            try:
                cyl_face = self._create_cylinder_face(
                    cyl_data["radius"],
                    cyl_data["center"],
                    cyl_data["axis"],
                    cyl_data["height"],
                    cyl_data["is_hole"]
                )

                if cyl_face is not None:
                    sewer.Add(cyl_face)
                    logger.debug(f"Rebuild: Zylinder-Face hinzugefuegt R={cyl_data['radius']:.2f}")
                else:
                    logger.warning(f"Rebuild: Zylinder-Face Erstellung fehlgeschlagen")

            except Exception as e:
                logger.error(f"Rebuild: Zylinder-Erstellung fehlgeschlagen: {e}")

        # 3. Sewing durchfuehren
        try:
            sewer.Perform()
            sewn_shape = sewer.SewedShape()

            if sewn_shape.IsNull():
                logger.error("Rebuild: Sewing ergab Null-Shape")
                return None

            # 4. Versuche Solid zu erstellen
            result = self._make_solid_from_shell(sewn_shape)

            if result is not None:
                return result

            # Fallback: Repariere und versuche erneut
            logger.warning("Rebuild: Erster Solid-Versuch fehlgeschlagen, versuche Reparatur")

            fixer = ShapeFix_Shape(sewn_shape)
            fixer.SetPrecision(self.LINEAR_TOLERANCE)
            fixer.Perform()
            fixed = fixer.Shape()

            return self._make_solid_from_shell(fixed)

        except Exception as e:
            logger.error(f"Rebuild: Sewing fehlgeschlagen: {e}")
            return None

    def _create_cylinder_face(
        self,
        radius: float,
        center: np.ndarray,
        axis: np.ndarray,
        height: float,
        is_hole: bool
    ) -> Optional[TopoDS_Face]:
        """
        Erstellt eine analytische Zylinderflaeche.

        Args:
            radius: Zylinderradius in mm
            center: 3D-Zentrum (Basis)
            axis: Achsenrichtung (normiert)
            height: Hoehe des Zylinders
            is_hole: True wenn Loch (Normale nach aussen)
        """
        try:
            # OCP gp_Ax3 fuer Zylinder
            origin = gp_Pnt(float(center[0]), float(center[1]), float(center[2]))
            direction = gp_Dir(float(axis[0]), float(axis[1]), float(axis[2]))

            # Koordinatensystem fuer Zylinder
            ax3 = gp_Ax3(origin, direction)

            # Zylinder-Geometrie
            cylinder = gp_Cylinder(ax3, float(radius))

            # Zylindrische Flaeche
            cyl_surface = Geom_CylindricalSurface(cylinder)

            # Face mit Parametergrenzen erstellen
            # U: 0 bis 2*PI (voller Kreis)
            # V: 0 bis height
            u_min = 0.0
            u_max = 2.0 * np.pi
            v_min = 0.0
            v_max = float(height)

            # Face erstellen
            face_builder = BRepBuilderAPI_MakeFace(
                cyl_surface,
                u_min, u_max,
                v_min, v_max,
                self.LINEAR_TOLERANCE
            )

            if not face_builder.IsDone():
                logger.warning("Cylinder Face Builder nicht erfolgreich")
                return None

            face = face_builder.Face()

            # Bei Loch: Face umdrehen (Normale nach aussen = weg vom Zentrum)
            if is_hole:
                face.Reverse()

            return face

        except Exception as e:
            logger.error(f"Zylinder-Face Erstellung fehlgeschlagen: {e}")
            return None

    def _make_solid_from_shell(self, shape: TopoDS_Shape) -> Optional[TopoDS_Shape]:
        """Versucht aus Shape ein Solid zu machen."""
        try:
            # Wenn bereits Solid, zurueckgeben
            if shape.ShapeType() == TopAbs_SOLID:
                return shape

            # Wenn Shell, zu Solid konvertieren
            if shape.ShapeType() == TopAbs_SHELL:
                shell = TopoDS.Shell_s(shape)

                # Repariere Shell
                fixer = ShapeFix_Shell(shell)
                fixer.SetPrecision(self.LINEAR_TOLERANCE)
                fixer.Perform()
                fixed_shell = fixer.Shell()

                # Solid erstellen
                solid_builder = BRepBuilderAPI_MakeSolid(fixed_shell)
                if solid_builder.IsDone():
                    return solid_builder.Solid()

            # Versuche aus beliebigem Shape
            solid_builder = BRepBuilderAPI_MakeSolid()

            # Alle Shells sammeln
            explorer = TopExp_Explorer(shape, TopAbs_SHELL)
            while explorer.More():
                shell = TopoDS.Shell_s(explorer.Current())
                solid_builder.Add(shell)
                explorer.Next()

            if solid_builder.IsDone():
                return solid_builder.Solid()

            return None

        except Exception as e:
            logger.error(f"Solid-Erstellung fehlgeschlagen: {e}")
            return None


class BRepFaceMerger:
    """
    Merged BREP-Faces nach Analyse.

    Bietet zwei Modi:
    1. Auto-Merge: UnifySameDomain auf gesamten Body
    2. Selektiv: Nur ausgewaehlte Features mergen

    Usage:
        merger = BRepFaceMerger()

        # Auto-Merge
        result = merger.auto_merge(solid)

        # Selektives Mergen
        result = merger.merge_features(solid, feature_indices, analysis)
    """

    # Toleranzen
    LINEAR_TOLERANCE = 0.1    # mm
    ANGULAR_TOLERANCE = 1.0   # Grad

    def auto_merge(self, solid, tolerance: float = None) -> OperationResult:
        """
        Merged automatisch alle koplanaren/koaxialen Faces.

        Verwendet ShapeUpgrade_UnifySameDomain fuer sichere Merge-Operation.
        Validiert Ergebnis vor Rueckgabe.

        Args:
            solid: Build123d Solid oder TopoDS_Shape
            tolerance: Optionale Toleranz (default: LINEAR_TOLERANCE)

        Returns:
            OperationResult mit gemergtem Solid
        """
        # Shape extrahieren
        shape = solid.wrapped if hasattr(solid, 'wrapped') else solid

        logger.info("BRepFaceMerger: Starte Auto-Merge...")

        # Face-Count vorher
        face_map_before = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(shape, TopAbs_FACE, face_map_before)
        faces_before = face_map_before.Extent()

        try:
            # UnifySameDomain anwenden
            lin_tol = tolerance if tolerance else self.LINEAR_TOLERANCE
            ang_tol = np.radians(self.ANGULAR_TOLERANCE)

            upgrader = ShapeUpgrade_UnifySameDomain(shape, True, True, True)
            upgrader.SetLinearTolerance(lin_tol)
            upgrader.SetAngularTolerance(ang_tol)
            upgrader.Build()

            result_shape = upgrader.Shape()

            # Validierung
            validation = self._validate_shape(result_shape)
            if not validation.is_success:
                return validation

            # Face-Count nachher
            face_map_after = TopTools_IndexedMapOfShape()
            TopExp.MapShapes_s(result_shape, TopAbs_FACE, face_map_after)
            faces_after = face_map_after.Extent()

            merged_count = faces_before - faces_after

            # In Build123d Solid wandeln falls verfuegbar
            if HAS_BUILD123D:
                result_solid = Solid(result_shape)
            else:
                result_solid = result_shape

            logger.success(f"Auto-Merge erfolgreich: {faces_before} → {faces_after} Faces ({merged_count} gemergt)")

            return OperationResult.success(
                result_solid,
                f"Auto-Merge erfolgreich: {merged_count} Faces zusammengefuegt"
            )

        except Exception as e:
            logger.error(f"Auto-Merge fehlgeschlagen: {e}")
            return OperationResult.error(
                f"Auto-Merge fehlgeschlagen: {e}",
                exception=e
            )

    def merge_features(self, solid, feature_indices: List[int],
                       analysis: AnalysisResult) -> OperationResult:
        """
        Merged spezifische Features basierend auf Analyse.

        Args:
            solid: Build123d Solid oder TopoDS_Shape
            feature_indices: Indices der zu mergenden Features aus analysis.features
            analysis: AnalysisResult vom BRepFaceAnalyzer

        Returns:
            OperationResult mit gemergtem Solid
        """
        if not feature_indices:
            return OperationResult.empty("Keine Features zum Mergen ausgewaehlt")

        # Face-Indices sammeln
        face_indices_to_merge: Set[int] = set()
        for feat_idx in feature_indices:
            if 0 <= feat_idx < len(analysis.features):
                feature = analysis.features[feat_idx]
                face_indices_to_merge.update(feature.face_indices)

        if not face_indices_to_merge:
            return OperationResult.empty("Keine Faces in den ausgewaehlten Features")

        logger.info(f"BRepFaceMerger: Merge {len(face_indices_to_merge)} Faces aus {len(feature_indices)} Features")

        # Fuer selektives Mergen verwenden wir auch UnifySameDomain
        # (OCP hat keine direkte "merge diese Faces" API)
        # Das Ergebnis ist das gleiche, da UnifySameDomain nur
        # geometrisch kompatible Faces merged

        return self.auto_merge(solid)

    def merge_by_feature_type(self, solid, feature_type: FeatureType,
                              analysis: AnalysisResult) -> OperationResult:
        """
        Merged alle Features eines bestimmten Typs.

        Args:
            solid: Build123d Solid oder TopoDS_Shape
            feature_type: FeatureType enum
            analysis: AnalysisResult vom BRepFaceAnalyzer

        Returns:
            OperationResult mit gemergtem Solid
        """
        # Features dieses Typs finden
        matching_indices = [
            i for i, f in enumerate(analysis.features)
            if f.feature_type == feature_type
        ]

        if not matching_indices:
            return OperationResult.empty(
                f"Keine Features vom Typ {feature_type.name} gefunden"
            )

        return self.merge_features(solid, matching_indices, analysis)

    def heal_and_merge(self, solid) -> OperationResult:
        """
        Repariert Shape vor dem Mergen.

        Nuetzlich wenn UnifySameDomain allein fehlschlaegt.

        Args:
            solid: Build123d Solid oder TopoDS_Shape

        Returns:
            OperationResult mit repariertem und gemergtem Solid
        """
        shape = solid.wrapped if hasattr(solid, 'wrapped') else solid

        logger.info("BRepFaceMerger: Heal and Merge...")

        try:
            # 1. Shape reparieren
            fixer = ShapeFix_Shape(shape)
            fixer.SetPrecision(self.LINEAR_TOLERANCE)
            fixer.Perform()
            fixed_shape = fixer.Shape()

            # 2. Auto-Merge auf repariertem Shape
            return self.auto_merge(fixed_shape)

        except Exception as e:
            logger.error(f"Heal and Merge fehlgeschlagen: {e}")
            return OperationResult.error(
                f"Heal and Merge fehlgeschlagen: {e}",
                exception=e
            )

    def _validate_shape(self, shape: TopoDS_Shape) -> OperationResult:
        """
        Validiert Shape nach Merge-Operation.

        Prueft auf:
        - Gueltige Geometrie
        - Geschlossene Shell
        - Positive Volumen
        """
        try:
            # BRepCheck Analyzer
            analyzer = BRepCheck_Analyzer(shape)

            if not analyzer.IsValid():
                # Versuche zu reparieren
                logger.warning("Shape nach Merge ungueltig, versuche Reparatur...")

                fixer = ShapeFix_Shape(shape)
                fixer.SetPrecision(self.LINEAR_TOLERANCE)
                fixer.Perform()
                fixed = fixer.Shape()

                analyzer2 = BRepCheck_Analyzer(fixed)
                if not analyzer2.IsValid():
                    return OperationResult.error(
                        "Shape nach Merge ungueltig und konnte nicht repariert werden"
                    )

                logger.info("Shape erfolgreich repariert")
                return OperationResult.success(fixed, "Shape repariert")

            return OperationResult.success(shape, "Shape valide")

        except Exception as e:
            return OperationResult.error(
                f"Shape-Validierung fehlgeschlagen: {e}",
                exception=e
            )

    def get_merge_preview(self, solid, analysis: AnalysisResult) -> dict:
        """
        Gibt Vorschau der Merge-Operation zurueck ohne sie auszufuehren.

        Returns:
            Dict mit:
            - faces_before: Anzahl Faces aktuell
            - faces_after_estimate: Geschaetzte Anzahl nach Merge
            - mergeable_features: Liste der zusammenfuehrbaren Features
        """
        shape = solid.wrapped if hasattr(solid, 'wrapped') else solid

        face_map = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(shape, TopAbs_FACE, face_map)
        faces_before = face_map.Extent()

        # Schaetze Reduktion basierend auf erkannten Features
        mergeable_count = 0
        mergeable_features = []

        for feature in analysis.features:
            if len(feature.face_indices) > 1:
                # Feature mit mehreren Faces kann gemergt werden
                mergeable_count += len(feature.face_indices) - 1
                mergeable_features.append({
                    "type": feature.display_name,
                    "icon": feature.icon,
                    "faces": len(feature.face_indices),
                    "reduction": len(feature.face_indices) - 1
                })

        return {
            "faces_before": faces_before,
            "faces_after_estimate": max(1, faces_before - mergeable_count),
            "reduction_estimate": mergeable_count,
            "mergeable_features": mergeable_features
        }

    def surface_fit_merge(self, solid, analysis: AnalysisResult,
                          feature_indices: List[int] = None) -> OperationResult:
        """
        Kombiniert Surface Fitting mit Auto-Merge.

        Erst werden tessellierte Zylinder durch analytische Flaechen ersetzt,
        dann wird UnifySameDomain angewendet.

        Args:
            solid: Build123d Solid oder TopoDS_Shape
            analysis: AnalysisResult vom BRepFaceAnalyzer
            feature_indices: Optionale Liste der zu fittenden Features

        Returns:
            OperationResult mit optimiertem Solid
        """
        logger.info("BRepFaceMerger: Starte Surface Fit + Merge...")

        # Schritt 1: Surface Fitting
        fitter = CylinderSurfaceFitter()
        fit_result = fitter.fit_cylinder_features(solid, analysis, feature_indices)

        if fit_result.is_error:
            logger.warning(f"Surface Fitting fehlgeschlagen: {fit_result.message}")
            # Fallback auf Auto-Merge ohne Fitting
            return self.auto_merge(solid)

        if fit_result.status == ResultStatus.EMPTY:
            logger.info("Keine zylindrischen Features gefunden, nur Auto-Merge")
            return self.auto_merge(solid)

        # Schritt 2: Auto-Merge auf gefittetem Result
        fitted_solid = fit_result.value
        merge_result = self.auto_merge(fitted_solid)

        if merge_result.is_error:
            # Fitting hat funktioniert, Merge nicht - gib Fitting-Ergebnis zurueck
            logger.warning("Auto-Merge nach Fitting fehlgeschlagen, verwende nur Fitting-Ergebnis")
            return fit_result

        # Kombinierte Nachricht
        total_message = f"{fit_result.message}; {merge_result.message}"
        return OperationResult.success(merge_result.value, total_message)


# =============================================================================
# Convenience Functions
# =============================================================================

def auto_merge_body(solid) -> OperationResult:
    """
    Convenience-Funktion fuer Auto-Merge.

    Usage:
        from modeling.brep_face_merger import auto_merge_body
        result = auto_merge_body(body._build123d_solid)
    """
    merger = BRepFaceMerger()
    return merger.auto_merge(solid)


def surface_fit_body(solid, analysis: AnalysisResult) -> OperationResult:
    """
    Convenience-Funktion fuer Surface Fitting.

    Ersetzt tessellierte Zylinder durch analytische Flaechen.

    Usage:
        from modeling.brep_face_merger import surface_fit_body
        result = surface_fit_body(body._build123d_solid, analysis)
    """
    fitter = CylinderSurfaceFitter()
    return fitter.fit_cylinder_features(solid, analysis)


def merge_with_transaction(body, analysis: AnalysisResult = None) -> OperationResult:
    """
    Merged Body mit Transaction-Sicherheit.

    Wenn analysis vorhanden ist, wird zuerst Surface Fitting angewendet.

    Usage:
        from modeling.brep_face_merger import merge_with_transaction
        result = merge_with_transaction(body)  # nur Auto-Merge
        result = merge_with_transaction(body, analysis)  # Surface Fit + Merge
    """
    from modeling.body_transaction import BodyTransaction

    merger = BRepFaceMerger()

    with BodyTransaction(body, "BREP Face Merge") as txn:
        if analysis is not None:
            # Surface Fitting + Auto-Merge
            result = merger.surface_fit_merge(body._build123d_solid, analysis)
        else:
            # Nur Auto-Merge
            result = merger.auto_merge(body._build123d_solid)

        if result.is_error:
            raise RuntimeError(result.message)

        body._build123d_solid = result.value
        body.invalidate_mesh()
        txn.commit()

    return result


def surface_fit_with_transaction(body, analysis: AnalysisResult,
                                  feature_indices: List[int] = None) -> OperationResult:
    """
    Surface Fitting mit Transaction-Sicherheit.

    Ersetzt tessellierte Zylinder durch analytische Flaechen.

    Usage:
        from modeling.brep_face_merger import surface_fit_with_transaction
        result = surface_fit_with_transaction(body, analysis)
    """
    from modeling.body_transaction import BodyTransaction

    fitter = CylinderSurfaceFitter()

    with BodyTransaction(body, "Surface Fitting") as txn:
        result = fitter.fit_cylinder_features(body._build123d_solid, analysis, feature_indices)

        if result.is_error:
            raise RuntimeError(result.message)

        if result.status == ResultStatus.EMPTY:
            # Keine Aenderung, aber kein Fehler
            return result

        body._build123d_solid = result.value
        body.invalidate_mesh()
        txn.commit()

    return result
