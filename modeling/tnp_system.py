"""
TNP v4.0 - Professionelles Topological Naming System

Architektur:
- ShapeID: Persistente, eindeutige Identifikatoren für geometrische Entitäten
- ShapeNamingService: Zentrale Registry für Shape-Auflösung
- OperationGraph: Gerichteter Graph aller Operationen mit History

Design-Prinzipien:
1. Single Source of Truth: EINE Registry pro Document
2. Lazy Resolution: Shapes werden erst bei Bedarf aufgelöst
3. Immutable IDs: ShapeIDs ändern sich nie, nur ihre Zuordnung zu Geometrie
4. OCCT-Native: Verwendet BRepTools_History wo möglich
"""

from typing import Dict, List, Optional, Tuple, Any, Set
from dataclasses import dataclass, field
from enum import Enum, auto
from uuid import uuid4
import hashlib
import numpy as np
from loguru import logger
from config.feature_flags import is_enabled

# OCP Imports
try:
    from OCP.TopoDS import TopoDS_Shape, TopoDS_Edge, TopoDS_Face
    from OCP.BRepTools import BRepTools_History
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_VERTEX
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    from OCP.TopTools import TopTools_ShapeMapHasher
    HAS_OCP = True
except ImportError as e:
    HAS_OCP = False
    logger.warning(f"OCP nicht vollständig verfügbar: {e}")


class ShapeType(Enum):
    EDGE = auto()
    FACE = auto()
    VERTEX = auto()
    SOLID = auto()


@dataclass(frozen=True)
class ShapeID:
    """
    Immutable, eindeutige ID für eine geometrische Entität.
    Wird beim ERSTEN Erzeugen vergeben und ändert sich nie.
    """
    uuid: str
    shape_type: ShapeType
    feature_id: str  # ID des Features, das dieses Shape erzeugt hat
    local_index: int  # Index innerhalb des Features
    geometry_hash: str  # Hash der Geometrie (Position, Kurve, etc.)
    timestamp: float = field(default_factory=lambda: __import__('time').time())
    
    @classmethod
    def create(cls, shape_type: ShapeType, feature_id: str, local_index: int,
               geometry_data: Tuple) -> 'ShapeID':
        """Erstellt eine neue ShapeID mit eindeutigem UUID"""
        geometry_hash = hashlib.sha256(str(geometry_data).encode()).hexdigest()[:16]
        return cls(
            uuid=str(uuid4()),
            shape_type=shape_type,
            feature_id=feature_id,
            local_index=local_index,
            geometry_hash=geometry_hash
        )


@dataclass
class ShapeRecord:
    """
    Eintrag in der Registry für ein Shape.
    Enthält die aktuelle Geometrie (oder Referenz darauf).
    """
    shape_id: ShapeID
    ocp_shape: Optional[TopoDS_Shape] = None
    geometric_signature: Dict[str, Any] = field(default_factory=dict)
    is_valid: bool = True
    
    def compute_signature(self) -> Dict[str, Any]:
        """Berechnet geometrischen Fingerabdruck für schnelles Matching"""
        if self.ocp_shape is None or not HAS_OCP:
            return {}
        
        sig = {}
        
        if self.shape_id.shape_type == ShapeType.EDGE:
            try:
                from OCP.BRepAdaptor import BRepAdaptor_Curve
                from OCP.GProp import GProp_GProps
                from OCP.BRepGProp import BRepGProp
                
                adaptor = BRepAdaptor_Curve(self.ocp_shape)
                
                # Mittelpunkt
                u_mid = (adaptor.FirstParameter() + adaptor.LastParameter()) / 2
                pnt = adaptor.Value(u_mid)
                sig['center'] = (pnt.X(), pnt.Y(), pnt.Z())
                
                # Länge
                props = GProp_GProps()
                BRepGProp.LinearProperties_s(self.ocp_shape, props)
                sig['length'] = props.Mass()
                
                # Kurven-Typ
                sig['curve_type'] = str(adaptor.GetType())
                
            except Exception as e:
                logger.debug(f"Signaturberechnung fehlgeschlagen: {e}")
        
        return sig


class OperationRecord:
    """
    Eine Operation im Graph mit Input/Output Shapes.
    """
    def __init__(self, operation_type: str = "", feature_id: str = "",
                 input_shape_ids: List[ShapeID] = None,
                 output_shape_ids: List[ShapeID] = None,
                 occt_history: Optional[Any] = None,
                 manual_mappings: Dict[str, List[str]] = None,
                 metadata: Dict[str, Any] = None,
                 operation_id: str = None):  # Optional - wird generiert wenn nicht angegeben
        self.operation_id = operation_id or str(uuid4())[:8]
        self.operation_type = operation_type
        self.feature_id = feature_id
        self.input_shape_ids = input_shape_ids or []
        self.output_shape_ids = output_shape_ids or []
        self.occt_history = occt_history
        self.manual_mappings = manual_mappings or {}
        self.metadata = metadata or {}
        self.timestamp = __import__('time').time()


class ShapeNamingService:
    """
    ZENTRALE Registry für alle Shapes im Document.
    Single Source of Truth für TNP.
    """
    
    def __init__(self):
        # ShapeID -> ShapeRecord
        self._shapes: Dict[str, ShapeRecord] = {}
        
        # Operation Graph
        self._operations: List[OperationRecord] = []
        
        # Schneller Lookup: feature_id -> [ShapeIDs]
        self._by_feature: Dict[str, List[ShapeID]] = {}
        
        # Räumlicher Index für geometrisches Matching
        self._spatial_index: Dict[ShapeType, List[Tuple[np.ndarray, ShapeID]]] = {
            ShapeType.EDGE: [],
            ShapeType.FACE: [],
            ShapeType.VERTEX: []
        }
        
        if is_enabled("tnp_debug_logging"):
            logger.info("TNP v4.0 ShapeNamingService initialisiert")
    
    def register_shape(self, ocp_shape: TopoDS_Shape, shape_type: ShapeType,
                       feature_id: str, local_index: int,
                       geometry_data: Optional[Tuple] = None) -> ShapeID:
        """
        Registriert ein neu erzeugtes Shape.
        """
        # Erstelle Geometry Data für Hash falls nicht angegeben
        if geometry_data is None and HAS_OCP:
            geometry_data = self._extract_geometry_data(ocp_shape, shape_type)
        
        # Erstelle ShapeID
        shape_id = ShapeID.create(
            shape_type=shape_type,
            feature_id=feature_id,
            local_index=local_index,
            geometry_data=geometry_data or ()
        )
        
        # Erstelle Record
        record = ShapeRecord(
            shape_id=shape_id,
            ocp_shape=ocp_shape
        )
        record.geometric_signature = record.compute_signature()
        
        # Speichern
        self._shapes[shape_id.uuid] = record
        
        # Feature-Index aktualisieren
        if feature_id not in self._by_feature:
            self._by_feature[feature_id] = []
        self._by_feature[feature_id].append(shape_id)
        
        # Räumlichen Index aktualisieren
        self._update_spatial_index(shape_id, record)
        
        if is_enabled("tnp_debug_logging"):
            logger.debug(f"Shape registriert: {shape_id}")
        return shape_id
    
    def record_operation(self, operation: OperationRecord) -> None:
        """Speichert eine Operation im Graph"""
        self._operations.append(operation)
        if is_enabled("tnp_debug_logging"):
            logger.debug(f"Operation aufgezeichnet: {operation.operation_type} "
                        f"({len(operation.input_shape_ids)} in -> "
                        f"{len(operation.output_shape_ids)} out)")
    
    def find_shape_id_by_edge(self, edge: Any, tolerance: float = 0.1) -> Optional[ShapeID]:
        """
        Findet eine ShapeID für eine gegebene Edge (geometrisches Matching).
        Wird verwendet wenn ein Feature Edges auswählt - wir müssen die
        existierende ShapeID finden, nicht eine neue erstellen.
        """
        try:
            import numpy as np
            
            center = edge.center()
            edge_center = np.array([center.X, center.Y, center.Z])
            edge_length = edge.length if hasattr(edge, 'length') else 0
            
            # Suche im räumlichen Index
            best_match = None
            best_score = float('inf')
            
            for pos, shape_id in self._spatial_index[ShapeType.EDGE]:
                dist = np.linalg.norm(edge_center - pos)
                
                # Prüfe auch Länge falls verfügbar
                record = self._shapes.get(shape_id.uuid)
                length_score = 0
                if record and 'length' in record.geometric_signature and edge_length > 0:
                    stored_length = record.geometric_signature['length']
                    length_diff = abs(stored_length - edge_length)
                    length_score = length_diff * 0.1  # Gewichtung
                
                score = dist + length_score
                
                if score < best_score and dist < tolerance:
                    best_score = score
                    best_match = shape_id
            
            if best_match and is_enabled("tnp_debug_logging"):
                logger.debug(f"ShapeID gefunden für Edge: {best_match.uuid[:8]}... (score={best_score:.4f})")
            
            return best_match
            
        except Exception as e:
            logger.debug(f"ShapeID-Lookup für Edge fehlgeschlagen: {e}")
            return None
    
    def find_shape_id_by_face(self, face: Any, tolerance: float = 0.5) -> Optional[ShapeID]:
        """
        Findet eine ShapeID für eine gegebene Face (geometrisches Matching).
        Analog zu find_shape_id_by_edge, aber für Faces.
        """
        try:
            import numpy as np

            center = face.center()
            face_center = np.array([center.X, center.Y, center.Z])
            face_area = face.area if hasattr(face, 'area') else 0

            best_match = None
            best_score = float('inf')

            for pos, shape_id in self._spatial_index[ShapeType.FACE]:
                dist = np.linalg.norm(face_center - pos)

                area_score = 0
                record = self._shapes.get(shape_id.uuid)
                if record and 'area' in record.geometric_signature and face_area > 0:
                    stored_area = record.geometric_signature['area']
                    area_score = abs(stored_area - face_area) * 0.01

                score = dist + area_score

                if score < best_score and dist < tolerance:
                    best_score = score
                    best_match = shape_id

            if best_match and is_enabled("tnp_debug_logging"):
                logger.debug(f"ShapeID gefunden für Face: {best_match.uuid[:8]}... (score={best_score:.4f})")

            return best_match

        except Exception as e:
            logger.debug(f"ShapeID-Lookup für Face fehlgeschlagen: {e}")
            return None

    def resolve_shape(self, shape_id: ShapeID,
                      current_solid: Any,
                      *,
                      log_unresolved: bool = True) -> Optional[Any]:
        """
        Löst eine ShapeID zur aktuellen Geometrie auf.
        
        Strategien (in Reihenfolge):
        1. Direkter Lookup (wenn Shape unverändert)
        2. History Tracing (via OCCT History)
        3. BRepFeat Mapping Lookup
        4. Geometric Matching (Fallback)
        """
        resolved, _method = self.resolve_shape_with_method(
            shape_id,
            current_solid,
            log_unresolved=log_unresolved,
        )
        return resolved

    def resolve_shape_with_method(self, shape_id: ShapeID,
                                  current_solid: Any,
                                  *,
                                  log_unresolved: bool = True) -> Tuple[Optional[Any], str]:
        """
        Löst eine ShapeID auf und gibt auch die verwendete Methode zurück.

        Returns:
            (resolved_shape, method) wobei method eines von:
            "direct", "history", "brepfeat", "geometric", "unresolved"
        """
        if shape_id.uuid not in self._shapes:
            if log_unresolved:
                logger.warning(f"Unbekannte ShapeID: {shape_id.uuid}")
            return None, "unresolved"
        
        record = self._shapes[shape_id.uuid]
        
        # Strategie 1: Direkter Lookup
        if record.is_valid and record.ocp_shape is not None:
            if self._shape_exists_in_solid(record.ocp_shape, current_solid):
                logger.debug(f"Shape {shape_id.uuid[:8]} direkt gefunden")
                return record.ocp_shape, "direct"
        
        # Strategie 2: History Tracing
        resolved = self._trace_via_history(shape_id, current_solid)
        if resolved:
            logger.debug(f"Shape {shape_id.uuid[:8]} via History gefunden")
            return resolved, "history"
        
        # Strategie 3: BRepFeat Mapping Lookup
        resolved = self._lookup_brepfeat_mapping(shape_id, current_solid)
        if resolved:
            logger.debug(f"Shape {shape_id.uuid[:8]} via BRepFeat Mapping gefunden")
            return resolved, "brepfeat"
        
        # Strategie 4: Geometric Matching (Fallback)
        resolved = self._match_geometrically(shape_id, current_solid)
        if resolved:
            logger.debug(f"Shape {shape_id.uuid[:8]} via Geometric Matching gefunden")
            return resolved, "geometric"
        
        if log_unresolved:
            logger.warning(f"Shape {shape_id.uuid[:8]} konnte nicht aufgelöst werden")
        return None, "unresolved"
    
    def get_shapes_by_feature(self, feature_id: str) -> List[ShapeID]:
        """Gibt alle Shapes zurück, die ein Feature erzeugt hat"""
        return self._by_feature.get(feature_id, [])
    
    def get_last_operation(self) -> Optional[OperationRecord]:
        """Gibt die letzte Operation zurück"""
        return self._operations[-1] if self._operations else None
    
    def get_stats(self) -> Dict[str, int]:
        """Statistiken für Debugging"""
        return {
            'total_shapes': len(self._shapes),
            'operations': len(self._operations),
            'features': len(self._by_feature),
            'edges': len(self._spatial_index[ShapeType.EDGE]),
            'faces': len(self._spatial_index[ShapeType.FACE])
        }

    _CONSUMING_FEATURE_TYPES = frozenset([
        'FilletFeature', 'ChamferFeature',
    ])

    def get_health_report(self, body) -> Dict[str, Any]:
        """
        Erstellt einen Gesundheitsbericht für einen Body.

        Prüft alle Features mit TNP-Referenzen (edge_shape_ids, face_shape_ids)
        und testet ob die ShapeIDs noch auflösbar sind.

        Konsumierende Features (Fillet/Chamfer) zerstören ihre Input-Kanten
        absichtlich. Deren Status wird aus dem letzten Rebuild übernommen
        (feature.status), da die Referenzen nur VOR der Operation gültig sind.
        """
        report = {
            'body_name': getattr(body, 'name', 'Body'),
            'status': 'ok',
            'ok': 0, 'fallback': 0, 'broken': 0,
            'features': []
        }

        features = getattr(body, 'features', [])
        current_solid = getattr(body, '_build123d_solid', None)

        ocp_solid = None
        if current_solid is not None:
            ocp_solid = current_solid.wrapped if hasattr(current_solid, 'wrapped') else current_solid

        face_from_index = None
        edge_from_index = None
        try:
            from modeling.topology_indexing import (
                face_from_index as _face_from_index,
                edge_from_index as _edge_from_index,
            )
            face_from_index = _face_from_index
            edge_from_index = _edge_from_index
        except Exception:
            pass

        def _to_list(value: Any) -> List[Any]:
            if value is None:
                return []
            if isinstance(value, list):
                return list(value)
            if isinstance(value, tuple):
                return list(value)
            return [value]

        def _to_index_list(value: Any) -> List[Optional[int]]:
            result: List[Optional[int]] = []
            for raw_idx in _to_list(value):
                try:
                    idx = int(raw_idx)
                    result.append(idx if idx >= 0 else None)
                except Exception:
                    result.append(None)
            return result

        def _collect_ref_groups(feat: Any) -> List[Tuple[str, List[Any], List[Optional[int]]]]:
            groups: List[Tuple[str, List[Any], List[Optional[int]]]] = []

            edge_shape_ids = _to_list(getattr(feat, "edge_shape_ids", []))
            edge_indices = _to_index_list(getattr(feat, "edge_indices", []))
            if edge_shape_ids or edge_indices:
                groups.append(("Edge", edge_shape_ids, edge_indices))

            face_shape_ids = _to_list(getattr(feat, "face_shape_ids", []))
            face_indices = _to_index_list(getattr(feat, "face_indices", []))
            if face_shape_ids or face_indices:
                groups.append(("Face", face_shape_ids, face_indices))

            opening_face_shape_ids = _to_list(getattr(feat, "opening_face_shape_ids", []))
            opening_face_indices = _to_index_list(getattr(feat, "opening_face_indices", []))
            if opening_face_shape_ids or opening_face_indices:
                groups.append(("Face", opening_face_shape_ids, opening_face_indices))

            single_face_shape_id = getattr(feat, "face_shape_id", None)
            single_face_index = getattr(feat, "face_index", None)
            if single_face_shape_id is not None or single_face_index is not None:
                groups.append((
                    "Face",
                    _to_list(single_face_shape_id),
                    _to_index_list(single_face_index),
                ))

            return groups

        def _resolve_index_ref(ref_kind: str, topo_index: Optional[int]) -> bool:
            if topo_index is None or current_solid is None:
                return False
            try:
                if ref_kind == "Face" and face_from_index is not None:
                    return face_from_index(current_solid, topo_index) is not None
                if ref_kind == "Edge" and edge_from_index is not None:
                    return edge_from_index(current_solid, topo_index) is not None
            except Exception:
                return False
            return False

        for feat in features:
            feat_type_name = type(feat).__name__
            is_consuming = feat_type_name in self._CONSUMING_FEATURE_TYPES

            feat_report = {
                'name': getattr(feat, 'name', 'Feature'),
                'type': feat_type_name.replace('Feature', ''),
                'status': 'no_refs',
                'ok': 0, 'fallback': 0, 'broken': 0,
                'consuming': is_consuming,
                'refs': []
            }

            ref_groups = _collect_ref_groups(feat)
            if not ref_groups:
                report['features'].append(feat_report)
                continue

            if is_consuming:
                rebuild_status = getattr(feat, 'status', 'OK')
                for ref_kind, shape_ids, index_refs in ref_groups:
                    ref_count = max(
                        len(shape_ids),
                        len(index_refs),
                        sum(1 for sid in shape_ids if isinstance(sid, ShapeID)),
                        sum(1 for idx in index_refs if idx is not None),
                    )
                    if ref_count <= 0:
                        continue

                    if rebuild_status in ('OK', 'SUCCESS', 'WARNING'):
                        feat_report['ok'] += ref_count
                        report['ok'] += ref_count
                        ref_status = 'ok'
                    else:
                        feat_report['broken'] += ref_count
                        report['broken'] += ref_count
                        ref_status = 'broken'

                    for _ in range(ref_count):
                        feat_report['refs'].append({
                            'kind': ref_kind,
                            'status': ref_status,
                            'method': 'rebuild'
                        })
            else:
                for ref_kind, shape_ids, index_refs in ref_groups:
                    ref_count = max(len(shape_ids), len(index_refs))
                    for ref_idx in range(ref_count):
                        topo_index = index_refs[ref_idx] if ref_idx < len(index_refs) else None
                        shape_id = shape_ids[ref_idx] if ref_idx < len(shape_ids) else None

                        if _resolve_index_ref(ref_kind, topo_index):
                            status = "ok"
                            method = "index"
                        elif isinstance(shape_id, ShapeID):
                            if ocp_solid is not None:
                                _resolved, method = self.resolve_shape_with_method(
                                    shape_id,
                                    ocp_solid,
                                    log_unresolved=False,
                                )
                            else:
                                method = "unresolved"

                            if method in ("direct", "history"):
                                status = "ok"
                            elif method in ("brepfeat", "geometric"):
                                status = "fallback"
                            else:
                                status = "broken"
                        elif topo_index is not None:
                            status = "broken"
                            method = "index"
                        else:
                            continue

                        if status == "ok":
                            feat_report['ok'] += 1
                            report['ok'] += 1
                        elif status == "fallback":
                            feat_report['fallback'] += 1
                            report['fallback'] += 1
                        else:
                            feat_report['broken'] += 1
                            report['broken'] += 1

                        feat_report['refs'].append({
                            'kind': ref_kind,
                            'status': status,
                            'method': method
                        })

            if feat_report['broken'] > 0:
                feat_report['status'] = 'broken'
            elif feat_report['fallback'] > 0:
                feat_report['status'] = 'fallback'
            elif feat_report['ok'] > 0:
                feat_report['status'] = 'ok'

            report['features'].append(feat_report)

        if report['broken'] > 0:
            report['status'] = 'broken'
        elif report['fallback'] > 0:
            report['status'] = 'fallback'

        return report

    def invalidate_feature(self, feature_id: str) -> None:
        """Remove all shapes from a feature (for undo/rebuild)."""
        if feature_id in self._by_feature:
            for shape_id in self._by_feature[feature_id]:
                if shape_id.uuid in self._shapes:
                    del self._shapes[shape_id.uuid]
            del self._by_feature[feature_id]

            # Rebuild spatial index (remove stale entries)
            for shape_type_key in self._spatial_index:
                self._spatial_index[shape_type_key] = [
                    (pos, sid) for pos, sid in self._spatial_index[shape_type_key]
                    if sid.feature_id != feature_id
                ]

            if is_enabled("tnp_debug_logging"):
                logger.info(f"TNP: Feature '{feature_id}' invalidiert")

    def compact(self, current_solid: Any) -> int:
        """Remove all shapes that no longer exist in the current solid."""
        to_remove = []
        for uuid, record in self._shapes.items():
            if record.ocp_shape and not self._shape_exists_in_solid(record.ocp_shape, current_solid):
                to_remove.append(uuid)

        for uuid in to_remove:
            feat_id = self._shapes[uuid].shape_id.feature_id
            del self._shapes[uuid]
            if feat_id in self._by_feature:
                self._by_feature[feat_id] = [
                    sid for sid in self._by_feature[feat_id] if sid.uuid != uuid
                ]

        # Rebuild spatial index
        if to_remove:
            removed_set = set(to_remove)
            for shape_type_key in self._spatial_index:
                self._spatial_index[shape_type_key] = [
                    (pos, sid) for pos, sid in self._spatial_index[shape_type_key]
                    if sid.uuid not in removed_set
                ]

        if is_enabled("tnp_debug_logging"):
            logger.info(f"TNP compact: {len(to_remove)} stale Shapes entfernt")
        return len(to_remove)

    def register_solid_edges(self, solid: Any, feature_id: str) -> int:
        """Register ALL edges from a solid. Uses IndexedMap for dedup."""
        if not HAS_OCP:
            return 0

        try:
            from OCP.TopTools import TopTools_IndexedMapOfShape
            from OCP.TopExp import TopExp
            from OCP.TopoDS import TopoDS

            solid_wrapped = solid.wrapped if hasattr(solid, 'wrapped') else solid
            edge_map = TopTools_IndexedMapOfShape()
            TopExp.MapShapes_s(solid_wrapped, TopAbs_EDGE, edge_map)

            count = 0
            for i in range(1, edge_map.Extent() + 1):
                edge = TopoDS.Edge_s(edge_map.FindKey(i))
                self.register_shape(edge, ShapeType.EDGE, feature_id, i - 1)
                count += 1

            if is_enabled("tnp_debug_logging"):
                logger.info(f"TNP: {count} Edges für Feature '{feature_id}' registriert")
            return count
        except Exception as e:
            logger.warning(f"register_solid_edges fehlgeschlagen: {e}")
            return 0

    # === Private Helper ===

    def _extract_geometry_data(self, ocp_shape: TopoDS_Shape,
                               shape_type: ShapeType) -> Tuple:
        """Extrahiert Geometriedaten für Hashing"""
        if not HAS_OCP:
            return ()
        
        try:
            if shape_type == ShapeType.EDGE:
                from OCP.BRepAdaptor import BRepAdaptor_Curve
                from OCP.GProp import GProp_GProps
                from OCP.BRepGProp import BRepGProp
                
                adaptor = BRepAdaptor_Curve(ocp_shape)
                u_mid = (adaptor.FirstParameter() + adaptor.LastParameter()) / 2
                pnt = adaptor.Value(u_mid)
                
                props = GProp_GProps()
                BRepGProp.LinearProperties_s(ocp_shape, props)
                
                return (pnt.X(), pnt.Y(), pnt.Z(), props.Mass())
            
            elif shape_type == ShapeType.FACE:
                from OCP.BRepGProp import BRepGProp
                from OCP.GProp import GProp_GProps
                
                props = GProp_GProps()
                BRepGProp.SurfaceProperties_s(ocp_shape, props)
                
                center = props.CentreOfMass()
                return (center.X(), center.Y(), center.Z(), props.Mass())
        
        except Exception as e:
            logger.debug(f"Geometriedaten-Extraktion fehlgeschlagen: {e}")
        
        return ()
    
    def _update_spatial_index(self, shape_id: ShapeID, record: ShapeRecord):
        """Aktualisiert den räumlichen Index"""
        if 'center' in record.geometric_signature:
            center = np.array(record.geometric_signature['center'])
            self._spatial_index[shape_id.shape_type].append((center, shape_id))
    
    def _shape_exists_in_solid(self, ocp_shape: TopoDS_Shape,
                               current_solid: Any) -> bool:
        """Prüft ob ein Shape noch im aktuellen Solid existiert.

        Verwendet OCCT IndexedMap für korrekte TShape-basierte Identität.
        """
        if current_solid is None:
            return False

        try:
            from OCP.TopTools import TopTools_IndexedMapOfShape
            from OCP.TopExp import TopExp

            shape_type = ocp_shape.ShapeType()
            solid_wrapped = current_solid.wrapped if hasattr(current_solid, 'wrapped') else current_solid

            shape_map = TopTools_IndexedMapOfShape()
            TopExp.MapShapes_s(solid_wrapped, shape_type, shape_map)

            return shape_map.Contains(ocp_shape)
        except Exception:
            return False
    
    def _trace_via_history(self, shape_id: ShapeID, 
                          current_solid: Any) -> Optional[Any]:
        """
        Level 2: Versucht Shape via Operation-Graph zu tracen.
        Folgt der Kette: ShapeID → Operation → Mapped Shapes
        """
        if not self._operations:
            return None
        
        try:
            # Finde die Operation, die dieses Shape erzeugt hat
            for op in reversed(self._operations):
                if shape_id in op.output_shape_ids:
                    # Prüfe ob OCCT History verfügbar
                    if op.occt_history and HAS_OCP:
                        try:
                            from OCP.BRepTools import BRepTools_History
                            from OCP.TopAbs import TopAbs_EDGE
                            
                            if isinstance(op.occt_history, BRepTools_History):
                                # Query the history
                                generated = op.occt_history.Generated(shape_id)
                                modified = op.occt_history.Modified(shape_id)
                                
                                if generated and generated.Size() > 0:
                                    return generated.First()
                                elif modified and modified.Size() > 0:
                                    return modified.First()
                        except Exception as e:
                            logger.debug(f"OCCT History Query fehlgeschlagen: {e}")
                    
                    # Prüfe manual_mappings (für BRepFeat)
                    if op.manual_mappings and shape_id.uuid in op.manual_mappings:
                        mapped_ids = op.manual_mappings[shape_id.uuid]
                        if mapped_ids:
                            # Nimm erstes gemapptes Shape
                            mapped_record = self._shapes.get(mapped_ids[0])
                            if mapped_record and mapped_record.ocp_shape:
                                return mapped_record.ocp_shape
        
        except Exception as e:
            logger.debug(f"History Tracing fehlgeschlagen: {e}")
        
        return None
    
    def _lookup_brepfeat_mapping(self, shape_id: ShapeID,
                                 current_solid: Any) -> Optional[Any]:
        """
        Level 3: Sucht in BRepFeat manual_mappings.
        Für Push/Pull Operationen: finde welche neue Edge zur alten gehört.
        """
        try:
            import numpy as np
            
            # Durchsuche alle Operationen nach Mappings
            for op in reversed(self._operations):
                if op.operation_type == "BREPFEAT_PRISM" and op.manual_mappings:
                    # Prüfe ob unsere ShapeID als Input in dieser Operation war
                    if shape_id.uuid in op.manual_mappings:
                        mapped_uuids = op.manual_mappings[shape_id.uuid]
                        
                        # Finde die gemappten Shapes im aktuellen Solid
                        for mapped_uuid in mapped_uuids:
                            mapped_record = self._shapes.get(mapped_uuid)
                            if mapped_record and 'center' in mapped_record.geometric_signature:
                                # Suche im aktuellen Solid nach dieser Position
                                target_center = np.array(mapped_record.geometric_signature['center'])
                                target_length = mapped_record.geometric_signature.get('length', 0)
                                
                                for edge in current_solid.edges():
                                    center = edge.center()
                                    edge_center = np.array([center.X, center.Y, center.Z])
                                    dist = np.linalg.norm(target_center - edge_center)
                                    
                                    # Prüfe auch Länge
                                    length_ok = True
                                    if target_length > 0 and hasattr(edge, 'length'):
                                        length_diff = abs(edge.length - target_length)
                                        length_ok = length_diff < 0.5  # 0.5mm Toleranz
                                    
                                    if dist < 0.5 and length_ok:  # 0.5mm Toleranz
                                        return edge.wrapped
        
        except Exception as e:
            logger.debug(f"BRepFeat Mapping Lookup fehlgeschlagen: {e}")
        
        return None
    
    def _match_geometrically(self, shape_id: ShapeID, 
                            current_solid: Any) -> Optional[Any]:
        """
        Level 4: Findet Shape via geometrischen Signaturen (Fallback).
        Verwendet Position, Länge und Kurventyp.
        """
        if shape_id.uuid not in self._shapes:
            return None
        
        record = self._shapes[shape_id.uuid]
        if 'center' not in record.geometric_signature:
            return None
        
        target_center = np.array(record.geometric_signature['center'])
        target_length = record.geometric_signature.get('length', 0)
        target_type = record.geometric_signature.get('curve_type', '')
        
        best_match = None
        best_score = float('inf')
        
        try:
            # current_solid kann Build123d Solid ODER OCP TopoDS_Shape sein
            if hasattr(current_solid, 'edges'):
                solid_for_iteration = current_solid
            else:
                # OCP Shape → zu Build123d wrappen für .edges()
                try:
                    from build123d import Solid, Shape
                    try:
                        solid_for_iteration = Solid(current_solid)
                    except Exception:
                        solid_for_iteration = Shape(current_solid)
                except Exception:
                    return None

            if shape_id.shape_type == ShapeType.EDGE:
                for edge in solid_for_iteration.edges():
                    center = edge.center()
                    edge_center = np.array([center.X, center.Y, center.Z])
                    
                    # Distanz-Score (wichtigster Faktor)
                    dist = np.linalg.norm(target_center - edge_center)
                    
                    # Längen-Score
                    length_score = 0
                    if target_length > 0 and hasattr(edge, 'length'):
                        length_diff = abs(edge.length - target_length)
                        if target_length > 0:
                            length_score = (length_diff / target_length) * 5  # Gewichtung
                    
                    # Kurven-Typ Score (Bonus für gleichen Typ)
                    type_score = 0
                    if target_type and hasattr(edge, 'geom_type'):
                        if str(edge.geom_type) != target_type:
                            type_score = 2  # Penalty für unterschiedlichen Typ
                    
                    score = dist + length_score + type_score
                    
                    if score < best_score and dist < 1.0:  # 1mm Distanz-Toleranz
                        best_score = score
                        best_match = edge.wrapped
                
                if best_match:
                    logger.debug(f"Geometric Match Score: {best_score:.3f}mm")
        
        except Exception as e:
            logger.debug(f"Geometrisches Matching fehlgeschlagen: {e}")
        
        return best_match

    def track_brepfeat_operation(self, feature_id: str, 
                                  source_solid: Any,
                                  result_solid: Any,
                                  modified_face: Any,
                                  direction: Tuple[float, float, float],
                                  distance: float) -> Optional[OperationRecord]:
        """
        TNP v4.0: Trackt eine BRepFeat_MakePrism Operation.
        
        BRepFeat ändert die Topologie des Solids - Faces werden verschoben,
        neue Edges entstehen. Diese Methode erstellt Mappings von alten
        zu neuen ShapeIDs.
        
        Args:
            feature_id: ID des Push/Pull Features
            source_solid: Das Solid vor der Operation
            result_solid: Das Solid nach der Operation
            modified_face: Die Face die gepusht/pulled wurde
            direction: Extrusionsrichtung
            distance: Extrusionsdistanz
            
        Returns:
            OperationRecord mit Mappings, oder None
        """
        if not HAS_OCP:
            return None
        
        try:
            import numpy as np
            from OCP.TopExp import TopExp_Explorer
            from OCP.TopAbs import TopAbs_EDGE
            from OCP.TopoDS import TopoDS
            
            if is_enabled("tnp_debug_logging"):
                logger.info(f"TNP v4.0: Tracke BRepFeat Operation '{feature_id}'")
            
            # 1. Finde alle Edges der modified_face vor der Operation
            old_face_edges = set()
            face_edge_exp = TopExp_Explorer(modified_face.wrapped, TopAbs_EDGE)
            while face_edge_exp.More():
                edge = TopoDS.Edge_s(face_edge_exp.Current())
                old_face_edges.add(edge)
                face_edge_exp.Next()
            
            # 2. Sammle ShapeIDs die zu den Edges der modified_face gehören
            # Wir können OCP Shapes nicht direkt vergleichen, daher nutzen wir geometrische Signaturen
            affected_shape_ids = []
            
            # Extrahiere Centers von allen Edges der modified_face
            modified_face_centers = []
            face_edge_exp = TopExp_Explorer(modified_face.wrapped, TopAbs_EDGE)
            while face_edge_exp.More():
                edge = TopoDS.Edge_s(face_edge_exp.Current())
                # Berechne Center dieser Edge
                try:
                    from OCP.BRepAdaptor import BRepAdaptor_Curve
                    from OCP.GProp import GProp_GProps
                    from OCP.BRepGProp import BRepGProp
                    
                    adaptor = BRepAdaptor_Curve(edge)
                    u_mid = (adaptor.FirstParameter() + adaptor.LastParameter()) / 2
                    pnt = adaptor.Value(u_mid)
                    
                    props = GProp_GProps()
                    BRepGProp.LinearProperties_s(edge, props)
                    length = props.Mass()
                    
                    modified_face_centers.append((np.array([pnt.X(), pnt.Y(), pnt.Z()]), length))
                except Exception as e:
                    logger.debug(f"[tnp_system.py] Fehler: {e}")
                    pass
                face_edge_exp.Next()
            
            # Finde ShapeIDs die zu diesen Positionen passen
            for shape_id, record in self._shapes.items():
                if record.shape_id.shape_type != ShapeType.EDGE:
                    continue
                    
                if 'center' not in record.geometric_signature:
                    continue
                
                record_center = np.array(record.geometric_signature['center'])
                record_length = record.geometric_signature.get('length', 0)
                
                # Prüfe ob diese Edge nahe einer der modified_face Edges ist
                # WICHTIG: Bei Push/Pull werden Edges verlängert, daher nur Center prüfen
                # (nicht Länge - die ändert sich bei BRepFeat)
                for face_center, face_length in modified_face_centers:
                    dist = np.linalg.norm(record_center - face_center)

                    # Center muss nah sein (0.1mm CAD-Standard), aber Länge ignorieren
                    # da BRepFeat die Seiten-Edges verlängert
                    if dist < 0.1:
                        affected_shape_ids.append(record.shape_id)
                        break
            
            if is_enabled("tnp_debug_logging"):
                logger.debug(f"TNP BRepFeat: {len(affected_shape_ids)}/{len(modified_face_centers)} betroffene Edges gefunden")
            
            # 3. Extrahiere alle Edges vom neuen Solid
            new_edges = list(result_solid.edges())
            
            # 4. Erstelle Mappings: Alte Edge → Neue Edge
            manual_mappings = {}  # {old_shape_uuid: [new_shape_uuid, ...]}
            new_shape_ids = []
            
            # Richtung als Vektor
            dir_vec = np.array(direction)
            
            for old_shape_id in affected_shape_ids:
                old_record = self._shapes.get(old_shape_id.uuid)
                if not old_record or 'center' not in old_record.geometric_signature:
                    continue
                
                old_center = np.array(old_record.geometric_signature['center'])
                old_length = old_record.geometric_signature.get('length', 0)
                
                # Suche nach der neuen Edge die zur alten passt
                # Die neue Edge ist um 'distance' in 'direction' verschoben
                best_match = None
                best_score = float('inf')
                
                for i, new_edge in enumerate(new_edges):
                    new_center = np.array([
                        new_edge.center().X,
                        new_edge.center().Y,
                        new_edge.center().Z
                    ])
                    new_length = new_edge.length if hasattr(new_edge, 'length') else 0
                    
                    # Berechne erwartete neue Position
                    # Bei BRepFeat wird die Face verschoben, daher sind die 
                    # äußeren Edges um 'distance' verschoben
                    expected_shift = dir_vec * distance
                    expected_center = old_center + expected_shift
                    
                    # Distanz zur erwarteten Position
                    dist_to_expected = np.linalg.norm(new_center - expected_center)
                    
                    # Aber: Die Face-Edges bleiben gleich! Nur die "Seiten"-Edges sind neu
                    # Daher auch prüfen ob Edge nahe der alten Position ist (für Face-Edges)
                    dist_to_old = np.linalg.norm(new_center - old_center)
                    
                    # Verwende Minimum der Distanzen
                    dist = min(dist_to_expected, dist_to_old)
                    
                    # Längen-Vergleich
                    length_diff = abs(new_length - old_length)
                    length_score = length_diff * 0.1
                    
                    score = dist + length_score
                    
                    if score < best_score and dist < 1.0:  # 1mm Toleranz
                        best_score = score
                        best_match = (i, new_edge)
                
                if best_match:
                    idx, matched_edge = best_match
                    
                    # Erstelle neue ShapeID für die gematchte Edge
                    new_shape_id = self.register_shape(
                        ocp_shape=matched_edge.wrapped,
                        shape_type=ShapeType.EDGE,
                        feature_id=feature_id,
                        local_index=len(new_shape_ids)
                    )
                    
                    new_shape_ids.append(new_shape_id)
                    
                    # Mapping erstellen
                    if old_shape_id.uuid not in manual_mappings:
                        manual_mappings[old_shape_id.uuid] = []
                    manual_mappings[old_shape_id.uuid].append(new_shape_id.uuid)

                    if is_enabled("tnp_debug_logging"):
                        logger.debug(f"TNP BRepFeat: Mapped {old_shape_id.uuid[:8]} → {new_shape_id.uuid[:8]} (score={best_score:.3f})")

            # === Phase 3: Registriere alle neuen Edges (z.B. Side-Edges von Extrusion) ===
            # BUG FIX: Korrekte Iteration über manual_mappings.items()
            mappings_for_unmapped = []
            if manual_mappings:
                for old_uuid, new_uuid_or_list in manual_mappings.items():
                    if isinstance(new_uuid_or_list, list):
                        # Liste von neuen UUIDs
                        for new_uuid in new_uuid_or_list:
                            mappings_for_unmapped.append(
                                type('Mapping', (), {'new_shape_uuid': new_uuid})()
                            )
                    elif isinstance(new_uuid_or_list, str):
                        # Einzelne UUID
                        mappings_for_unmapped.append(
                            type('Mapping', (), {'new_shape_uuid': new_uuid_or_list})()
                        )

            new_edge_count = self._register_unmapped_edges(
                result_solid=result_solid,
                feature_id=feature_id,
                existing_mappings=mappings_for_unmapped
            )

            if is_enabled("tnp_debug_logging"):
                logger.info(f"TNP BRepFeat: {len(manual_mappings)} mappings + {new_edge_count} neue Edges registriert")

            # 5. Erstelle OperationRecord
            if manual_mappings:
                op_record = OperationRecord(
                    operation_type="BREPFEAT_PRISM",
                    feature_id=feature_id,
                    input_shape_ids=affected_shape_ids,
                    output_shape_ids=new_shape_ids,
                    manual_mappings=manual_mappings,
                    metadata={
                        'direction': direction,
                        'distance': distance,
                        'mappings_count': len(manual_mappings)
                    }
                )
                
                self.record_operation(op_record)
                
                total_edges = len(manual_mappings) + new_edge_count
                if is_enabled("tnp_debug_logging"):
                    logger.success(f"TNP v4.0: BRepFeat Operation getrackt - {len(manual_mappings)} mappings + {new_edge_count} neue Edges = {total_edges} total")
                return op_record
            else:
                if is_enabled("tnp_debug_logging"):
                    logger.warning("TNP v4.0: Keine BRepFeat Mappings erstellt")
                return None
                
        except Exception as e:
            if is_enabled("tnp_debug_logging"):
                logger.error(f"TNP v4.0: BRepFeat Tracking fehlgeschlagen: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _register_unmapped_edges(self, result_solid, feature_id: str, existing_mappings: List) -> int:
        """
        Registriert alle Edges im Result-Solid die noch kein Mapping haben.

        Verwendet OCCT-native TopTools_IndexedMapOfShape für korrekte
        Shape-Identität (TShape pointer equality) statt fragiler Hash-Vergleiche.

        Returns:
            Anzahl neu registrierter Edges
        """
        if not HAS_OCP:
            return 0

        try:
            from OCP.TopTools import TopTools_IndexedMapOfShape
            from OCP.TopExp import TopExp, TopExp_Explorer
            from OCP.TopAbs import TopAbs_EDGE
            from OCP.TopoDS import TopoDS

            result_shape = result_solid.wrapped if hasattr(result_solid, 'wrapped') else result_solid

            # 1. Build map of ALL already-known edges (from registry)
            known_edges_map = TopTools_IndexedMapOfShape()
            for record in self._shapes.values():
                if record.shape_id.shape_type == ShapeType.EDGE and record.ocp_shape:
                    known_edges_map.Add(record.ocp_shape)

            if is_enabled("tnp_debug_logging"):
                # Count edges in result
                result_edge_map = TopTools_IndexedMapOfShape()
                TopExp.MapShapes_s(result_shape, TopAbs_EDGE, result_edge_map)
                logger.debug(f"[TNP] _register_unmapped_edges: {result_edge_map.Extent()} unique Edges in result, "
                           f"{known_edges_map.Extent()} already known")

            # 2. Iterate result solid edges using IndexedMap for dedup
            explorer = TopExp_Explorer(result_shape, TopAbs_EDGE)
            new_count = 0
            local_index = 0

            while explorer.More():
                edge = TopoDS.Edge_s(explorer.Current())

                if not known_edges_map.Contains(edge):
                    # Truly new edge → register
                    shape_id = self.register_shape(
                        ocp_shape=edge,
                        shape_type=ShapeType.EDGE,
                        feature_id=feature_id,
                        local_index=local_index
                    )
                    known_edges_map.Add(edge)  # prevent double-registration
                    new_count += 1
                    local_index += 1

                    if is_enabled("tnp_debug_logging"):
                        logger.debug(f"[TNP] Neue Edge registriert: {shape_id.uuid[:8]}")

                explorer.Next()

            if is_enabled("tnp_debug_logging"):
                logger.info(f"[TNP] _register_unmapped_edges: {new_count} neue Edges registriert")
            return new_count

        except Exception as e:
            logger.warning(f"_register_unmapped_edges fehlgeschlagen: {e}")
            return 0


# Globaler Service für Document
# Wird in Document.__init__ erstellt
_document_services: Dict[str, ShapeNamingService] = {}


def get_naming_service(document_id: str) -> ShapeNamingService:
    """Gibt oder erstellt den NamingService für ein Document"""
    if document_id not in _document_services:
        _document_services[document_id] = ShapeNamingService()
    return _document_services[document_id]


def _safe_shape_hash(shape) -> int:
    """Safe shape hashing that works across OCP versions."""
    try:
        return TopTools_ShapeMapHasher.HashCode_s(shape, 2**31 - 1)
    except AttributeError:
        try:
            return shape.HashCode(2**31 - 1)
        except AttributeError:
            return id(shape)


# Backward-Compatibility Aliases (für schrittweise Migration)
# Alte Klassennamen auf neue mappen
ShapeReference = ShapeRecord  # Temporärer Alias


def test_foundation():
    """
    Testet die Foundation des TNP Systems.
    Option B: Validierung vor Integration.
    """
    print("=" * 60)
    print("TNP v4.0 Foundation Test")
    print("=" * 60)
    
    # 1. Service erstellen
    print("\n1. ShapeNamingService erstellen...")
    service = ShapeNamingService()
    print(f"   ✓ Service erstellt")
    print(f"   Stats: {service.get_stats()}")
    
    # 2. ShapeID erstellen (ohne echte Geometrie)
    print("\n2. ShapeID erstellen...")
    shape_id = ShapeID.create(
        shape_type=ShapeType.EDGE,
        feature_id="test_extrude",
        local_index=0,
        geometry_data=(0.0, 0.0, 0.0, 10.0)  # x, y, z, length
    )
    print(f"   ✓ ShapeID: {shape_id.uuid[:16]}...")
    print(f"   ✓ Feature: {shape_id.feature_id}")
    print(f"   ✓ Type: {shape_id.shape_type}")
    
    # 3. OperationRecord erstellen
    print("\n3. OperationRecord erstellen...")
    op = OperationRecord(
        operation_id="op_001",
        operation_type="EXTRUDE",
        feature_id="test_extrude",
        input_shape_ids=[],
        output_shape_ids=[shape_id]
    )
    service.record_operation(op)
    print(f"   ✓ Operation aufgezeichnet: {op.operation_type}")
    
    # 4. Stats prüfen
    print("\n4. Finale Stats...")
    stats = service.get_stats()
    print(f"   Shapes: {stats['total_shapes']}")
    print(f"   Operations: {stats['operations']}")
    print(f"   Features: {stats['features']}")
    
    # 5. Letzte Operation abrufen
    print("\n5. Letzte Operation abrufen...")
    last_op = service.get_last_operation()
    if last_op:
        print(f"   ✓ Gefunden: {last_op.operation_type}")
        print(f"   ✓ Output Shapes: {len(last_op.output_shape_ids)}")
    else:
        print("   ✗ Nicht gefunden")
        return False
    
    print("\n" + "=" * 60)
    print("✓ FOUNDATION TEST ERFOLGREICH")
    print("=" * 60)
    return True


if __name__ == "__main__":
    import sys
    success = test_foundation()
    sys.exit(0 if success else 1)
