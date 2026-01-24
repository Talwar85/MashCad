"""
Geometric Selectors für Topological Naming Problem (TNP) Lösung

Statt Faces/Edges nur über Punkt-Koordinaten zu referenzieren (fragil!),
speichern wir eine komplette geometrische Beschreibung.

Bei Rebuild nach Boolean-Ops können wir Faces/Edges mit Match-Score wiederfinden,
auch wenn sie sich leicht bewegt/verformt haben.

Autor: Claude (TNP-Fix Priority)
Datum: 2026-01-22
"""

from dataclasses import dataclass
from typing import Tuple, Optional, List
import numpy as np
from loguru import logger

try:
    from build123d import Face, Edge, Vector
    HAS_BUILD123D = True
except ImportError:
    HAS_BUILD123D = False
    logger.warning("build123d nicht verfügbar - GeometricSelectors können nicht genutzt werden")


@dataclass
class GeometricFaceSelector:
    """
    Geometrische Beschreibung einer Face für robustes Matching.

    Löst das Topological Naming Problem indem wir Face nicht nur über
    einen Punkt identifizieren, sondern über:
    - Center (Position)
    - Normal (Orientierung)
    - Area (Größe)
    - Surface-Type (Geometrie-Typ)

    Match-Score berechnet wie gut eine Candidate-Face passt (0-1).
    """
    center: Tuple[float, float, float]
    normal: Tuple[float, float, float]
    area: float
    surface_type: str  # "planar", "cylindrical", "spherical", "bspline"
    tolerance: float = 10.0  # mm Toleranz für Center-Match

    @staticmethod
    def from_face(face: 'Face') -> 'GeometricFaceSelector':
        """
        Erstellt Selector von Build123d Face.

        Args:
            face: Build123d Face-Objekt

        Returns:
            GeometricFaceSelector mit gespeicherten Properties
        """
        if not HAS_BUILD123D:
            raise ImportError("build123d nicht verfügbar")

        try:
            center = face.center()
            normal = face.normal_at(center)
            area = face.area

            # Surface-Type Detection
            surface_type = "planar"
            try:
                if hasattr(face.wrapped, 'Surface'):
                    surf = face.wrapped.Surface()
                    surf_type = type(surf).__name__
                    if 'Plane' in surf_type:
                        surface_type = "planar"
                    elif 'Cylinder' in surf_type:
                        surface_type = "cylindrical"
                    elif 'Sphere' in surf_type:
                        surface_type = "spherical"
                    else:
                        surface_type = "bspline"
            except Exception as e:
                logger.debug(f"Surface-Type Detection fehlgeschlagen: {e}")

            return GeometricFaceSelector(
                center=(center.X, center.Y, center.Z),
                normal=(normal.X, normal.Y, normal.Z),
                area=area,
                surface_type=surface_type
            )
        except Exception as e:
            logger.error(f"GeometricFaceSelector.from_face() fehlgeschlagen: {e}")
            raise

    def find_best_match(self, faces: List['Face']) -> Optional['Face']:
        """
        Findet beste Match-Face in Liste.

        Args:
            faces: Liste von Build123d Faces

        Returns:
            Beste Match-Face oder None (wenn Score < 60%)
        """
        if not faces:
            return None

        best_face = None
        best_score = 0.0

        for face in faces:
            try:
                score = self._match_score(face)
                if score > best_score:
                    best_score = score
                    best_face = face
            except Exception as e:
                logger.debug(f"Face-Matching fehlgeschlagen: {e}")
                continue

        # Nur returnen wenn Match gut genug (>60%)
        if best_score > 0.6:
            logger.debug(f"✅ Face Match gefunden (Score: {best_score:.2%})")
            return best_face
        else:
            logger.warning(f"⚠️ Keine passende Face gefunden (bester Score: {best_score:.2%})")
            return None

    def _match_score(self, face: 'Face') -> float:
        """
        Berechnet Match-Score (0-1) für Candidate-Face.

        Score-Komponenten:
        - 40%: Center-Proximity (< tolerance)
        - 30%: Normal-Similarity (Parallelität)
        - 20%: Area-Similarity
        - 10%: Surface-Type Match

        Args:
            face: Candidate Face

        Returns:
            Score 0-1 (1.0 = perfektes Match)
        """
        score = 0.0

        try:
            # 1. Center-Proximity (max 40 Punkte)
            center_face = face.center()
            dist = np.linalg.norm(
                np.array([center_face.X, center_face.Y, center_face.Z]) -
                np.array(self.center)
            )
            if dist < self.tolerance:
                score += 40 * (1.0 - dist / self.tolerance)

            # 2. Normal-Similarity (max 30 Punkte)
            normal_face = face.normal_at(center_face)
            dot = abs(np.dot(
                [normal_face.X, normal_face.Y, normal_face.Z],
                self.normal
            ))
            score += 30 * dot  # 1.0 = perfekt parallel

            # 3. Area-Similarity (max 20 Punkte)
            area_ratio = min(self.area, face.area) / max(self.area, face.area)
            score += 20 * area_ratio

            # 4. Surface-Type Match (max 10 Punkte)
            surf_type_match = self._detect_surface_type(face)
            if surf_type_match == self.surface_type:
                score += 10

        except Exception as e:
            logger.debug(f"Match-Score Berechnung fehlgeschlagen: {e}")
            return 0.0

        return score / 100.0  # Normalisiert 0-1

    def _detect_surface_type(self, face: 'Face') -> str:
        """Detektiert Surface-Typ von Face"""
        try:
            if hasattr(face.wrapped, 'Surface'):
                surf = face.wrapped.Surface()
                surf_type = type(surf).__name__
                if 'Plane' in surf_type:
                    return "planar"
                elif 'Cylinder' in surf_type:
                    return "cylindrical"
                elif 'Sphere' in surf_type:
                    return "spherical"
        except:
            pass
        return "bspline"

    def to_dict(self) -> dict:
        """Serialisiert Selector zu Dict für persistente Speicherung."""
        return {
            "center": list(self.center),
            "normal": list(self.normal),
            "area": self.area,
            "surface_type": self.surface_type,
            "tolerance": self.tolerance,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'GeometricFaceSelector':
        """Deserialisiert Selector von Dict."""
        return cls(
            center=tuple(data.get("center", (0, 0, 0))),
            normal=tuple(data.get("normal", (0, 0, 1))),
            area=data.get("area", 0),
            surface_type=data.get("surface_type", "planar"),
            tolerance=data.get("tolerance", 10.0),
        )


@dataclass
class GeometricEdgeSelector:
    """
    Geometrische Beschreibung einer Edge für robustes Matching.

    Löst das Topological Naming Problem indem wir Edge nicht nur über
    einen Punkt identifizieren, sondern über:
    - Center (Position)
    - Direction (Tangente)
    - Length (Länge)
    - Curve-Type (Geometrie-Typ)

    Match-Score berechnet wie gut eine Candidate-Edge passt (0-1).
    """
    center: Tuple[float, float, float]
    direction: Tuple[float, float, float]  # Tangente (normalisiert)
    length: float
    curve_type: str  # "line", "circle", "bspline"
    tolerance: float = 10.0  # mm Toleranz für Center-Match

    @staticmethod
    def from_edge(edge: 'Edge') -> 'GeometricEdgeSelector':
        """
        Erstellt Selector von Build123d Edge.

        Args:
            edge: Build123d Edge-Objekt

        Returns:
            GeometricEdgeSelector mit gespeicherten Properties
        """
        if not HAS_BUILD123D:
            raise ImportError("build123d nicht verfügbar")

        try:
            center = edge.center()
            tangent = edge.tangent_at(0.5)  # Mitte der Edge
            length = edge.length

            # Curve-Type Detection
            curve_type = "line"
            try:
                if hasattr(edge.wrapped, 'Curve'):
                    curve = edge.wrapped.Curve()
                    curve_type_name = type(curve).__name__
                    if 'Line' in curve_type_name:
                        curve_type = "line"
                    elif 'Circle' in curve_type_name:
                        curve_type = "circle"
                    else:
                        curve_type = "bspline"
            except Exception as e:
                logger.debug(f"Curve-Type Detection fehlgeschlagen: {e}")

            return GeometricEdgeSelector(
                center=(center.X, center.Y, center.Z),
                direction=(tangent.X, tangent.Y, tangent.Z),
                length=length,
                curve_type=curve_type
            )
        except Exception as e:
            logger.error(f"GeometricEdgeSelector.from_edge() fehlgeschlagen: {e}")
            raise

    def find_best_match(self, edges: List['Edge']) -> Optional['Edge']:
        """
        Findet beste Match-Edge in Liste.

        Args:
            edges: Liste von Build123d Edges

        Returns:
            Beste Match-Edge oder None (wenn Score < 60%)
        """
        if not edges:
            return None

        best_edge = None
        best_score = 0.0

        for edge in edges:
            try:
                score = self._match_score(edge)
                if score > best_score:
                    best_score = score
                    best_edge = edge
            except Exception as e:
                logger.debug(f"Edge-Matching fehlgeschlagen: {e}")
                continue

        # Nur returnen wenn Match gut genug (>60%)
        if best_score > 0.6:
            logger.debug(f"✅ Edge Match gefunden (Score: {best_score:.2%})")
            return best_edge
        else:
            logger.warning(f"⚠️ Keine passende Edge gefunden (bester Score: {best_score:.2%})")
            return None

    def _match_score(self, edge: 'Edge') -> float:
        """
        Berechnet Match-Score (0-1) für Candidate-Edge.

        Score-Komponenten:
        - 40%: Center-Proximity (< tolerance)
        - 30%: Direction-Similarity (Parallelität)
        - 20%: Length-Similarity
        - 10%: Curve-Type Match

        Args:
            edge: Candidate Edge

        Returns:
            Score 0-1 (1.0 = perfektes Match)
        """
        score = 0.0

        try:
            # 1. Center-Proximity (max 40 Punkte)
            center_edge = edge.center()
            dist = np.linalg.norm(
                np.array([center_edge.X, center_edge.Y, center_edge.Z]) -
                np.array(self.center)
            )
            if dist < self.tolerance:
                score += 40 * (1.0 - dist / self.tolerance)

            # 2. Direction-Similarity (max 30 Punkte)
            tangent_edge = edge.tangent_at(0.5)
            dot = abs(np.dot(
                [tangent_edge.X, tangent_edge.Y, tangent_edge.Z],
                self.direction
            ))
            score += 30 * dot  # 1.0 = perfekt parallel

            # 3. Length-Similarity (max 20 Punkte)
            length_ratio = min(self.length, edge.length) / max(self.length, edge.length)
            score += 20 * length_ratio

            # 4. Curve-Type Match (max 10 Punkte)
            curve_type = self._detect_curve_type(edge)
            if curve_type == self.curve_type:
                score += 10

        except Exception as e:
            logger.debug(f"Match-Score Berechnung fehlgeschlagen: {e}")
            return 0.0

        return score / 100.0  # Normalisiert 0-1

    def _detect_curve_type(self, edge: 'Edge') -> str:
        """Detektiert Curve-Typ von Edge"""
        try:
            if hasattr(edge.wrapped, 'Curve'):
                curve = edge.wrapped.Curve()
                curve_type = type(curve).__name__
                if 'Line' in curve_type:
                    return "line"
                elif 'Circle' in curve_type:
                    return "circle"
        except:
            pass
        return "bspline"

    def to_dict(self) -> dict:
        """Serialisiert Selector zu Dict für persistente Speicherung."""
        return {
            "center": list(self.center),
            "direction": list(self.direction),
            "length": self.length,
            "curve_type": self.curve_type,
            "tolerance": self.tolerance,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'GeometricEdgeSelector':
        """Deserialisiert Selector von Dict."""
        return cls(
            center=tuple(data.get("center", (0, 0, 0))),
            direction=tuple(data.get("direction", (1, 0, 0))),
            length=data.get("length", 0),
            curve_type=data.get("curve_type", "line"),
            tolerance=data.get("tolerance", 10.0),
        )


# ==================== HELPER FUNCTIONS ====================

def create_geometric_selectors_from_edges(edges: List['Edge']) -> List[GeometricEdgeSelector]:
    """
    Convenience-Funktion: Erstellt GeometricEdgeSelectors von Edge-Liste.

    Args:
        edges: Liste von Build123d Edges

    Returns:
        Liste von GeometricEdgeSelectors
    """
    selectors = []
    for edge in edges:
        try:
            selector = GeometricEdgeSelector.from_edge(edge)
            selectors.append(selector)
        except Exception as e:
            logger.warning(f"Konnte GeometricEdgeSelector nicht erstellen: {e}")
            continue

    return selectors


def create_geometric_selectors_from_faces(faces: List['Face']) -> List[GeometricFaceSelector]:
    """
    Convenience-Funktion: Erstellt GeometricFaceSelectors von Face-Liste.

    Args:
        faces: Liste von Build123d Faces

    Returns:
        Liste von GeometricFaceSelectors
    """
    selectors = []
    for face in faces:
        try:
            selector = GeometricFaceSelector.from_face(face)
            selectors.append(selector)
        except Exception as e:
            logger.warning(f"Konnte GeometricFaceSelector nicht erstellen: {e}")
            continue

    return selectors
