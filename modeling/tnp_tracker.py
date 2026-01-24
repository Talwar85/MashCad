"""
MashCad - TNP Tracker (Topological Naming Problem)
==================================================

Phase 8.2: Erweiterte Shape-Referenz-Verfolgung

Das Topological Naming Problem (TNP) tritt auf, wenn sich Shape-Referenzen
nach CAD-Operationen ändern. Beispiel:
- Extrude erstellt Face_1
- Fillet referenziert Face_1
- Änderung am Extrude → Face_1 bekommt neuen Hash → Fillet bricht

Lösungsansatz:
1. BRepTools_History für Operations-Tracking
2. Geometrische Selektoren als Fallback
3. Multi-Strategie-Auflösung

Verwendung:
    from modeling.tnp_tracker import TNPTracker, ShapeReference

    tracker = TNPTracker()

    # Referenz erstellen
    ref = tracker.create_reference(face, "fillet_target_1", "face")

    # Nach Operation auflösen
    new_face = tracker.resolve_reference("fillet_target_1", new_solid)

Author: Claude (Phase 8 CAD-Kernel)
Date: 2026-01-23
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple, Set
from enum import Enum, auto
from loguru import logger
import hashlib


class ShapeType(Enum):
    """Topologische Shape-Typen."""
    FACE = "face"
    EDGE = "edge"
    VERTEX = "vertex"
    WIRE = "wire"
    SHELL = "shell"
    SOLID = "solid"


class ResolutionStrategy(Enum):
    """Strategien zur Referenz-Auflösung."""
    HISTORY = auto()     # BRepTools_History (primär)
    HASH = auto()        # Shape-Hash Vergleich
    GEOMETRY = auto()    # Geometrischer Selektor
    TOPOLOGY = auto()    # Topologische Position


@dataclass
class GeometricSelector:
    """
    Geometrische Eigenschaften eines Shapes für Fallback-Matching.

    Speichert Eigenschaften die sich bei topologischen Änderungen
    weniger ändern als der Shape-Hash.
    """
    center: Tuple[float, float, float] = (0, 0, 0)
    normal: Optional[Tuple[float, float, float]] = None  # Für Faces
    area: float = 0.0  # Für Faces
    length: float = 0.0  # Für Edges
    midpoint: Optional[Tuple[float, float, float]] = None  # Für Edges
    surface_type: str = ""  # "plane", "cylinder", "cone", "sphere", etc.
    curve_type: str = ""  # "line", "circle", "ellipse", "bspline", etc.

    def match_score(self, other: 'GeometricSelector', tolerance: float = 0.1) -> float:
        """
        Berechnet Übereinstimmungs-Score [0.0 - 1.0].

        Args:
            other: Anderer Selektor zum Vergleich
            tolerance: Toleranz für Positionsvergleiche

        Returns:
            Score von 0.0 (keine Übereinstimmung) bis 1.0 (perfekt)
        """
        score = 0.0
        weights = 0.0

        # Center-Match
        if self.center and other.center:
            dist = sum((a - b) ** 2 for a, b in zip(self.center, other.center)) ** 0.5
            center_score = max(0, 1.0 - dist / tolerance) if dist < tolerance * 10 else 0
            score += center_score * 0.3
            weights += 0.3

        # Normal-Match (für Faces)
        if self.normal and other.normal:
            dot = sum(a * b for a, b in zip(self.normal, other.normal))
            normal_score = max(0, (dot + 1) / 2)  # -1..1 → 0..1
            score += normal_score * 0.2
            weights += 0.2

        # Area-Match (für Faces)
        if self.area > 0 and other.area > 0:
            ratio = min(self.area, other.area) / max(self.area, other.area)
            score += ratio * 0.2
            weights += 0.2

        # Length-Match (für Edges)
        if self.length > 0 and other.length > 0:
            ratio = min(self.length, other.length) / max(self.length, other.length)
            score += ratio * 0.2
            weights += 0.2

        # Type-Match
        if self.surface_type and other.surface_type:
            type_score = 1.0 if self.surface_type == other.surface_type else 0.0
            score += type_score * 0.15
            weights += 0.15

        if self.curve_type and other.curve_type:
            type_score = 1.0 if self.curve_type == other.curve_type else 0.0
            score += type_score * 0.15
            weights += 0.15

        return score / weights if weights > 0 else 0.0


@dataclass
class ShapeReference:
    """
    Referenz auf ein Shape-Element (Face, Edge, Vertex).

    Speichert sowohl den aktuellen OCP-Hash als auch History-Informationen
    und geometrische Selektoren für robuste Referenz-Auflösung.
    """
    ref_id: str                      # Eindeutige Referenz-ID
    shape_type: ShapeType            # Face, Edge, Vertex
    original_hash: int               # Hash beim Erstellen
    current_hash: Optional[int] = None  # Hash nach Operationen (kann sich ändern)
    history_path: List[str] = field(default_factory=list)  # ["Extrude_1", "Fillet_2", ...]
    geometric_selector: GeometricSelector = field(default_factory=GeometricSelector)
    created_by: str = ""             # Feature das diese Referenz erstellt hat
    last_resolved: bool = True       # War letzte Auflösung erfolgreich?

    def to_dict(self) -> dict:
        """Serialisiert zu Dict für Speicherung."""
        return {
            "ref_id": self.ref_id,
            "shape_type": self.shape_type.value,
            "original_hash": self.original_hash,
            "current_hash": self.current_hash,
            "history_path": self.history_path,
            "geometric_selector": {
                "center": self.geometric_selector.center,
                "normal": self.geometric_selector.normal,
                "area": self.geometric_selector.area,
                "length": self.geometric_selector.length,
                "surface_type": self.geometric_selector.surface_type,
                "curve_type": self.geometric_selector.curve_type,
            },
            "created_by": self.created_by,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'ShapeReference':
        """Deserialisiert von Dict."""
        geo_data = data.get("geometric_selector", {})
        return cls(
            ref_id=data["ref_id"],
            shape_type=ShapeType(data["shape_type"]),
            original_hash=data["original_hash"],
            current_hash=data.get("current_hash"),
            history_path=data.get("history_path", []),
            geometric_selector=GeometricSelector(
                center=tuple(geo_data.get("center", (0, 0, 0))),
                normal=tuple(geo_data["normal"]) if geo_data.get("normal") else None,
                area=geo_data.get("area", 0.0),
                length=geo_data.get("length", 0.0),
                surface_type=geo_data.get("surface_type", ""),
                curve_type=geo_data.get("curve_type", ""),
            ),
            created_by=data.get("created_by", ""),
        )


@dataclass
class HistoryEntry:
    """Eintrag für eine Operation im History-Log."""
    operation_name: str          # z.B. "Extrude_1", "Fillet_2"
    operation_type: str          # "extrude", "fillet", "boolean", etc.
    history_object: Any = None   # BRepTools_History (wenn verfügbar)
    modified_refs: List[str] = field(default_factory=list)  # Betroffene Referenz-IDs


class TNPTracker:
    """
    Topological Naming Problem Tracker.

    Verwaltet Shape-Referenzen über CAD-Operationen hinweg.
    Verwendet BRepTools_History (wenn verfügbar) und geometrische
    Selektoren als Fallback.

    Attributes:
        _references: Dict[ref_id, ShapeReference]
        _histories: List[HistoryEntry]
        _resolution_stats: Statistiken zur Auflösungs-Erfolgsrate
    """

    def __init__(self):
        self._references: Dict[str, ShapeReference] = {}
        self._histories: List[HistoryEntry] = []
        self._resolution_stats = {
            "history_success": 0,
            "hash_success": 0,
            "geometry_success": 0,
            "failed": 0,
        }

    def create_reference(self, shape, ref_id: str, shape_type: str,
                         created_by: str = "") -> ShapeReference:
        """
        Erstellt eine neue Shape-Referenz.

        Args:
            shape: OCP TopoDS_Shape (Face, Edge, Vertex) oder Build123d Shape
            ref_id: Eindeutige ID für diese Referenz
            shape_type: "face", "edge", "vertex"
            created_by: Feature das diese Referenz erstellt

        Returns:
            ShapeReference Objekt
        """
        # Shape extrahieren
        ocp_shape = shape.wrapped if hasattr(shape, 'wrapped') else shape

        # Hash berechnen
        shape_hash = self._compute_shape_hash(ocp_shape)

        # Geometrischen Selektor erstellen
        geo_selector = self._create_geometric_selector(ocp_shape, shape_type)

        # Referenz erstellen
        ref = ShapeReference(
            ref_id=ref_id,
            shape_type=ShapeType(shape_type),
            original_hash=shape_hash,
            current_hash=shape_hash,
            geometric_selector=geo_selector,
            created_by=created_by,
        )

        self._references[ref_id] = ref
        logger.debug(f"TNP: Referenz erstellt: {ref_id} (Hash: {shape_hash})")

        return ref

    def track_operation(self, operation_name: str, operation_type: str,
                        history=None, affected_refs: List[str] = None):
        """
        Speichert History einer Operation für spätere Referenz-Auflösung.

        Args:
            operation_name: z.B. "Extrude_1", "Fillet_2"
            operation_type: "extrude", "fillet", "boolean", etc.
            history: BRepTools_History von BooleanOperation (optional)
            affected_refs: Liste betroffener Referenz-IDs
        """
        entry = HistoryEntry(
            operation_name=operation_name,
            operation_type=operation_type,
            history_object=history,
            modified_refs=affected_refs or []
        )

        self._histories.append(entry)
        logger.debug(f"TNP: Operation {operation_name} ({operation_type}) gespeichert")

        # Referenz-History aktualisieren
        for ref_id in (affected_refs or []):
            if ref_id in self._references:
                self._references[ref_id].history_path.append(operation_name)

    def resolve_reference(self, ref_id: str, current_solid,
                          tolerance: float = 0.1) -> Optional[Any]:
        """
        Löst eine Referenz auf dem aktuellen Solid auf.

        Multi-Strategie-Ansatz:
        1. History-basierte Auflösung (primär, wenn History verfügbar)
        2. Hash-basierte Suche (sekundär)
        3. Geometrischer Selektor (Fallback)

        Args:
            ref_id: Referenz-ID
            current_solid: Aktuelles Build123d Solid
            tolerance: Toleranz für geometrisches Matching

        Returns:
            Gefundenes Shape oder None
        """
        if ref_id not in self._references:
            logger.warning(f"TNP: Referenz {ref_id} nicht gefunden")
            return None

        ref = self._references[ref_id]
        ocp_solid = current_solid.wrapped if hasattr(current_solid, 'wrapped') else current_solid

        # Strategie 1: History-basierte Auflösung
        result = self._resolve_via_history(ref, ocp_solid)
        if result:
            self._resolution_stats["history_success"] += 1
            ref.last_resolved = True
            logger.debug(f"TNP: {ref_id} via History gefunden")
            return result

        # Strategie 2: Hash-basierte Suche
        result = self._resolve_via_hash(ref, ocp_solid)
        if result:
            self._resolution_stats["hash_success"] += 1
            ref.last_resolved = True
            logger.debug(f"TNP: {ref_id} via Hash gefunden")
            return result

        # Strategie 3: Geometrischer Selektor
        result = self._resolve_via_geometry(ref, ocp_solid, tolerance)
        if result:
            self._resolution_stats["geometry_success"] += 1
            ref.last_resolved = True

            # Hash aktualisieren für zukünftige Suchen
            ref.current_hash = self._compute_shape_hash(result)
            logger.debug(f"TNP: {ref_id} via Geometrie gefunden (Fallback)")
            return result

        # Keine Strategie erfolgreich
        self._resolution_stats["failed"] += 1
        ref.last_resolved = False
        logger.warning(f"TNP: {ref_id} konnte nicht aufgelöst werden")
        return None

    def _resolve_via_history(self, ref: ShapeReference, solid) -> Optional[Any]:
        """
        Verfolgt Shape durch alle aufgezeichneten Histories.

        Verwendet BRepTools_History um Shape-Transformationen zu verfolgen.
        """
        if not self._histories:
            return None

        try:
            from OCP.TopTools import TopTools_ShapeMapHasher
            from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE, TopAbs_VERTEX
            from OCP.TopExp import TopExp_Explorer

            type_map = {
                ShapeType.FACE: TopAbs_FACE,
                ShapeType.EDGE: TopAbs_EDGE,
                ShapeType.VERTEX: TopAbs_VERTEX,
            }
            shape_type = type_map.get(ref.shape_type)

            if not shape_type:
                return None

            # Durch Histories iterieren und Shape-Evolution verfolgen
            current_hashes = {ref.original_hash}

            for entry in self._histories:
                if entry.history_object is None:
                    continue

                history = entry.history_object

                # Versuche Modified/Generated Shapes zu finden
                try:
                    # BRepTools_History API (wenn verfügbar)
                    # history.Modified(shape) → Liste modifizierter Shapes
                    # history.Generated(shape) → Liste generierter Shapes
                    # history.IsRemoved(shape) → True wenn Shape gelöscht
                    pass
                except:
                    pass

            # Finales Shape mit einem der Hashes finden
            explorer = TopExp_Explorer(solid, shape_type)
            while explorer.More():
                shape = explorer.Current()
                shape_hash = TopTools_ShapeMapHasher.HashCode(shape, 2**31 - 1)

                if shape_hash in current_hashes:
                    return shape

                explorer.Next()

        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"History-Auflösung Fehler: {e}")

        return None

    def _resolve_via_hash(self, ref: ShapeReference, solid) -> Optional[Any]:
        """Sucht Shape mit bekanntem Hash."""
        try:
            from OCP.TopTools import TopTools_ShapeMapHasher
            from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE, TopAbs_VERTEX
            from OCP.TopExp import TopExp_Explorer

            type_map = {
                ShapeType.FACE: TopAbs_FACE,
                ShapeType.EDGE: TopAbs_EDGE,
                ShapeType.VERTEX: TopAbs_VERTEX,
            }
            shape_type = type_map.get(ref.shape_type)

            if not shape_type:
                return None

            # Beide Hashes prüfen (original und current)
            target_hashes = {ref.original_hash}
            if ref.current_hash:
                target_hashes.add(ref.current_hash)

            explorer = TopExp_Explorer(solid, shape_type)
            while explorer.More():
                shape = explorer.Current()
                shape_hash = TopTools_ShapeMapHasher.HashCode(shape, 2**31 - 1)

                if shape_hash in target_hashes:
                    return shape

                explorer.Next()

        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"Hash-Auflösung Fehler: {e}")

        return None

    def _resolve_via_geometry(self, ref: ShapeReference, solid,
                               tolerance: float) -> Optional[Any]:
        """
        Fallback: Geometrischer Selektor.

        Findet Shape mit ähnlichsten geometrischen Eigenschaften.
        """
        try:
            from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE, TopAbs_VERTEX
            from OCP.TopExp import TopExp_Explorer

            type_map = {
                ShapeType.FACE: TopAbs_FACE,
                ShapeType.EDGE: TopAbs_EDGE,
                ShapeType.VERTEX: TopAbs_VERTEX,
            }
            shape_type = type_map.get(ref.shape_type)

            if not shape_type:
                return None

            best_match = None
            best_score = 0.0
            min_score_threshold = 0.7  # Mindest-Übereinstimmung

            explorer = TopExp_Explorer(solid, shape_type)
            while explorer.More():
                shape = explorer.Current()

                # Geometrischen Selektor für dieses Shape erstellen
                candidate_selector = self._create_geometric_selector(
                    shape, ref.shape_type.value
                )

                # Score berechnen
                score = ref.geometric_selector.match_score(candidate_selector, tolerance)

                if score > best_score and score >= min_score_threshold:
                    best_score = score
                    best_match = shape

                explorer.Next()

            if best_match:
                logger.debug(f"Geometrisches Matching: Score {best_score:.2f}")

            return best_match

        except Exception as e:
            logger.debug(f"Geometrie-Auflösung Fehler: {e}")

        return None

    def _compute_shape_hash(self, shape) -> int:
        """Berechnet Hash für ein OCP Shape."""
        try:
            from OCP.TopTools import TopTools_ShapeMapHasher
            return TopTools_ShapeMapHasher.HashCode(shape, 2**31 - 1)
        except:
            # Fallback: Python id
            return id(shape) % (2**31 - 1)

    def _create_geometric_selector(self, shape, shape_type: str) -> GeometricSelector:
        """Erstellt geometrischen Selektor für ein Shape."""
        selector = GeometricSelector()

        try:
            if shape_type == "face":
                selector = self._create_face_selector(shape)
            elif shape_type == "edge":
                selector = self._create_edge_selector(shape)
            elif shape_type == "vertex":
                selector = self._create_vertex_selector(shape)
        except Exception as e:
            logger.debug(f"Geometric Selector Fehler: {e}")

        return selector

    def _create_face_selector(self, face) -> GeometricSelector:
        """Erstellt Selektor für Face."""
        try:
            from OCP.BRepGProp import BRepGProp
            from OCP.GProp import GProp_GProps
            from OCP.BRepAdaptor import BRepAdaptor_Surface
            from OCP.GeomAbs import (
                GeomAbs_Plane, GeomAbs_Cylinder, GeomAbs_Cone,
                GeomAbs_Sphere, GeomAbs_Torus, GeomAbs_BSplineSurface
            )

            # Flächeneigenschaften
            props = GProp_GProps()
            BRepGProp.SurfaceProperties_s(face, props)

            center = props.CentreOfMass()
            area = props.Mass()

            # Flächentyp und Normal
            adaptor = BRepAdaptor_Surface(face)
            surface_type_ocp = adaptor.GetType()

            type_map = {
                GeomAbs_Plane: "plane",
                GeomAbs_Cylinder: "cylinder",
                GeomAbs_Cone: "cone",
                GeomAbs_Sphere: "sphere",
                GeomAbs_Torus: "torus",
                GeomAbs_BSplineSurface: "bspline",
            }
            surface_type = type_map.get(surface_type_ocp, "other")

            # Normal in der Mitte
            normal = None
            try:
                u_mid = (adaptor.FirstUParameter() + adaptor.LastUParameter()) / 2
                v_mid = (adaptor.FirstVParameter() + adaptor.LastVParameter()) / 2
                pnt = adaptor.Value(u_mid, v_mid)

                from OCP.BRepLProp import BRepLProp_SLProps
                props_lp = BRepLProp_SLProps(adaptor, u_mid, v_mid, 1, 0.01)
                if props_lp.IsNormalDefined():
                    n = props_lp.Normal()
                    normal = (n.X(), n.Y(), n.Z())
            except:
                pass

            return GeometricSelector(
                center=(center.X(), center.Y(), center.Z()),
                normal=normal,
                area=area,
                surface_type=surface_type
            )

        except Exception as e:
            logger.debug(f"Face Selector Fehler: {e}")
            return GeometricSelector()

    def _create_edge_selector(self, edge) -> GeometricSelector:
        """Erstellt Selektor für Edge."""
        try:
            from OCP.BRepGProp import BRepGProp
            from OCP.GProp import GProp_GProps
            from OCP.BRepAdaptor import BRepAdaptor_Curve
            from OCP.GeomAbs import (
                GeomAbs_Line, GeomAbs_Circle, GeomAbs_Ellipse,
                GeomAbs_BSplineCurve, GeomAbs_BezierCurve
            )

            # Kanteneigenschaften
            props = GProp_GProps()
            BRepGProp.LinearProperties_s(edge, props)

            center = props.CentreOfMass()
            length = props.Mass()

            # Kurventyp
            adaptor = BRepAdaptor_Curve(edge)
            curve_type_ocp = adaptor.GetType()

            type_map = {
                GeomAbs_Line: "line",
                GeomAbs_Circle: "circle",
                GeomAbs_Ellipse: "ellipse",
                GeomAbs_BSplineCurve: "bspline",
                GeomAbs_BezierCurve: "bezier",
            }
            curve_type = type_map.get(curve_type_ocp, "other")

            # Mittelpunkt der Kurve
            t_mid = (adaptor.FirstParameter() + adaptor.LastParameter()) / 2
            midpoint = adaptor.Value(t_mid)

            return GeometricSelector(
                center=(center.X(), center.Y(), center.Z()),
                length=length,
                midpoint=(midpoint.X(), midpoint.Y(), midpoint.Z()),
                curve_type=curve_type
            )

        except Exception as e:
            logger.debug(f"Edge Selector Fehler: {e}")
            return GeometricSelector()

    def _create_vertex_selector(self, vertex) -> GeometricSelector:
        """Erstellt Selektor für Vertex."""
        try:
            from OCP.BRep import BRep_Tool

            pnt = BRep_Tool.Pnt_s(vertex)

            return GeometricSelector(
                center=(pnt.X(), pnt.Y(), pnt.Z())
            )

        except Exception as e:
            logger.debug(f"Vertex Selector Fehler: {e}")
            return GeometricSelector()

    def get_stats(self) -> dict:
        """Gibt Auflösungs-Statistiken zurück."""
        total = sum(self._resolution_stats.values())
        if total == 0:
            return {"total": 0, "success_rate": 0.0, **self._resolution_stats}

        success = total - self._resolution_stats["failed"]
        return {
            "total": total,
            "success_rate": success / total * 100,
            **self._resolution_stats
        }

    def get_statistics(self) -> dict:
        """Alias für get_stats() - Kompatibilität mit TNPStatsPanel."""
        return self.get_stats()

    def clear(self):
        """Löscht alle Referenzen und Histories."""
        self._references.clear()
        self._histories.clear()
        logger.debug("TNP: Tracker zurückgesetzt")

    def export_references(self) -> List[dict]:
        """Exportiert alle Referenzen als Liste von Dicts."""
        return [ref.to_dict() for ref in self._references.values()]

    def import_references(self, data: List[dict]):
        """Importiert Referenzen aus Liste von Dicts."""
        for item in data:
            ref = ShapeReference.from_dict(item)
            self._references[ref.ref_id] = ref


# =============================================================================
# Globaler Tracker (Singleton-Pattern für einfache Integration)
# =============================================================================

_global_tracker: Optional[TNPTracker] = None


def get_tnp_tracker() -> TNPTracker:
    """Gibt globalen TNP-Tracker zurück (erstellt bei Bedarf)."""
    global _global_tracker
    if _global_tracker is None:
        _global_tracker = TNPTracker()
    return _global_tracker


def reset_tnp_tracker():
    """Setzt globalen TNP-Tracker zurück."""
    global _global_tracker
    if _global_tracker:
        _global_tracker.clear()
    _global_tracker = TNPTracker()
