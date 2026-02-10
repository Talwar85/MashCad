"""
Mesh Analyzer - Analysiert Meshes und extrahiert CAD-Intent

Hauptziel des Sketch Agent:
Analysiert ein Mesh und schlägt Rekonstruktions-Schritte vor.

Author: Claude (Sketch Agent)
Date: 2026-02-10
"""

import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from loguru import logger

try:
    import pyvista as pv
    HAS_PYVISTA = True
except ImportError:
    HAS_PYVISTA = False
    logger.warning("PyVista nicht verfügbar")


from sketching.core.result_types import (
    MeshAnalysis, PrimitiveInfo, FeatureInfo
)


class MeshAnalyzer:
    """
    Analysiert ein Mesh und extrahiert CAD-Intent.

    Output:
    - Primitive Liste (Zylinder, Ebenen, Kugeln, etc.)
    - Feature Liste (Fillet, Chamfer, Bohrungen)
    - Vorgeschlagene Rekonstruktions-Schritte
    """

    def __init__(
        self,
        min_region_faces: int = 10,
        tolerance: float = 0.3
    ):
        """
        Args:
            min_region_faces: Min Faces für eine Region
            tolerance: Toleranz für Fitting in mm
        """
        self.min_region_faces = min_region_faces
        self.tolerance = tolerance

        # Importe vorhandene Detector
        try:
            from meshconverter.perfect.primitive_detector import (
                PrimitiveDetector, PrimitiveType
            )
            self.detector = PrimitiveDetector()
            self.PrimitiveType = PrimitiveType
            self.has_detector = True
        except ImportError:
            self.detector = None
            self.PrimitiveType = None
            self.has_detector = False
            logger.warning("PrimitiveDetector nicht verfügbar")

    def analyze(self, mesh_path: str) -> MeshAnalysis:
        """
        Führt vollständige Analyse durch.

        Schritte:
        1. Mesh laden
        2. Oberflächensegmentierung
        3. Primitive Detection (Plane, Cylinder, Sphere, Cone)
        4. Feature Detection (Fillet, Chamfer, Hole)
        5. Struktur-Analyse (Boss, Cut, Pocket)

        Args:
            mesh_path: Pfad zur Mesh-Datei

        Returns:
            MeshAnalysis mit allen gefundenen Informationen
        """
        import time
        start_time = time.time()

        try:
            # 1. Mesh laden
            mesh = self._load_mesh(mesh_path)
            if mesh is None:
                return MeshAnalysis([], [], {}, {}, 0)

            # 2. Primitives erkennen
            primitives = self.detect_primitives(mesh)

            # 3. Features erkennen
            features = self.detect_features(mesh, primitives)

            # 4. Rekonstruktions-Schritte vorschlagen
            steps = self.suggest_reconstruction(primitives, features)

            # 5. Mesh-Info sammeln
            mesh_info = self._get_mesh_info(mesh)

            duration_ms = (time.time() - start_time) * 1000

            return MeshAnalysis(
                primitives=[p.__dict__ for p in primitives],
                features=[f.__dict__ for f in features],
                suggested_steps=[s.__dict__ for s in steps],
                mesh_info=mesh_info,
                duration_ms=duration_ms
            )

        except Exception as e:
            logger.error(f"[MeshAnalyzer] Analyse fehlgeschlagen: {e}")
            import traceback
            traceback.print_exc()

            duration_ms = (time.time() - start_time) * 1000
            return MeshAnalysis([], [], {}, {}, duration_ms)

    def detect_primitives(
        self,
        mesh: 'pv.PolyData'
    ) -> List[PrimitiveInfo]:
        """
        Erkennt primitive Formen im Mesh.

        Returns:
            - PlaneInfo (Normal, Size, Position)
            - CylinderInfo (Radius, Height, Axis)
            - SphereInfo (Radius, Center)
            - ConeInfo (Radii, Height, Axis)
        """
        if not self.has_detector:
            logger.warning("[MeshAnalyzer] Kein Detector verfügbar")
            return []

        logger.debug(f"[MeshAnalyzer] Detecting Primitives: {mesh.n_cells} faces")

        primitives = []

        try:
            # Verwende den existierenden PrimitiveDetector
            detected = self.detector.detect_all(mesh)

            for det in detected:
                # Konvertiere zu PrimitiveInfo
                prim = PrimitiveInfo(
                    primitive_type=det.type.name.lower(),
                    center=tuple(det.origin) if det.origin is not None else (0, 0, 0),
                    parameters={},
                    confidence=det.confidence
                )

                # Typ-spezifische Parameter
                if det.type == self.PrimitiveType.PLANE:
                    prim.parameters = {
                        "normal": tuple(det.normal),
                        "area": det.area
                    }
                elif det.type == self.PrimitiveType.CYLINDER:
                    prim.parameters = {
                        "radius": det.radius or 0,
                        "height": det.height or 0,
                        "axis": tuple(det.axis) if det.axis is not None else (0, 0, 1)
                    }
                elif det.type == self.PrimitiveType.SPHERE:
                    prim.parameters = {
                        "radius": det.radius or 0
                    }
                elif det.type == self.PrimitiveType.CONE:
                    prim.parameters = {
                        "radius1": det.radius or 0,
                        "radius2": det.radius2 or 0,
                        "height": det.height or 0
                    }

                primitives.append(prim)
                logger.debug(f"  - {det.type.name}: {prim.parameters}")

        except Exception as e:
            logger.error(f"[MeshAnalyzer] Primitive Detection Error: {e}")

        return primitives

    def detect_features(
        self,
        mesh: 'pv.PolyData',
        primitives: List[PrimitiveInfo]
    ) -> List[FeatureInfo]:
        """
        Erkennt CAD-Features.

        Returns:
            - FilletInfo (Radius, Edges)
            - ChamferInfo (Distance, Edges)
            - HoleInfo (Diameter, Depth, Position)
            - PocketInfo (Shape, Depth, Corners)
        """
        features = []

        # TODO: Implementiere Feature-Erkennung
        # - Fillets: Prüfe auf konvexe Übergänge mit konstantem Radius
        # - Chamfers: Prüfe auf lineare Übergänge
        # - Holes: Kreisförmige Löcher durch andere Faces
        # - Pockets: Vertiefungen in planaren Faces

        logger.debug(f"[MeshAnalyzer] Feature Detection: {len(features)} Features")
        return features

    def suggest_reconstruction(
        self,
        primitives: List[PrimitiveInfo],
        features: List[FeatureInfo]
    ) -> List['ReconstructionStep']:
        """
        Schlägt Rekonstruktions-Schritte vor.

        Strategie:
        1. Finde größte planare Base-Fläche
        2. Erstelle Sketch mit allen 2D-Profilen
        3. Extrudiere
        4. Füge Secondary Features hinzu (Fillet, Chamfer, Bohrungen)
        """
        steps = []
        step_id = 0

        # Gruppiere Primitives nach Position
        if not primitives:
            # Keine Primitives gefunden -> Fallback
            steps.append(ReconstructionStep(
                step_id=step_id,
                operation="error",
                description="Keine Primitives erkannt - manuelle Rekonstruktion empfohlen"
            ))
            return steps

        # Finde Base-Plane (größte planare Fläche)
        base_plane = self._find_base_plane(primitives)
        if base_plane:
            steps.append(ReconstructionStep(
                step_id=step_id,
                operation="create_plane",
                description=f"Erstelle Base-Plane: {base_plane.parameters.get('area', 0):.1f}mm²",
                params={"plane": base_plane.parameters}
            ))
            step_id += 1

        # Finde alle 2D-Profile für Sketch
        profiles_2d = self._extract_2d_profiles(primitives, base_plane)

        for profile in profiles_2d:
            steps.append(ReconstructionStep(
                step_id=step_id,
                operation="create_profile",
                description=f"Erstelle {profile['type']}: {profile.get('radius', 0):.1f}",
                params=profile
            ))
            step_id += 1

        # Extrusion
        height = self._estimate_height(primitives, base_plane)
        steps.append(ReconstructionStep(
            step_id=step_id,
            operation="extrude",
            description=f"Extrudiere: {height:.1f}mm",
            params={"distance": height}
        ))
        step_id += 1

        # Features
        if features:
            for feat in features:
                steps.append(ReconstructionStep(
                    step_id=step_id,
                    operation=feat.feature_type,
                    description=f"Füge {feat.feature_type} hinzu",
                    params=feat.parameters
                ))
                step_id += 1

        logger.info(f"[MeshAnalyzer] {len(steps)} Rekonstruktions-Schritte vorgeschlagen")
        return steps

    def _load_mesh(self, mesh_path: str) -> Optional['pv.PolyData']:
        """Lädt Mesh aus Datei."""
        if not HAS_PYVISTA:
            return None

        try:
            logger.debug(f"[MeshAnalyzer] Lade Mesh: {mesh_path}")
            mesh = pv.read(mesh_path)

            # Reparieren wenn nötig
            if mesh.n_points == 0:
                logger.warning("[MeshAnalyzer] Mesh hat keine Punkte")
                return None

            # Clean up
            mesh = mesh.clean()

            logger.debug(f"[MeshAnalyzer] Mesh geladen: {mesh.n_points} pts, {mesh.n_cells} cells")
            return mesh

        except Exception as e:
            logger.error(f"[MeshAnalyzer] Laden fehlgeschlagen: {e}")
            return None

    def _get_mesh_info(self, mesh: 'pv.PolyData') -> Dict[str, Any]:
        """Sammelt Mesh-Informationen."""
        if mesh is None:
            return {}

        bbox = mesh.bounds
        return {
            "n_points": mesh.n_points,
            "n_cells": mesh.n_cells,
            "bounds": {
                "min": list(bbox[0]) if bbox else [0, 0, 0],
                "max": list(bbox[1]) if bbox else [0, 0, 0]
            },
            "size": [
                bbox[1][0] - bbox[0][0] if bbox else 0,
                bbox[1][1] - bbox[0][1] if bbox else 0,
                bbox[1][2] - bbox[0][2] if bbox else 0
            ]
        }

    def _find_base_plane(self, primitives: List[PrimitiveInfo]) -> Optional[PrimitiveInfo]:
        """Finde größte planare Fläche als Base."""
        planes = [p for p in primitives if p.primitive_type == "plane"]
        if planes:
            return max(planes, key=lambda p: p.parameters.get("area", 0))
        return None

    def _extract_2d_profiles(
        self,
        primitives: List[PrimitiveInfo],
        base_plane: Optional[PrimitiveInfo]
    ) -> List[Dict]:
        """
        Extrahiert 2D-Profile für Sketch-Erstellung.

        Projektiert alle Zylinder/Kreise auf die Base-Plane.
        """
        profiles = []

        for prim in primitives:
            if prim.primitive_type == "cylinder":
                # Kreis-Profile
                profiles.append({
                    "type": "circle",
                    "radius": prim.parameters.get("radius", 0),
                    "center": self._project_to_plane(prim.center, base_plane),
                    "primitive": prim.__dict__
                })
            elif prim.primitive_type == "sphere":
                profiles.append({
                    "type": "circle",
                    "radius": prim.parameters.get("radius", 0),
                    "center": self._project_to_plane(prim.center, base_plane)
                })

        return profiles

    def _project_to_plane(
        self,
        point_3d: Tuple[float, float, float],
        plane: Optional[PrimitiveInfo]
    ) -> Tuple[float, float]:
        """Projiziert 3D-Punkt auf 2D-Ebene."""
        if plane is None:
            return (point_3d[0], point_3d[1])

        # TODO: Implementiere echte Projektion auf Plane
        # Für jetzt: X, Y
        return (point_3d[0], point_3d[1])

    def _estimate_height(
        self,
        primitives: List[PrimitiveInfo],
        base_plane: Optional[PrimitiveInfo]
    ) -> float:
        """
        Schätzt Extrusionshöhe aus Primitives.

        Verwendet die Höhe von Zylindern oder eine Default-Höhe.
        """
        # Versuche Höhe von Zylindern zu bekommen
        for prim in primitives:
            if prim.primitive_type == "cylinder":
                height = prim.parameters.get("height", 0)
                if height > 0:
                    return height

        # Fallback: Default-Höhe
        return 30.0


@dataclass
class ReconstructionStep:
    """Ein Schritt im Rekonstruktions-Prozess."""
    step_id: int
    operation: str  # "create_plane", "create_profile", "extrude", "fillet", etc.
    description: str
    params: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dict für Serialisierung."""
        return {
            "step_id": self.step_id,
            "operation": self.operation,
            "description": self.description,
            "params": self.params
        }
