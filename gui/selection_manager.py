"""
MashCad - Unified Selection Manager
===================================

Single Source of Truth für alle Selektionen im Viewport.
Bridged die Lücke zwischen GUI-Picking und TNP-System.

TNP v4.0 Integration:
- Erzeugt ShapeReferences aus Picking-Ergebnissen
- Löst ShapeReferences über ShapeNamingService auf
- Verwaltet multiple parallele Referenzsysteme konsistent

Author: Claude (TNP Phase 2 - GUI-Kette)
Date: 2026-02-11
"""

from typing import List, Optional, Dict, Any, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum, auto
from loguru import logger


class SelectionType(Enum):
    """Art der Selektion"""
    FACE = auto()
    EDGE = auto()
    VERTEX = auto()
    BODY = auto()


@dataclass
class SelectionItem:
    """
    Ein Selektionselement im Unified Selection Manager.
    Kann aus verschiedenen Quellen stammen (Picking, GUI, etc.).

    Unified Representation:
    - Egal ob von TNP (ShapeID), Geometrie (Fallback) oder Legacy (Index)
    - Alles wird konsistent verwaltet
    """
    item_id: str  # Eindeutige ID für diese Selektion
    selection_type: SelectionType

    # TNP v4.0: Primary Referenz (wenn verfügbar)
    shape_uuid: Optional[str] = None  # ShapeID.uuid aus ShapeNamingService

    # Legacy/GUI Referenzen (Fallback)
    face_id: Optional[int] = None  # SelectionFace.id
    edge_index: Optional[int] = None  # Topologischer Index
    body_id: Optional[str] = None

    # Geometrische Signatur (für geometrisches Fallback-Matching)
    geometric_signature: Dict[str, Any] = field(default_factory=dict)

    # Metadaten
    domain_type: Optional[str] = None  # 'body_face', 'sketch_shell', etc.
    is_valid: bool = True

    @property
    def uses_tnp(self) -> bool:
        """True wenn diese Selektion TNP-basiert ist"""
        return self.shape_uuid is not None


class SelectionManager:
    """
    Single Source of Truth für alle Viewport-Selektionen.

    Verwaltet:
    - Aktive Selektionen (Face/Edge/Vertex)
    - ShapeReference-Auflösung via TNP
    - Geometrisches Fallback wenn TNP nicht verfügbar

    Usage:
        # Selektion hinzufügen
        manager.add_selection_from_pick(face_id, body_id, domain_type)

        # Aufgelöste Shapes holen
        edges = manager.get_resolved_edges(document, body)

        # Selektionen konvertieren
        shape_ids = manager.get_shape_ids_for_feature(feature_id)
    """

    def __init__(self):
        # Aktive Selektionen (unified)
        self._selections: Dict[str, SelectionItem] = {}

        # Counter für eindeutige Item-IDs
        self._counter = 0

    def clear(self):
        """Alle Selektionen entfernen"""
        self._selections.clear()

    @property
    def selections(self) -> List[SelectionItem]:
        """Liste aller aktiven Selektionen"""
        return list(self._selections.values())

    @property
    def is_empty(self) -> bool:
        """True wenn keine Selektionen vorhanden"""
        return len(self._selections) == 0

    @property
    def count(self) -> int:
        """Anzahl der Selektionen"""
        return len(self._selections)

    # ----------------------------------------------------------------------
    # Selektion hinzufügen (aus verschiedenen Quellen)
    # ----------------------------------------------------------------------

    def add_selection_from_pick(
        self,
        face_id: int,
        body_id: str,
        domain_type: str,
        shape_uuid: Optional[str] = None,
        geometric_signature: Optional[Dict[str, Any]] = None,
    ) -> SelectionItem:
        """
        Fügt eine Selektion aus Viewport-Picking hinzu.

        Args:
            face_id: SelectionFace ID
            body_id: Owner Body ID
            domain_type: 'body_face', 'sketch_shell', etc.
            shape_uuid: Optionale ShapeID.uuid (wenn von TNP verfügbar)
            geometric_signature: Optionale geometrische Signatur für Fallback

        Returns:
            SelectionItem: Das erstellte Selektionselement
        """
        item_id = f"sel_{self._counter}"
        self._counter += 1

        item = SelectionItem(
            item_id=item_id,
            selection_type=SelectionType.FACE,
            shape_uuid=shape_uuid,
            face_id=face_id,
            body_id=body_id,
            geometric_signature=geometric_signature or {},
            domain_type=domain_type,
        )

        self._selections[item_id] = item
        logger.debug(f"[SelectionManager] Added: {domain_type} (face_id={face_id}, tnp={shape_uuid is not None})")

        return item

    def add_selection_from_shape_id(
        self,
        shape_uuid: str,
        body_id: str,
        selection_type: SelectionType,
        geometric_signature: Optional[Dict[str, Any]] = None,
    ) -> SelectionItem:
        """
        Fügt eine Selektion direkt von ShapeID hinzu.

        Usage:
            shape_id = service.get_shape_id_for_edge(edge)
            manager.add_selection_from_shape_id(shape_id.uuid, body_id, SelectionType.EDGE)
        """
        item_id = f"sel_{self._counter}"
        self._counter += 1

        item = SelectionItem(
            item_id=item_id,
            selection_type=selection_type,
            shape_uuid=shape_uuid,
            body_id=body_id,
            geometric_signature=geometric_signature or {},
        )

        self._selections[item_id] = item
        logger.debug(f"[SelectionManager] Added from ShapeID: {shape_uuid[:8]}...")

        return item

    def add_selection_from_edge_index(
        self,
        edge_index: int,
        body_id: str,
        geometric_signature: Optional[Dict[str, Any]] = None,
    ) -> SelectionItem:
        """
        Fügt eine Selektion via Edge-Index hinzu (Legacy Fallback).
        """
        item_id = f"sel_{self._counter}"
        self._counter += 1

        item = SelectionItem(
            item_id=item_id,
            selection_type=SelectionType.EDGE,
            edge_index=edge_index,
            body_id=body_id,
            geometric_signature=geometric_signature or {},
        )

        self._selections[item_id] = item
        logger.debug(f"[SelectionManager] Added from Edge Index: {edge_index}")

        return item

    # ----------------------------------------------------------------------
    # Selektionen verwalten
    # ----------------------------------------------------------------------

    def remove_selection(self, item_id: str) -> bool:
        """Entfernt eine Selektion"""
        if item_id in self._selections:
            del self._selections[item_id]
            return True
        return False

    def toggle_selection(
        self,
        face_id: int,
        body_id: str,
        domain_type: str,
        shape_uuid: Optional[str] = None,
    ) -> bool:
        """
        Toggle-Selektion (wenn schon selektiert → entfernen, sonst hinzufügen).

        Returns:
            True wenn jetzt selektiert, False wenn entfernt
        """
        # Prüfen ob schon selektiert (per face_id)
        for item in self._selections.values():
            if item.face_id == face_id and item.body_id == body_id:
                # Bereits selektiert → entfernen
                self.remove_selection(item.item_id)
                logger.debug(f"[SelectionManager] Toggled OFF: face_id={face_id}")
                return False

        # Nicht selektiert → hinzufügen
        self.add_selection_from_pick(face_id, body_id, domain_type, shape_uuid)
        return True

    def set_single_selection(
        self,
        face_id: int,
        body_id: str,
        domain_type: str,
        shape_uuid: Optional[str] = None,
    ):
        """
        Setzt eine einzelne Selektion (alle anderen entfernen).
        """
        self.clear()
        self.add_selection_from_pick(face_id, body_id, domain_type, shape_uuid)

    # ----------------------------------------------------------------------
    # TNP-Auflösung (über ShapeNamingService)
    # ----------------------------------------------------------------------

    def get_shape_ids_for_feature(self, feature_id: str, document=None) -> List[str]:
        """
        Gibt alle Shape-UUIDs zurück, die zu einem Feature gehören.

        Args:
            feature_id: Feature ID
            document: Optional document mit ShapeNamingService

        Returns:
            List of ShapeID UUIDs
        """
        if document is None:
            return []

        try:
            service = getattr(document, '_shape_naming_service', None)
            if service is None:
                return []

            shape_ids = service.get_shapes_for_feature(feature_id)
            return [sid.uuid for sid in shape_ids]
        except Exception as e:
            logger.warning(f"[SelectionManager] get_shape_ids_for_feature failed: {e}")
            return []

    def resolve_to_ocp_shapes(
        self,
        document,
        body,
        shape_type_filter: Optional[SelectionType] = None,
    ) -> List[Tuple[Any, SelectionItem]]:
        """
        Löst alle Selektionen zu OCP-Shapes auf.

        Args:
            document: Document mit ShapeNamingService
            body: Body mit build123d Solid
            shape_type_filter: Optional filter auf SelectionType

        Returns:
            List of (ocp_shape, SelectionItem) tuples
        """
        resolved = []

        service = getattr(document, '_shape_naming_service', None)
        if service is None:
            logger.debug("[SelectionManager] No ShapeNamingService - using geometric fallback only")

        solid = getattr(body, '_build123d_solid', None)
        if solid is None:
            logger.warning("[SelectionManager] Body has no solid")
            return []

        for item in self._selections.values():
            if shape_type_filter and item.selection_type != shape_type_filter:
                continue

            ocp_shape = None

            # Strategie 1: TNP-basierte Auflösung (Primary)
            if item.shape_uuid and service:
                try:
                    ocp_shape = service.resolve_shape_id(
                        item.shape_uuid,
                        solid.wrapped if hasattr(solid, 'wrapped') else solid
                    )
                    if ocp_shape:
                        logger.debug(f"[SelectionManager] Resolved {item.shape_uuid[:8]}... via TNP")
                except Exception as e:
                    logger.debug(f"[SelectionManager] TNP resolution failed: {e}")

            # Strategie 2: Geometrisches Fallback (Secondary)
            if ocp_shape is None and item.geometric_signature:
                try:
                    ocp_shape = self._resolve_via_geometry(
                        item.geometric_signature,
                        solid,
                        item.selection_type
                    )
                    if ocp_shape:
                        logger.debug(f"[SelectionManager] Resolved via geometric fallback")
                except Exception as e:
                    logger.debug(f"[SelectionManager] Geometric fallback failed: {e}")

            # Strategie 3: Index-basiert (Legacy - letzte Option)
            if ocp_shape is None and item.edge_index is not None:
                try:
                    edges = list(solid.edges())
                    if 0 <= item.edge_index < len(edges):
                        ocp_shape = edges[item.edge_index].wrapped
                        logger.debug(f"[SelectionManager] Resolved via legacy index")
                except Exception as e:
                    logger.debug(f"[SelectionManager] Legacy index resolution failed: {e}")

            if ocp_shape is not None:
                resolved.append((ocp_shape, item))
            else:
                logger.warning(f"[SelectionManager] Could not resolve selection {item.item_id}")

        return resolved

    def _resolve_via_geometry(self, signature: Dict, solid, shape_type: SelectionType) -> Optional[Any]:
        """
        Geometrisches Fallback-Matching basierend auf Signatur.

        Verwendet Center/Direction/Length Matching (40/30/20/10 Gewichtung).
        """
        if not signature:
            return None

        try:
            from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
            from OCP.GeomAbs import GeomAbs_Line, GeomAbs_Circle, GeomAbs_Plane
            from OCP.GCPnts import GCPnts_AbscissaPoint
            from OCP.BRep import BRep_Tool
            from OCP.TopExp import TopExp_Explorer
            from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
            from OCP.TopoDS import TopoDS_Edge, TopoDS_Face
            import math

            target_center = signature.get('center')
            target_direction = signature.get('direction')
            target_length = signature.get('length')

            if shape_type == SelectionType.EDGE:
                # Edge-Matching
                best_edge = None
                best_score = 0.0

                for edge in solid.edges():
                    sig = self._compute_edge_signature(edge.wrapped)
                    if sig is None:
                        continue

                    score = 0.0
                    total_weight = 0.0

                    # Center-Ähnlichkeit (40%)
                    if target_center and sig.get('center'):
                        center_dist = sum(
                            (a - b) ** 2 for a, b in zip(target_center, sig['center'])
                        ) ** 0.5
                        center_sim = max(0, 1 - center_dist / 10.0)  # 10mm Toleranz
                        score += center_sim * 0.4
                        total_weight += 0.4

                    # Direction-Ähnlichkeit (30%)
                    if target_direction and sig.get('direction'):
                        dot = sum(
                            a * b for a, b in zip(target_direction, sig['direction'])
                        )
                        dir_sim = abs(dot)
                        score += dir_sim * 0.3
                        total_weight += 0.3

                    # Length-Ähnlichkeit (30%)
                    if target_length is not None and sig.get('length'):
                        length_diff = abs(target_length - sig['length'])
                        length_sim = max(0, 1 - length_diff / 5.0)  # 5mm Toleranz
                        score += length_sim * 0.3
                        total_weight += 0.3

                    # Normalisieren
                    if total_weight > 0:
                        score /= total_weight

                    if score > best_score and score > 0.6:  # Mindest-Threshold
                        best_score = score
                        best_edge = edge

                return best_edge.wrapped if best_edge else None

            elif shape_type == SelectionType.FACE:
                # Face-Matching (Center + Normal)
                target_normal = signature.get('normal')

                best_face = None
                best_score = 0.0

                for face in solid.faces():
                    sig = self._compute_face_signature(face.wrapped)
                    if sig is None:
                        continue

                    score = 0.0

                    # Normal-Ähnlichkeit (70%)
                    if target_normal and sig.get('normal'):
                        dot = sum(
                            a * b for a, b in zip(target_normal, sig['normal'])
                        )
                        normal_sim = abs(dot)
                        score += normal_sim * 0.7

                    # Center-Ähnlichkeit (30%)
                    if target_center and sig.get('center'):
                        center_dist = sum(
                            (a - b) ** 2 for a, b in zip(target_center, sig['center'])
                        ) ** 0.5
                        center_sim = max(0, 1 - center_dist / 10.0)
                        score += center_sim * 0.3

                    if score > best_score and score > 0.6:
                        best_score = score
                        best_face = face

                return best_face.wrapped if best_face else None

        except Exception as e:
            logger.debug(f"[SelectionManager] Geometric resolution error: {e}")

        return None

    def _compute_edge_signature(self, ocp_edge) -> Optional[Dict]:
        """Berechnet geometrische Signatur einer Edge"""
        try:
            from OCP.BRepAdaptor import BRepAdaptor_Curve
            from OCP.GeomAbs import GeomAbs_Line, GeomAbs_Circle
            from OCP.GCPnts import GCPnts_AbscissaPoint
            import math

            adaptor = BRepAdaptor_Curve(ocp_edge)
            curve_type = adaptor.GetType()

            length = GCPnts_AbscissaPoint.Length_s(adaptor)

            # Erster Punkt für Direction-Berechnung
            first = adaptor.Value(0.0)
            last = adaptor.Value(length)

            center = [
                (first.X() + last.X()) / 2,
                (first.Y() + last.Y()) / 2,
                (first.Z() + last.Z()) / 2,
            ]

            direction = None
            if curve_type == GeomAbs_Line:
                # Linie: Direction ist Tangente
                tangent = adaptor.D0(0.0)
                direction = [tangent.X(), tangent.Y(), tangent.Z()]
                # Normalisieren
                d_len = math.sqrt(sum(d**2 for d in direction))
                if d_len > 1e-9:
                    direction = [d / d_len for d in direction]

            return {
                'center': center,
                'direction': direction,
                'length': length,
            }
        except Exception:
            return None

    def _compute_face_signature(self, ocp_face) -> Optional[Dict]:
        """Berechnet geometrische Signatur einer Face"""
        try:
            from OCP.BRepAdaptor import BRepAdaptor_Surface
            from OCP.BRepGProp import BRepGProp_Face
            from OCP.GProp import GProp_GProps
            import numpy as np

            # Center of Mass
            props = GProp_GProps()
            face_props = BRepGProp_Face(ocp_face)
            face_props.NormalisedProperties(props)
            center = list(props.CentreOfMass().Coord())

            # Normal an Center
            adaptor = BRepAdaptor_Surface(ocp_face)
            normal_params = props.CentreOfMass()
            # Projektiere Point auf Surface
            try:
                from OCP.GeomAPI import geomapi_ProjectPointOnSurf
                proj = geomapi_ProjectPointOnSurf(normal_params.X(), normal_params.Y(), normal_params.Z(),
                                                   adaptor.Surface().Surface(),
                                                   adaptor.FirstUParameter(), adaptor.LastUParameter(),
                                                   adaptor.FirstVParameter(), adaptor.LastVParameter())
                u, v = proj.LowerDistanceParameters()
            except Exception:
                # Fallback: FirstU/FirstV
                u = (adaptor.FirstUParameter() + adaptor.LastUParameter()) / 2
                v = (adaptor.FirstVParameter() + adaptor.LastVParameter()) / 2

            try:
                pnt = adaptor.Value(u, v)
                normal_list = []

                # Berechne Normal via D1
                try:
                    pnt_out, d1_u, d1_v = adaptor.D1(u, v)
                    # Cross product für Normal
                    nx = d1_u.Y() * d1_v.Z() - d1_u.Z() * d1_v.Y()
                    ny = d1_u.Z() * d1_v.X() - d1_u.X() * d1_v.Z()
                    nz = d1_u.X() * d1_v.Y() - d1_u.Y() * d1_v.X()
                    n_len = (nx**2 + ny**2 + nz**2) ** 0.5
                    if n_len > 1e-9:
                        normal_list = [nx / n_len, ny / n_len, nz / n_len]
                except Exception:
                    pass

                return {
                    'center': center,
                    'normal': normal_list,
                }
            except Exception:
                return None

        except Exception:
            return None

    # ----------------------------------------------------------------------
    # Convenience Methods für Edge-Selektion
    # ----------------------------------------------------------------------

    def get_selected_edges(self, document, body) -> List[Any]:
        """
        Gibt aufgelöste Edge-Shapes zurück.

        Returns:
            List von OCP Edge Shapes (oder build123d Edges)
        """
        resolved = self.resolve_to_ocp_shapes(document, body, SelectionType.EDGE)
        return [shape for shape, _ in resolved]

    def get_edge_indices(self) -> List[int]:
        """
        Gibt Edge-Indices zurück (Legacy-Kompatibilität).

        Achtung: Kann -1 enthalten wenn TNP-basiert und nicht aufgelöst!
        """
        indices = []
        for item in self._selections:
            if item.edge_index is not None:
                indices.append(item.edge_index)
            else:
                indices.append(-1)  # Marker: TNP-based, needs resolution
        return indices

    def get_face_ids(self) -> List[int]:
        """Gibt Face-IDs zurück (GUI-Kompatibilität)"""
        return [
            item.face_id for item in self._selections.values()
            if item.face_id is not None
        ]

    def get_selected_body_ids(self) -> Set[str]:
        """Gibt alle betroffenen Body-IDs zurück"""
        return {
            item.body_id for item in self._selections.values()
            if item.body_id is not None
        }


# Global instance für den Viewport
_global_selection_manager: Optional[SelectionManager] = None


def get_selection_manager() -> SelectionManager:
    """Gibt den globalen Selection Manager zurück (Singleton)"""
    global _global_selection_manager
    if _global_selection_manager is None:
        _global_selection_manager = SelectionManager()
    return _global_selection_manager
