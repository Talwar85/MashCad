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
        elif self.shape_id.shape_type == ShapeType.FACE:
            try:
                from OCP.GProp import GProp_GProps
                from OCP.BRepGProp import BRepGProp

                props = GProp_GProps()
                BRepGProp.SurfaceProperties_s(self.ocp_shape, props)

                center = props.CentreOfMass()
                sig["center"] = (center.X(), center.Y(), center.Z())
                sig["area"] = props.Mass()
            except Exception as e:
                logger.debug(f"Face-Signaturberechnung fehlgeschlagen: {e}")
        
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
        # Erstelle Geometry Data für Hash falls nicht angegeben.
        if geometry_data is None and HAS_OCP:
            geometry_data = self._extract_geometry_data(ocp_shape, shape_type)

        # Reuse bestehende Shape-Slots pro (feature_id, shape_type, local_index),
        # damit Rebuilds dieselben ShapeIDs aktualisieren statt endlos neue UUIDs
        # anzulegen.
        feature_bucket = self._by_feature.setdefault(feature_id, [])
        existing_shape_id: Optional[ShapeID] = None
        for sid in reversed(feature_bucket):
            if sid.shape_type != shape_type:
                continue
            if int(getattr(sid, "local_index", -1)) == int(local_index):
                existing_shape_id = sid
                break

        if existing_shape_id is not None:
            shape_id = existing_shape_id
            # Alte Spatial-Index Position entfernen, Record wird unten aktualisiert.
            for shape_type_key in self._spatial_index:
                self._spatial_index[shape_type_key] = [
                    (pos, sid) for pos, sid in self._spatial_index[shape_type_key]
                    if sid.uuid != shape_id.uuid
                ]
        else:
            # Erstelle ShapeID
            shape_id = ShapeID.create(
                shape_type=shape_type,
                feature_id=feature_id,
                local_index=local_index,
                geometry_data=geometry_data or ()
            )
            feature_bucket.append(shape_id)
        
        # Erstelle Record
        record = ShapeRecord(
            shape_id=shape_id,
            ocp_shape=ocp_shape
        )
        record.geometric_signature = record.compute_signature()
        
        # Speichern
        self._shapes[shape_id.uuid] = record
        
        # Räumlichen Index aktualisieren
        self._update_spatial_index(shape_id, record)
        
        if is_enabled("tnp_debug_logging"):
            logger.debug(f"Shape registriert: {shape_id}")
        return shape_id

    def seed_shape(self, shape_id: ShapeID, ocp_shape: TopoDS_Shape) -> None:
        """
        Registriert ein bereits existierendes ShapeID->Shape Mapping (z. B. nach Load).

        Anders als register_shape() wird die UUID dabei NICHT neu erzeugt.
        """
        if shape_id is None or not getattr(shape_id, "uuid", ""):
            return

        record = ShapeRecord(shape_id=shape_id, ocp_shape=ocp_shape)
        record.geometric_signature = record.compute_signature()

        # Vorherige Einträge für dieselbe UUID aus dem räumlichen Index entfernen.
        for shape_type_key in self._spatial_index:
            self._spatial_index[shape_type_key] = [
                (pos, sid) for pos, sid in self._spatial_index[shape_type_key]
                if sid.uuid != shape_id.uuid
            ]

        self._shapes[shape_id.uuid] = record

        feature_bucket = self._by_feature.setdefault(shape_id.feature_id, [])
        if not any(existing.uuid == shape_id.uuid for existing in feature_bucket):
            feature_bucket.append(shape_id)

        self._update_spatial_index(shape_id, record)
    
    def record_operation(self, operation: OperationRecord) -> None:
        """Speichert eine Operation im Graph"""
        # Rebuilds führen dasselbe Feature mehrfach aus. Für stabile History
        # behalten wir je (feature_id, operation_type) nur den neuesten Record.
        self._operations = [
            op for op in self._operations
            if not (
                op.feature_id == operation.feature_id
                and op.operation_type == operation.operation_type
            )
        ]
        self._operations.append(operation)
        if is_enabled("tnp_debug_logging"):
            logger.debug(f"Operation aufgezeichnet: {operation.operation_type} "
                        f"({len(operation.input_shape_ids)} in -> "
                        f"{len(operation.output_shape_ids)} out)")
    
    def _find_exact_shape_id(self, shape: Any, shape_type: ShapeType) -> Optional[ShapeID]:
        """
        Findet eine ShapeID per exakter Topologie-Identität (IsSame).

        Diese Suche ist robust gegen symmetrische/geometrisch ähnliche Entitäten
        und sollte für interaktive Selektion bevorzugt werden.
        """
        try:
            target_shape = shape.wrapped if hasattr(shape, "wrapped") else shape
            if target_shape is None:
                return None

            # Neueste Records zuerst bevorzugen (Dict ist insertion-ordered).
            for record in reversed(list(self._shapes.values())):
                sid = record.shape_id
                if sid.shape_type != shape_type:
                    continue
                rec_shape = record.ocp_shape
                if rec_shape is None:
                    continue
                try:
                    if rec_shape.IsSame(target_shape):
                        return sid
                except Exception:
                    continue
        except Exception as e:
            logger.debug(f"Exact-ShapeID Lookup fehlgeschlagen: {e}")
        return None

    def find_shape_id_by_edge(
        self,
        edge: Any,
        tolerance: float = 0.1,
        *,
        require_exact: bool = False,
    ) -> Optional[ShapeID]:
        """
        Findet eine ShapeID für eine gegebene Edge (geometrisches Matching).
        Wird verwendet wenn ein Feature Edges auswählt - wir müssen die
        existierende ShapeID finden, nicht eine neue erstellen.
        """
        try:
            exact = self._find_exact_shape_id(edge, ShapeType.EDGE)
            if exact is not None:
                return exact
            if require_exact:
                return None

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
    
    def find_shape_id_by_face(
        self,
        face: Any,
        tolerance: float = 0.5,
        *,
        require_exact: bool = False,
    ) -> Optional[ShapeID]:
        """
        Findet eine ShapeID für eine gegebene Face (geometrisches Matching).
        Analog zu find_shape_id_by_edge, aber für Faces.
        """
        try:
            exact = self._find_exact_shape_id(face, ShapeType.FACE)
            if exact is not None:
                return exact
            if require_exact:
                return None

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

    def find_shape_id_by_shape(
        self,
        ocp_shape: Any,
        tolerance: float = 0.5,
        *,
        require_exact: bool = False,
    ) -> Optional[ShapeID]:
        """
        Generische Methode zum Finden einer ShapeID für ein beliebiges Shape.

        Erkennt automatisch den Shape-Typ (Edge/Face/Vertex) und ruft
        die spezialisierte Methode auf.

        Args:
            ocp_shape: OCP Shape (TopoDS_Edge, TopoDS_Face, etc.)
            tolerance: Toleranz für geometrisches Matching
            require_exact: Wenn True, nur exakte Matches zurückgeben

        Returns:
            ShapeID oder None
        """
        if not HAS_OCP or ocp_shape is None:
            return None

        try:
            from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_VERTEX
            from OCP.TopoDS import TopoDS_Edge, TopoDS_Face, TopoDS_Vertex

            # Shape-Typ erkennen
            shape_type = ocp_shape.ShapeType()

            if shape_type == TopAbs_EDGE:
                # Wrapper zu build123d Edge
                from build123d import Edge
                b123d_edge = Edge(ocp_shape)
                return self.find_shape_id_by_edge(b123d_edge, tolerance=tolerance, require_exact=require_exact)

            elif shape_type == TopAbs_FACE:
                # Wrapper zu build123d Face
                from build123d import Face
                b123d_face = Face(ocp_shape)
                return self.find_shape_id_by_face(b123d_face, tolerance=tolerance, require_exact=require_exact)

            elif shape_type == TopAbs_VERTEX:
                # TODO: Vertex-Support wenn benötigt
                if require_exact:
                    return self._find_exact_shape_id(ocp_shape, ShapeType.VERTEX)
                return None

            else:
                logger.debug(f"[TNP] Unsupported shape type for ShapeID lookup: {shape_type}")
                return None

        except Exception as e:
            logger.debug(f"[TNP] find_shape_id_by_shape failed: {e}")
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

    def resolve_shape_id(
        self,
        shape_uuid: str,
        current_solid: Any,
        *,
        log_unresolved: bool = True,
    ) -> Optional[Any]:
        """
        Löst eine ShapeID (per UUID) zur aktuellen Geometrie auf.

        Convenience-Methode für UUID-basierte Auflösung (TNP v4.0 GUI Integration).

        Args:
            shape_uuid: Die UUID der ShapeID (als String)
            current_solid: Der aktuelle build123d Solid
            log_unresolved: Ob ungelöste Shapes geloggt werden sollen

        Returns:
            Aufgelöstes OCP Shape oder None
        """
        # ShapeID aus UUID finden
        shape_record = self._shapes.get(shape_uuid)
        if shape_record is None:
            if log_unresolved:
                logger.debug(f"[TNP] ShapeID {shape_uuid[:8]}... nicht in Registry")
            return None

        # ShapeID auflösen
        return self.resolve_shape(
            shape_record.shape_id,
            current_solid,
            log_unresolved=log_unresolved,
        )

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
        # Fillet/Chamfer und Push/Pull verbrauchen ihre Input-Topologie.
        # Die Input-Referenzen sind danach im End-Solid nicht mehr zwingend
        # direkt auflösbar, obwohl der Rebuild korrekt ist.
        'FilletFeature', 'ChamferFeature',
        'ExtrudeFeature',
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

        def _status_details_dict(feat: Any) -> Dict[str, Any]:
            details = getattr(feat, "status_details", {})
            return details if isinstance(details, dict) else {}

        def _status_diag_level(feat: Any, details: Dict[str, Any]) -> str:
            code = str(details.get("code", "") or "").strip().lower()
            if code in {"fallback_used"}:
                return "fallback"
            if code in {
                "operation_failed",
                "fallback_failed",
                "no_result_solid",
                "self_heal_rollback_geometry_drift",
            }:
                return "broken"

            feat_status = str(getattr(feat, "status", "") or "").strip().upper()
            if feat_status == "WARNING":
                return "fallback"
            if feat_status == "ERROR":
                return "broken"
            return "ok"

        def _status_ref_kind(label: str) -> str:
            txt = str(label or "").lower()
            if "edge" in txt:
                return "Edge"
            if "face" in txt:
                return "Face"
            return "Ref"

        def _collect_status_ref_entries(feat: Any) -> List[Dict[str, Any]]:
            details = _status_details_dict(feat)
            refs = details.get("refs")
            if not isinstance(refs, dict):
                return []

            diag_status = _status_diag_level(feat, details)
            entries: List[Dict[str, Any]] = []
            for ref_label, raw_value in refs.items():
                values = _to_list(raw_value)
                if not values:
                    continue
                for value in values:
                    if value in (None, "", [], (), {}):
                        continue
                    entries.append(
                        {
                            "kind": _status_ref_kind(ref_label),
                            "status": diag_status,
                            "method": "status_details",
                            "label": str(ref_label),
                            "value": value,
                        }
                    )
            return entries

        def _enforce_feature_status_truth(feat: Any, feat_report: Dict[str, Any]) -> None:
            """
            Force health semantics to follow rebuild truth for feature-level status.

            If a feature ended in ERROR/WARNING, report must reflect this even when
            reference probing still resolves stale indices.
            """
            details = _status_details_dict(feat)
            diag_status = _status_diag_level(feat, details)

            if diag_status == "ok":
                return

            # If refs already indicate same/worse severity, do not duplicate.
            if diag_status == "broken" and feat_report.get("broken", 0) > 0:
                return
            if diag_status == "fallback" and (
                feat_report.get("fallback", 0) > 0 or feat_report.get("broken", 0) > 0
            ):
                return

            # Add synthetic truth-ref so UI and totals stay consistent.
            feat_report["refs"].append(
                {
                    "kind": "Ref",
                    "status": diag_status,
                    "method": "feature_status",
                    "label": "feature_status",
                    "value": str(getattr(feat, "status", "") or ""),
                }
            )

            if diag_status == "broken":
                feat_report["broken"] = int(feat_report.get("broken", 0)) + 1
                report["broken"] = int(report.get("broken", 0)) + 1
            elif diag_status == "fallback":
                feat_report["fallback"] = int(feat_report.get("fallback", 0)) + 1
                report["fallback"] = int(report.get("fallback", 0)) + 1

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

            sweep_profile_shape_id = getattr(feat, "profile_shape_id", None)
            sweep_profile_index = getattr(feat, "profile_face_index", None)
            if sweep_profile_shape_id is not None or sweep_profile_index is not None:
                groups.append((
                    "Face",
                    _to_list(sweep_profile_shape_id),
                    _to_index_list(sweep_profile_index),
                ))

            sweep_path_shape_id = getattr(feat, "path_shape_id", None)
            sweep_path_indices: List[Optional[int]] = []
            path_data = getattr(feat, "path_data", {})
            if isinstance(path_data, dict):
                sweep_path_indices = _to_index_list(path_data.get("edge_indices", []))
            if sweep_path_shape_id is not None or sweep_path_indices:
                groups.append((
                    "Edge",
                    _to_list(sweep_path_shape_id),
                    sweep_path_indices,
                ))

            return groups

        def _resolve_index_entity(ref_kind: str, topo_index: Optional[int]) -> Optional[Any]:
            if topo_index is None or current_solid is None:
                return None
            try:
                if ref_kind == "Face" and face_from_index is not None:
                    return face_from_index(current_solid, topo_index)
                if ref_kind == "Edge" and edge_from_index is not None:
                    return edge_from_index(current_solid, topo_index)
            except Exception:
                return None
            return None

        def _same_topology_entity(entity_a: Any, entity_b: Any) -> bool:
            if entity_a is None or entity_b is None:
                return False
            try:
                wa = entity_a.wrapped if hasattr(entity_a, "wrapped") else entity_a
                wb = entity_b.wrapped if hasattr(entity_b, "wrapped") else entity_b
                return wa.IsSame(wb)
            except Exception:
                return entity_a is entity_b

        strict_face_feature_types = {
            "ExtrudeFeature",
            "ThreadFeature",
            "HoleFeature",
            "DraftFeature",
            "ShellFeature",
            "HollowFeature",
        }
        strict_edge_feature_types = {
            "FilletFeature",
            "ChamferFeature",
        }

        for feat in features:
            feat_type_name = type(feat).__name__
            is_consuming = feat_type_name in self._CONSUMING_FEATURE_TYPES
            feat_status_message = str(getattr(feat, "status_message", "") or "")
            feat_status_details = _status_details_dict(feat)
            status_ref_entries = _collect_status_ref_entries(feat)

            feat_report = {
                'name': getattr(feat, 'name', 'Feature'),
                'type': feat_type_name.replace('Feature', ''),
                'status': 'no_refs',
                'ok': 0, 'fallback': 0, 'broken': 0,
                'consuming': is_consuming,
                'refs': [],
                'feature_status': str(getattr(feat, "status", "OK") or "OK"),
                'status_message': feat_status_message,
                'status_details': dict(feat_status_details),
                'status_refs': list(status_ref_entries),
            }

            ref_groups = _collect_ref_groups(feat)
            if not ref_groups:
                if status_ref_entries:
                    for ref in status_ref_entries:
                        ref_status = str(ref.get("status", "broken"))
                        if ref_status == "ok":
                            feat_report['ok'] += 1
                            report['ok'] += 1
                        elif ref_status == "fallback":
                            feat_report['fallback'] += 1
                            report['fallback'] += 1
                        else:
                            feat_report['broken'] += 1
                            report['broken'] += 1
                        feat_report['refs'].append(
                            {
                                "kind": ref.get("kind", "Ref"),
                                "status": ref_status,
                                "method": ref.get("method", "status_details"),
                                "label": ref.get("label", ""),
                                "value": ref.get("value"),
                            }
                        )
                _enforce_feature_status_truth(feat, feat_report)
                if feat_report['broken'] > 0:
                    feat_report['status'] = 'broken'
                elif feat_report['fallback'] > 0:
                    feat_report['status'] = 'fallback'
                elif feat_report['ok'] > 0:
                    feat_report['status'] = 'ok'
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

                    if rebuild_status in ('OK', 'SUCCESS'):
                        feat_report['ok'] += ref_count
                        report['ok'] += ref_count
                        ref_status = 'ok'
                    elif rebuild_status == 'WARNING':
                        feat_report['fallback'] += ref_count
                        report['fallback'] += ref_count
                        ref_status = 'fallback'
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
                    strict_kind = (
                        (ref_kind == "Face" and feat_type_name in strict_face_feature_types)
                        or (ref_kind == "Edge" and feat_type_name in strict_edge_feature_types)
                    )
                    valid_index_refs = [idx for idx in index_refs if idx is not None]
                    expected_shape_refs = sum(1 for sid in shape_ids if isinstance(sid, ShapeID))
                    single_ref_pair = bool(expected_shape_refs == 1 and len(valid_index_refs) == 1)
                    shape_ids_index_aligned = True
                    if expected_shape_refs > 0 and valid_index_refs and not single_ref_pair:
                        for sid in shape_ids:
                            if not isinstance(sid, ShapeID):
                                continue
                            local_idx = getattr(sid, "local_index", None)
                            if not isinstance(local_idx, int) or not (0 <= local_idx < len(valid_index_refs)):
                                shape_ids_index_aligned = False
                                break
                    strict_group_check = (
                        strict_kind
                        and expected_shape_refs > 0
                        and bool(valid_index_refs)
                        and len(valid_index_refs) == expected_shape_refs
                        and (shape_ids_index_aligned or single_ref_pair)
                    )

                    ref_count = max(len(shape_ids), len(index_refs))
                    for ref_idx in range(ref_count):
                        topo_index = index_refs[ref_idx] if ref_idx < len(index_refs) else None
                        shape_id = shape_ids[ref_idx] if ref_idx < len(shape_ids) else None

                        index_entity = _resolve_index_entity(ref_kind, topo_index)
                        index_ok = index_entity is not None

                        shape_entity = None
                        method = "unresolved"
                        has_shape_ref = isinstance(shape_id, ShapeID)
                        strict_shape_check = has_shape_ref and strict_group_check
                        should_resolve_shape = strict_shape_check or (has_shape_ref and not index_ok)
                        if should_resolve_shape and ocp_solid is not None:
                            shape_entity, method = self.resolve_shape_with_method(
                                shape_id,
                                ocp_solid,
                                log_unresolved=False,
                            )

                        # Für strict TNP-v4 Features:
                        # Bei ShapeID+Index nicht blind "index=ok" zählen,
                        # sondern beide Referenzen gegeneinander validieren.
                        if (
                            strict_shape_check
                            and has_shape_ref
                            and topo_index is not None
                        ):
                            if shape_entity is not None:
                                if index_ok and not _same_topology_entity(index_entity, shape_entity):
                                    status = "broken"
                                    method = "index_mismatch"
                                elif method in ("direct", "history"):
                                    status = "ok"
                                    method = "shape"
                                elif method in ("brepfeat", "geometric"):
                                    status = "fallback"
                                else:
                                    status = "broken"
                            else:
                                status = "broken"
                                method = "shape_unresolved"
                        elif strict_shape_check and topo_index is None:
                            if shape_entity is not None:
                                if method in ("direct", "history"):
                                    status = "ok"
                                    method = "shape"
                                elif method in ("brepfeat", "geometric"):
                                    status = "fallback"
                                else:
                                    status = "broken"
                            else:
                                status = "broken"
                                method = "shape_unresolved"
                        elif index_ok:
                            status = "ok"
                            method = "index"
                        elif has_shape_ref:
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

            _enforce_feature_status_truth(feat, feat_report)
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

    def update_shape_id_after_operation(
        self,
        old_shape: Any,
        new_shape: Any,
        feature_id: str,
        operation_type: str = "unknown"
    ) -> bool:
        """
        TNP v4.1: Aktualisiert eine ShapeID mit neuer Geometrie nach einer Operation.

        Dies ist die KERN-METHODE für History-basiertes TNP. Anstatt auf
        Geometric-Fallback zurückzufallen, werden ShapeIDs direkt mit der
        neuen Geometrie aktualisiert.

        Args:
            old_shape: Die OCP-Shape VOR der Operation
            new_shape: Die OCP-Shape NACH der Operation
            feature_id: ID des Features das die Operation ausführt
            operation_type: Art der Operation (für Logging)

        Returns:
            True wenn ShapeID gefunden und aktualisiert wurde, False sonst
        """
        if not HAS_OCP:
            return False

        try:
            # Alte ShapeID finden
            old_shape_id = self._find_exact_shape_id_by_ocp_shape(old_shape)
            if old_shape_id is None:
                if is_enabled("tnp_debug_logging"):
                    logger.debug(f"TNP: Alte Shape nicht gefunden für Update")
                return False

            # Neue Geometrie-Daten berechnen
            from OCP.BRepGProp import BRepGProp
            from OCP.GeomAbs import GeomAbs_Curve
            from OCP.BRepAdaptor import BRepAdaptor_Curve
            from OCP.GProp import GProp_GProps

            geo_data = self._compute_geometry_data(new_shape)
            if geo_data is None:
                logger.warning(f"TNP: Konnte Geometrie-Daten nicht berechnen für {old_shape_id.uuid[:8]}")
                return False

            # ShapeID aktualisieren - neue Geometrie, gleiche UUID
            updated_shape_id = ShapeID(
                uuid=old_shape_id.uuid,
                shape_type=old_shape_id.shape_type,
                feature_id=feature_id,
                local_index=old_shape_id.local_index,
                geometry_hash=geo_data,
                timestamp=time.time()
            )

            # ShapeRecord aktualisieren
            new_record = ShapeRecord(
                shape_id=updated_shape_id,
                ocp_shape=new_shape,
                is_valid=True,
                geometric_signature=self._compute_geometric_signature(new_shape)
            )

            # Alten Record ersetzen
            self._shapes[old_shape_id.uuid] = new_record

            # Spatial Index aktualisieren
            shape_type_key = updated_shape_id.shape_type.name
            if shape_type_key in self._spatial_index:
                # Alten Eintrag entfernen
                self._spatial_index[shape_type_key] = [
                    (pos, sid) for pos, sid in self._spatial_index[shape_type_key]
                    if sid.uuid != old_shape_id.uuid
                ]
                # Neuen Eintrag hinzufügen
                center = self._get_shape_center(new_shape)
                if center:
                    self._spatial_index[shape_type_key].append((center, updated_shape_id))

            if is_enabled("tnp_debug_logging"):
                logger.success(
                    f"TNP v4.1: ShapeID {old_shape_id.uuid[:8]} aktualisiert "
                    f"nach {operation_type}"
                )
            return True

        except Exception as e:
            logger.warning(f"TNP: update_shape_id_after_operation fehlgeschlagen: {e}")
            return False

    def update_shape_ids_from_history(
        self,
        source_solid: Any,
        result_solid: Any,
        occt_history: Any,
        feature_id: str,
        operation_type: str = "unknown"
    ) -> int:
        """
        TNP v4.1: Aktualisiert ALLE ShapeIDs basierend auf OCCT History.

        Dies ist die bevorzugte Methode um ShapeIDs nach Boolean/Extrude/etc.
        Operationen zu aktualisieren.

        Args:
            source_solid: Solid VOR der Operation
            result_solid: Solid NACH der Operation
            occt_history: BRepTools_History Objekt
            feature_id: ID des Features
            operation_type: Art der Operation

        Returns:
            Anzahl der aktualisierten ShapeIDs
        """
        if not HAS_OCP or occt_history is None:
            return 0

        try:
            from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
            from OCP.TopTools import TopTools_IndexedMapOfShape
            from OCP.TopExp import TopExp

            updated_count = 0

            # Alle Shapes im Source-Solid durchgehen
            for shape_type in (TopAbs_EDGE, TopAbs_FACE):
                source_map = TopTools_IndexedMapOfShape()
                TopExp.MapShapes_s(source_solid, shape_type, source_map)

                for i in range(1, source_map.Extent() + 1):
                    old_shape = source_map.FindKey(i)

                    # Prüfen ob diese Shape eine ShapeID hat
                    old_shape_id = self._find_exact_shape_id_by_ocp_shape(old_shape)
                    if old_shape_id is None:
                        continue

                    # History abfragen: Was ist aus dieser Shape geworden?
                    modified = self._history_outputs_for_shape(occt_history, old_shape)
                    if not modified:
                        # Shape wurde nicht modifiziert (existiert noch)
                        continue

                    # Die modifizierte Shape nehmen (erste)
                    new_shape = modified[0]

                    # ShapeID aktualisieren
                    if self.update_shape_id_after_operation(
                        old_shape, new_shape, feature_id, f"{operation_type}_history"
                    ):
                        updated_count += 1

            if is_enabled("tnp_debug_logging") and updated_count > 0:
                logger.success(
                    f"TNP v4.1: {updated_count} ShapeIDs nach {operation_type} "
                    f"über History aktualisiert"
                )

            return updated_count

        except Exception as e:
            logger.warning(f"TNP: update_shape_ids_from_history fehlgeschlagen: {e}")
            import traceback
            traceback.print_exc()
            return 0

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
    
    def _iter_history_shapes(self, shape_list_obj: Any) -> List[Any]:
        """Konvertiert OCCT ListOfShape robust in eine Python-Liste."""
        if shape_list_obj is None:
            return []
        try:
            return [s for s in shape_list_obj]
        except Exception:
            pass

        try:
            it = shape_list_obj.Iterator()
            out = []
            while it.More():
                out.append(it.Value())
                it.Next()
            return out
        except Exception:
            return []

    def _history_outputs_for_shape(self, occt_history: Any, source_shape: Any) -> List[Any]:
        """
        Liefert History-Outputs für ein Source-Shape.
        Bevorzugt Modified vor Generated.
        """
        if occt_history is None or source_shape is None:
            return []

        outputs: List[Any] = []
        seen: List[Any] = []
        for query_name in ("Modified", "Generated"):
            try:
                query_fn = getattr(occt_history, query_name, None)
                if query_fn is None:
                    continue
                mapped = self._iter_history_shapes(query_fn(source_shape))
            except Exception:
                mapped = []

            for mapped_shape in mapped:
                if mapped_shape is None:
                    continue
                duplicate = False
                for known in seen:
                    try:
                        if known.IsSame(mapped_shape):
                            duplicate = True
                            break
                    except Exception:
                        continue
                if duplicate:
                    continue
                seen.append(mapped_shape)
                outputs.append(mapped_shape)

        return outputs

    def _trace_via_history(self, shape_id: ShapeID,
                          current_solid: Any) -> Optional[Any]:
        """
        Level 2: Versucht Shape via Operation-Graph zu tracen.
        Folgt der Kette: ShapeID -> Operation -> Mapped Shapes.
        """
        if not self._operations or shape_id.uuid not in self._shapes:
            return None

        try:
            base_record = self._shapes.get(shape_id.uuid)
            candidate_shape = base_record.ocp_shape if base_record is not None else None
            candidate_uuid = shape_id.uuid

            if candidate_shape is None:
                return None

            # Chronologisch durchlaufen: wir folgen derselben Evolutionsrichtung
            # wie die Feature-Historie.
            for op in self._operations:
                had_mapping = False
                next_shape = None
                next_uuid = None

                if op.manual_mappings and candidate_uuid in op.manual_mappings:
                    had_mapping = True
                    for mapped_uuid in op.manual_mappings.get(candidate_uuid, []):
                        mapped_record = self._shapes.get(mapped_uuid)
                        if mapped_record is None or mapped_record.ocp_shape is None:
                            continue
                        mapped_shape = mapped_record.ocp_shape
                        if self._shape_exists_in_solid(mapped_shape, current_solid):
                            return mapped_shape
                        if next_shape is None:
                            next_shape = mapped_shape
                            next_uuid = mapped_uuid

                if op.occt_history is not None and HAS_OCP and candidate_shape is not None:
                    history_outputs = self._history_outputs_for_shape(op.occt_history, candidate_shape)
                    if history_outputs:
                        had_mapping = True
                        for mapped_shape in history_outputs:
                            if self._shape_exists_in_solid(mapped_shape, current_solid):
                                # Selbstheilend: aktualisiere Record auf die zuletzt
                                # aufgelöste Geometrie.
                                if base_record is not None:
                                    base_record.ocp_shape = mapped_shape
                                    base_record.is_valid = True
                                    base_record.geometric_signature = base_record.compute_signature()
                                return mapped_shape
                        if next_shape is None:
                            next_shape = history_outputs[0]

                if had_mapping and next_shape is not None:
                    candidate_shape = next_shape
                    if next_uuid is not None:
                        candidate_uuid = next_uuid

        except Exception as e:
            logger.debug(f"History Tracing fehlgeschlagen: {e}")

        return None

    def _collect_brepfeat_history_inputs(
        self,
        source_solid: Any,
        modified_face: Any,
    ) -> List[Tuple[ShapeID, Any]]:
        """
        Sammelt Source-ShapeIDs (Face + Boundary-Edges) für kernel-first BRepFeat Mapping.
        """
        if not HAS_OCP or modified_face is None:
            return []

        from OCP.TopExp import TopExp_Explorer
        from OCP.TopAbs import TopAbs_EDGE
        from OCP.TopoDS import TopoDS

        inputs: List[Tuple[ShapeID, Any]] = []
        seen_uuids: Set[str] = set()

        def _append_candidate(shape_id: Optional[ShapeID], shape_obj: Any) -> None:
            if shape_id is None or shape_obj is None:
                return
            if shape_id.uuid in seen_uuids:
                return
            record = self._shapes.get(shape_id.uuid)
            candidate_shape = record.ocp_shape if (record and record.ocp_shape is not None) else shape_obj
            if candidate_shape is None:
                return
            if not self._shape_exists_in_solid(candidate_shape, source_solid):
                return
            seen_uuids.add(shape_id.uuid)
            inputs.append((shape_id, candidate_shape))

        face_shape = modified_face.wrapped if hasattr(modified_face, "wrapped") else modified_face
        face_shape_id = self.find_shape_id_by_face(face_shape, require_exact=True)
        _append_candidate(face_shape_id, face_shape)

        edge_exp = TopExp_Explorer(face_shape, TopAbs_EDGE)
        while edge_exp.More():
            edge_shape = TopoDS.Edge_s(edge_exp.Current())
            edge_shape_id = self.find_shape_id_by_edge(edge_shape, require_exact=True)
            _append_candidate(edge_shape_id, edge_shape)
            edge_exp.Next()

        return inputs

    def _build_brepfeat_history_mappings(
        self,
        feature_id: str,
        source_items: List[Tuple[ShapeID, Any]],
        result_solid: Any,
        occt_history: Any,
        *,
        start_local_index: int = 0,
    ) -> Tuple[Dict[str, List[str]], List[ShapeID]]:
        """
        Erstellt Input->Output Mappings per OCCT History für BRepFeat.
        """
        from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_VERTEX

        shape_type_to_topabs = {
            ShapeType.EDGE: TopAbs_EDGE,
            ShapeType.FACE: TopAbs_FACE,
            ShapeType.VERTEX: TopAbs_VERTEX,
        }

        local_index = max(0, int(start_local_index or 0))
        manual_mappings: Dict[str, List[str]] = {}
        new_shape_ids: List[ShapeID] = []
        registered_outputs: List[Tuple[Any, ShapeID]] = []

        for source_shape_id, source_shape in source_items:
            expected_topabs = shape_type_to_topabs.get(source_shape_id.shape_type)
            history_outputs = self._history_outputs_for_shape(occt_history, source_shape)
            if not history_outputs:
                continue

            for mapped_shape in history_outputs:
                if mapped_shape is None:
                    continue
                try:
                    if expected_topabs is not None and mapped_shape.ShapeType() != expected_topabs:
                        continue
                except Exception:
                    continue
                if not self._shape_exists_in_solid(mapped_shape, result_solid):
                    continue

                mapped_shape_id: Optional[ShapeID] = None
                for known_shape, known_shape_id in registered_outputs:
                    try:
                        if known_shape.IsSame(mapped_shape):
                            mapped_shape_id = known_shape_id
                            break
                    except Exception:
                        continue

                if mapped_shape_id is None:
                    mapped_shape_id = self.register_shape(
                        ocp_shape=mapped_shape,
                        shape_type=source_shape_id.shape_type,
                        feature_id=feature_id,
                        local_index=local_index,
                    )
                    registered_outputs.append((mapped_shape, mapped_shape_id))
                    new_shape_ids.append(mapped_shape_id)
                    local_index += 1

                bucket = manual_mappings.setdefault(source_shape_id.uuid, [])
                if mapped_shape_id.uuid not in bucket:
                    bucket.append(mapped_shape_id.uuid)

        return manual_mappings, new_shape_ids
    
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
            elif shape_id.shape_type == ShapeType.FACE:
                target_area = record.geometric_signature.get('area', 0)

                for face in solid_for_iteration.faces():
                    center = face.center()
                    face_center = np.array([center.X, center.Y, center.Z])

                    # Distanz-Score (wichtigster Faktor)
                    dist = np.linalg.norm(target_center - face_center)

                    # Flächen-Score
                    area_score = 0
                    if target_area > 0 and hasattr(face, 'area'):
                        area_diff = abs(face.area - target_area)
                        area_score = (area_diff / target_area) * 5

                    score = dist + area_score

                    if score < best_score and dist < 1.0:  # 1mm Distanz-Toleranz
                        best_score = score
                        best_match = face.wrapped

                if best_match:
                    logger.debug(f"Face Geometric Match Score: {best_score:.3f}")
        
        except Exception as e:
            logger.debug(f"Geometrisches Matching fehlgeschlagen: {e}")
        
        return best_match

    def track_brepfeat_operation(self, feature_id: str,
                                  source_solid: Any,
                                  result_solid: Any,
                                  modified_face: Any,
                                  direction: Tuple[float, float, float],
                                  distance: float,
                                  occt_history: Optional[Any] = None) -> Optional[OperationRecord]:
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
            occt_history: Optionales BRepTools_History aus BRepFeat_MakePrism.
                Wenn gesetzt, wird kernel-first History-Mapping verwendet.
            
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
            
            # Kernel-first Pfad: Wenn OCCT History vorhanden ist, zuerst echte
            # Source->Result Mappings daraus ableiten.
            if occt_history is not None:
                source_items = self._collect_brepfeat_history_inputs(source_solid, modified_face)
                if source_items:
                    manual_mappings, new_shape_ids = self._build_brepfeat_history_mappings(
                        feature_id=feature_id,
                        source_items=source_items,
                        result_solid=result_solid,
                        occt_history=occt_history,
                        start_local_index=0,
                    )

                    edge_output_ids = [sid for sid in new_shape_ids if sid.shape_type == ShapeType.EDGE]
                    max_edge_local_index = max(
                        (int(sid.local_index) for sid in edge_output_ids),
                        default=-1,
                    )

                    mappings_for_unmapped = []
                    for new_shape_id in edge_output_ids:
                        mappings_for_unmapped.append(
                            type("Mapping", (), {"new_shape_uuid": new_shape_id.uuid})()
                        )

                    new_edge_count = self._register_unmapped_edges(
                        result_solid=result_solid,
                        feature_id=feature_id,
                        existing_mappings=mappings_for_unmapped,
                        start_local_index=max_edge_local_index + 1,
                    )

                    input_shape_ids = [sid for sid, _shape in source_items]
                    op_record = OperationRecord(
                        operation_type="BREPFEAT_PRISM",
                        feature_id=feature_id,
                        input_shape_ids=input_shape_ids,
                        output_shape_ids=new_shape_ids,
                        occt_history=occt_history,
                        manual_mappings=manual_mappings,
                        metadata={
                            "direction": direction,
                            "distance": distance,
                            "mappings_count": len(manual_mappings),
                            "new_edges_registered": int(new_edge_count),
                            "mapping_mode": "history",
                        },
                    )
                    self.record_operation(op_record)

                    if is_enabled("tnp_debug_logging"):
                        logger.success(
                            "TNP v4.0: BRepFeat kernel-history getrackt - "
                            f"{len(manual_mappings)} mappings + {new_edge_count} neue Edges"
                        )
                    return op_record
                if is_enabled("tnp_debug_logging"):
                    logger.debug(
                        "TNP v4.0: BRepFeat kernel-history ohne Source-Inputs, "
                        "falle auf Heuristik zurück"
                    )

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
            # und dedupe mehrere Records, die auf dieselbe Source-Edge zeigen.
            source_edge_shapes = []
            for shape_id, record in self._shapes.items():
                if record.shape_id.shape_type != ShapeType.EDGE:
                    continue
                     
                if 'center' not in record.geometric_signature:
                    continue

                # Nur Edges berücksichtigen, die tatsächlich im Source-Solid der
                # aktuellen Operation existieren. Sonst werden stale Records aus
                # früheren Rebuilds fälschlich als "betroffen" gemappt.
                if not record.ocp_shape or not self._shape_exists_in_solid(record.ocp_shape, source_solid):
                    continue

                # Dedupe gleiche Source-Edge (mehrere stale ShapeIDs auf derselben Kante).
                already_seen = False
                for seen_shape in source_edge_shapes:
                    try:
                        if seen_shape.IsSame(record.ocp_shape):
                            already_seen = True
                            break
                    except Exception:
                        continue
                if already_seen:
                    continue
                source_edge_shapes.append(record.ocp_shape)
                
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
            used_new_edge_indices = set()
            
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
                    if i in used_new_edge_indices:
                        continue
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
                    used_new_edge_indices.add(idx)
                    
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
                existing_mappings=mappings_for_unmapped,
                start_local_index=len(new_shape_ids),
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
                        'mappings_count': len(manual_mappings),
                        'mapping_mode': 'heuristic',
                    }
                )
                
                self.record_operation(op_record)
                 
                mapped_unique = len({sid.uuid for sid in new_shape_ids})
                total_refs = mapped_unique + new_edge_count
                if is_enabled("tnp_debug_logging"):
                    logger.success(
                        "TNP v4.0: BRepFeat Operation getrackt - "
                        f"{len(manual_mappings)} mappings ({mapped_unique} unique) + "
                        f"{new_edge_count} neue Edges = {total_refs} unique refs"
                    )
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

    def _register_unmapped_edges(
        self,
        result_solid,
        feature_id: str,
        existing_mappings: List,
        start_local_index: int = 0,
    ) -> int:
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

            # Ergänze explizit bereits gemappte Output-Edges.
            # (Defensiv: verhindert Doppel-Registrierung bei partiellen Registry-States.)
            for mapping in existing_mappings or []:
                new_uuid = getattr(mapping, "new_shape_uuid", None)
                if not new_uuid:
                    continue
                record = self._shapes.get(str(new_uuid))
                if not record or record.shape_id.shape_type != ShapeType.EDGE or not record.ocp_shape:
                    continue
                try:
                    known_edges_map.Add(record.ocp_shape)
                except Exception:
                    continue

            if is_enabled("tnp_debug_logging"):
                # Count edges in result
                result_edge_map = TopTools_IndexedMapOfShape()
                TopExp.MapShapes_s(result_shape, TopAbs_EDGE, result_edge_map)
                logger.debug(f"[TNP] _register_unmapped_edges: {result_edge_map.Extent()} unique Edges in result, "
                           f"{known_edges_map.Extent()} already known")

            # 2. Iterate result solid edges using IndexedMap for dedup
            explorer = TopExp_Explorer(result_shape, TopAbs_EDGE)
            new_count = 0
            local_index = max(0, int(start_local_index or 0))

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

    def track_fillet_operation(
        self,
        feature_id: str,
        source_solid: Any,
        result_solid: Any,
        occt_history: Optional[Any] = None,
        edge_shapes: Optional[List[Any]] = None,
        radius: float = 0.0,
    ) -> Optional[OperationRecord]:
        """
        TNP v4.0: Trackt eine BRepFilletAPI_MakeFillet Operation.

        Fillet/Chamfer modifizieren Edges zu Faces. Die OCCT History
        trackt welche Edges modifiziert wurden und welche neuen Faces/Edges
        entstanden sind.

        Args:
            feature_id: ID des Fillet Features
            source_solid: Das Solid vor der Operation
            result_solid: Das Solid nach der Operation
            occt_history: BRepTools_History aus BRepFilletAPI_MakeFillet
            edge_shapes: Optional: Die filletenden Edges (für Fallback)
            radius: Fillet-Radius (für Metadaten)

        Returns:
            OperationRecord mit Mappings, oder None
        """
        if not HAS_OCP:
            return None

        try:
            from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
            from OCP.TopTools import TopTools_IndexedMapOfShape
            from OCP.TopExp import TopExp, TopExp_Explorer
            from OCP.TopoDS import TopoDS

            if is_enabled("tnp_debug_logging"):
                logger.info(f"TNP v4.0: Tracke Fillet Operation '{feature_id}'")

            # Kernel-first: OCCT History auswerten wenn vorhanden
            if occt_history is not None:
                manual_mappings: Dict[str, List[str]] = {}
                new_shape_ids: List[ShapeID] = []

                # Alle Source-Edges finden die im Service registriert sind
                source_edge_map = TopTools_IndexedMapOfShape()
                TopExp.MapShapes_s(source_solid, TopAbs_EDGE, source_edge_map)

                # Für jede registrierte Edge, die Modifications hat
                for uuid, record in list(self._shapes.items()):
                    if record.shape_id.shape_type != ShapeType.EDGE:
                        continue
                    if record.ocp_shape is None:
                        continue

                    # Prüfe ob diese Edge im Source-Solid existiert
                    if not self._shape_exists_in_solid(record.ocp_shape, source_solid):
                        continue

                    # History-Abfrage: Was ist aus dieser Edge geworden?
                    modified_shapes = self._history_outputs_for_shape(occt_history, record.ocp_shape)

                    if modified_shapes:
                        input_shape_id = record.shape_id
                        output_uuids = []

                        for modified_shape in modified_shapes:
                            # TNP v4.1: Zuerst versuchen, die BESTEHENDE ShapeID zu aktualisieren
                            # statt immer neue Shapes zu registrieren
                            existing_id = self._find_exact_shape_id_by_ocp_shape(modified_shape)

                            if existing_id:
                                # Shape ist bereits registriert - weiter zur nächsten
                                output_uuids.append(existing_id.uuid)
                                if existing_id not in new_shape_ids:
                                    new_shape_ids.append(existing_id)
                            else:
                                # TNP v4.1: Versuche die ShapeID mit neuer Geometrie zu aktualisieren
                                # (bevor neue ShapeID erstellt wird)
                                if self.update_shape_id_after_operation(
                                    old_shape=record.ocp_shape,
                                    new_shape=modified_shape,
                                    feature_id=feature_id,
                                    operation_type=f"fillet_{feature_id}"
                                ):
                                    # Erfolgreich aktualisiert - gleiche UUID bleibt erhalten
                                    output_uuids.append(record.shape_id.uuid)
                                    if record.shape_id not in new_shape_ids:
                                        new_shape_ids.append(record.shape_id)
                                    if is_enabled("tnp_debug_logging"):
                                        logger.debug(
                                            f"TNP Fillet: {input_shape_id.uuid[:8]} aktualisiert (ShapeID behalten)"
                                        )
                                else:
                                    # Update fehlgeschlagen - neue ShapeID erstellen
                                    shape_type = ShapeType.FACE if modified_shape.ShapeType() == TopAbs_FACE else ShapeType.EDGE
                                    new_id = self.register_shape(
                                        ocp_shape=modified_shape,
                                        shape_type=shape_type,
                                        feature_id=feature_id,
                                        local_index=len(new_shape_ids)
                                    )
                                    new_shape_ids.append(new_id)
                                    output_uuids.append(new_id.uuid)

                        if output_uuids:
                            manual_mappings[input_shape_id.uuid] = output_uuids

                            if is_enabled("tnp_debug_logging"):
                                logger.debug(
                                    f"TNP Fillet: {input_shape_id.uuid[:8]} → "
                                    f"{len(output_uuids)} Shapes gemappt"
                                )

                # OperationRecord erstellen
                if manual_mappings or new_shape_ids:
                    op_record = OperationRecord(
                        operation_type="FILLET",
                        feature_id=feature_id,
                        input_shape_ids=[sid for sid in self._shapes.values()
                                        if sid.shape_id.uuid in manual_mappings],
                        output_shape_ids=new_shape_ids,
                        occt_history=occt_history,
                        manual_mappings=manual_mappings,
                        metadata={
                            "radius": radius,
                            "mappings_count": len(manual_mappings),
                            "new_shapes": len(new_shape_ids),
                        }
                    )
                    self.record_operation(op_record)

                    if is_enabled("tnp_debug_logging"):
                        logger.success(
                            f"TNP v4.0: Fillet History getrackt - "
                            f"{len(manual_mappings)} mappings, {len(new_shape_ids)} neue Shapes"
                        )
                    return op_record

            # Fallback: Alle neuen Edges im Result-Solid registrieren
            new_edge_count = self._register_unmapped_edges(
                result_solid=result_solid,
                feature_id=feature_id,
                existing_mappings=[],
                start_local_index=0,
            )

            if is_enabled("tnp_debug_logging"):
                logger.info(f"TNP Fillet Fallback: {new_edge_count} neue Edges registriert")

            # Minimaler OperationRecord für Fallback
            op_record = OperationRecord(
                operation_type="FILLET",
                feature_id=feature_id,
                input_shape_ids=[],
                output_shape_ids=[],
                occt_history=occt_history,
                manual_mappings={},
                metadata={
                    "radius": radius,
                    "fallback_mode": True,
                    "new_edges": new_edge_count,
                }
            )
            self.record_operation(op_record)
            return op_record

        except Exception as e:
            if is_enabled("tnp_debug_logging"):
                logger.error(f"TNP v4.0: Fillet Tracking fehlgeschlagen: {e}")
            import traceback
            traceback.print_exc()
            return None

    def track_chamfer_operation(
        self,
        feature_id: str,
        source_solid: Any,
        result_solid: Any,
        occt_history: Optional[Any] = None,
        edge_shapes: Optional[List[Any]] = None,
        distance: float = 0.0,
    ) -> Optional[OperationRecord]:
        """
        TNP v4.0: Trackt eine BRepChamferAPI_MakeChamfer Operation.

        Chamfer ist ähnlich zu Fillet, erstellt aber planare Faces
        anstatt gekrümmter.

        Args:
            feature_id: ID des Chamfer Features
            source_solid: Das Solid vor der Operation
            result_solid: Das Solid nach der Operation
            occt_history: BRepTools_History aus BRepChamferAPI_MakeChamfer
            edge_shapes: Optional: Die chamferenden Edges (für Fallback)
            distance: Chamfer-Abstand (für Metadaten)

        Returns:
            OperationRecord mit Mappings, oder None
        """
        if not HAS_OCP:
            return None

        try:
            from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
            from OCP.TopTools import TopTools_IndexedMapOfShape
            from OCP.TopExp import TopExp, TopExp_Explorer
            from OCP.TopoDS import TopoDS

            if is_enabled("tnp_debug_logging"):
                logger.info(f"TNP v4.0: Tracke Chamfer Operation '{feature_id}'")

            # Kernel-first: OCCT History auswerten wenn vorhanden
            if occt_history is not None:
                manual_mappings: Dict[str, List[str]] = {}
                new_shape_ids: List[ShapeID] = []

                # Alle Source-Edges finden die im Service registriert sind
                source_edge_map = TopTools_IndexedMapOfShape()
                TopExp.MapShapes_s(source_solid, TopAbs_EDGE, source_edge_map)

                # Für jede registrierte Edge, die Modifications hat
                for uuid, record in list(self._shapes.items()):
                    if record.shape_id.shape_type != ShapeType.EDGE:
                        continue
                    if record.ocp_shape is None:
                        continue

                    # Prüfe ob diese Edge im Source-Solid existiert
                    if not self._shape_exists_in_solid(record.ocp_shape, source_solid):
                        continue

                    # History-Abfrage: Was ist aus dieser Edge geworden?
                    modified_shapes = self._history_outputs_for_shape(occt_history, record.ocp_shape)

                    if modified_shapes:
                        input_shape_id = record.shape_id
                        output_uuids = []

                        for modified_shape in modified_shapes:
                            # TNP v4.1: Zuerst versuchen, die BESTEHENDE ShapeID zu aktualisieren
                            # statt immer neue Shapes zu registrieren
                            existing_id = self._find_exact_shape_id_by_ocp_shape(modified_shape)

                            if existing_id:
                                # Shape ist bereits registriert - weiter zur nächsten
                                output_uuids.append(existing_id.uuid)
                                if existing_id not in new_shape_ids:
                                    new_shape_ids.append(existing_id)
                            else:
                                # TNP v4.1: Versuche die ShapeID mit neuer Geometrie zu aktualisieren
                                # (bevor neue ShapeID erstellt wird)
                                if self.update_shape_id_after_operation(
                                    old_shape=record.ocp_shape,
                                    new_shape=modified_shape,
                                    feature_id=feature_id,
                                    operation_type=f"chamfer_{feature_id}"
                                ):
                                    # Erfolgreich aktualisiert - gleiche UUID bleibt erhalten
                                    output_uuids.append(record.shape_id.uuid)
                                    if record.shape_id not in new_shape_ids:
                                        new_shape_ids.append(record.shape_id)
                                    if is_enabled("tnp_debug_logging"):
                                        logger.debug(
                                            f"TNP Chamfer: {input_shape_id.uuid[:8]} aktualisiert (ShapeID behalten)"
                                        )
                                else:
                                    # Update fehlgeschlagen - neue ShapeID erstellen
                                    shape_type = ShapeType.FACE if modified_shape.ShapeType() == TopAbs_FACE else ShapeType.EDGE
                                    new_id = self.register_shape(
                                        ocp_shape=modified_shape,
                                        shape_type=shape_type,
                                        feature_id=feature_id,
                                        local_index=len(new_shape_ids)
                                    )
                                    new_shape_ids.append(new_id)
                                    output_uuids.append(new_id.uuid)

                        if output_uuids:
                            manual_mappings[input_shape_id.uuid] = output_uuids

                            if is_enabled("tnp_debug_logging"):
                                logger.debug(
                                    f"TNP Chamfer: {input_shape_id.uuid[:8]} → "
                                    f"{len(output_uuids)} Shapes gemappt"
                                )

                # OperationRecord erstellen
                if manual_mappings or new_shape_ids:
                    op_record = OperationRecord(
                        operation_type="CHAMFER",
                        feature_id=feature_id,
                        input_shape_ids=[sid for sid in self._shapes.values()
                                        if sid.shape_id.uuid in manual_mappings],
                        output_shape_ids=new_shape_ids,
                        occt_history=occt_history,
                        manual_mappings=manual_mappings,
                        metadata={
                            "distance": distance,
                            "mappings_count": len(manual_mappings),
                            "new_shapes": len(new_shape_ids),
                        }
                    )
                    self.record_operation(op_record)

                    if is_enabled("tnp_debug_logging"):
                        logger.success(
                            f"TNP v4.0: Chamfer History getrackt - "
                            f"{len(manual_mappings)} mappings, {len(new_shape_ids)} neue Shapes"
                        )
                    return op_record

            # Fallback: Alle neuen Edges im Result-Solid registrieren
            new_edge_count = self._register_unmapped_edges(
                result_solid=result_solid,
                feature_id=feature_id,
                existing_mappings=[],
                start_local_index=0,
            )

            if is_enabled("tnp_debug_logging"):
                logger.info(f"TNP Chamfer Fallback: {new_edge_count} neue Edges registriert")

            # Minimaler OperationRecord für Fallback
            op_record = OperationRecord(
                operation_type="CHAMFER",
                feature_id=feature_id,
                input_shape_ids=[],
                output_shape_ids=[],
                occt_history=occt_history,
                manual_mappings={},
                metadata={
                    "distance": distance,
                    "fallback_mode": True,
                    "new_edges": new_edge_count,
                }
            )
            self.record_operation(op_record)
            return op_record

        except Exception as e:
            if is_enabled("tnp_debug_logging"):
                logger.error(f"TNP v4.0: Chamfer Tracking fehlgeschlagen: {e}")
            import traceback
            traceback.print_exc()
            return None

    def track_sketch_extrude(
        self,
        feature_id: str,
        sketch: Any,
        result_solid: Any,
        distance: float,
        direction: Tuple[float, float, float] = (0, 0, 1),
        plane_origin: Tuple[float, float, float] = (0, 0, 0),
        plane_normal: Tuple[float, float, float] = (0, 0, 1),
    ) -> Optional[OperationRecord]:
        """
        TNP v4.1: Trackt eine Sketch-Extrusion und erstellt Mappings von
        Sketch-Elementen zu den generierten 3D-Edges.

        Args:
            feature_id: ID des ExtrudeFeature
            sketch: Der Sketch der extrudiert wurde
            result_solid: Das resultierende Solid nach Extrusion
            distance: Extrusionsdistanz
            direction: Extrusionsrichtung (Vektor)
            plane_origin: Ursprung der Sketch-Ebene
            plane_normal: Normale der Sketch-Ebene

        Returns:
            OperationRecord mit Edge-Mappings, oder None
        """
        if not HAS_OCP:
            return None

        try:
            from OCP.TopExp import TopExp_Explorer
            from OCP.TopAbs import TopAbs_EDGE
            from OCP.TopoDS import TopoDS
            import numpy as np

            if is_enabled("tnp_debug_logging"):
                logger.info(f"TNP v4.1: Tracke Sketch-Extrusion '{feature_id}'")

            # Mapping-Dictionary: Sketch-Element-ID -> 3D-Edge-ShapeUUID
            sketch_edge_mappings: Dict[str, str] = {}
            new_shape_ids: List[ShapeID] = []

            # Sketch-ShapeUUIDs sammeln
            sketch_uuids = sketch.get_all_shape_uuids() if hasattr(sketch, 'get_all_shape_uuids') else {}

            # Alle Edges im result Solid sammeln
            result_shape = result_solid.wrapped if hasattr(result_solid, 'wrapped') else result_solid
            edge_map = {}
            try:
                from OCP.TopTools import TopTools_IndexedMapOfShape
                from OCP.TopExp import TopExp
                e_map = TopTools_IndexedMapOfShape()
                TopExp.MapShapes_s(result_shape, TopAbs_EDGE, e_map)
                for i in range(e_map.Extent()):
                    edge = e_map.FindKey(i + 1)
                    edge_map[id(edge)] = edge
            except Exception:
                # Fallback: direct iteration
                for edge in result_solid.edges():
                    edge_map[id(edge)] = edge.wrapped

            # Für jedes Sketch-Element (Line, Circle, Arc) die passende 3D-Edge finden
            element_types = ['line', 'circle', 'arc']

            for elem_type in element_types:
                uuids_attr = f'_{elem_type}_shape_uuids'
                if not hasattr(sketch, uuids_attr):
                    continue

                element_uuids = getattr(sketch, uuids_attr, {})
                if not element_uuids:
                    continue

                # Jedes Sketch-Element durchgehen
                for elem_id, elem_uuid in element_uuids.items():
                    # Finde die Edge im result Solid die diesem Element entspricht
                    # Strategie: Die Edge muss in der Extrusionsrichtung liegen
                    best_match_edge = None
                    best_score = float('inf')

                    for edge_id, ocp_edge in edge_map.items():
                        try:
                            # Build123d Edge für Center-Berechnung
                            from build123d import Edge as B123Edge
                            b123_edge = B123Edge(ocp_edge)
                            center = b123_edge.center()
                            edge_center = np.array([center.X, center.Y, center.Z])
                            edge_length = b123_edge.length if hasattr(b123_edge, 'length') else 0

                            # Erwartete Position basierend auf Sketch-Element
                            # Lines/Circles/Arcs haben 2D-Position + plane transform
                            # Wir suchen die Edge die in Extrusionsrichtung "oben" liegt
                            # Distance von plane_origin + distance in direction
                            expected_tip = np.array(plane_origin) + np.array(direction) * distance

                            # Score basierend auf Nähe zur erwarteten Position
                            dist_to_tip = np.linalg.norm(edge_center - expected_tip)

                            # Sketch-Elemente sind typischerweise am "unteren" Ende der Extrusion
                            # und laufen in direction distance hoch
                            dist_score = dist_to_tip

                            # Länge-Score: Kürzere Distanz ist besser
                            if dist_score < best_score:
                                best_score = dist_score
                                best_match_edge = ocp_edge

                        except Exception:
                            continue

                    if best_match_edge is not None:
                        # ShapeID für die gefundene Edge registrieren
                        edge_shape_id = self.register_shape(
                            ocp_shape=best_match_edge,
                            shape_type=ShapeType.EDGE,
                            feature_id=feature_id,
                            local_index=len(new_shape_ids),
                            geometry_data=None,  # Wird von register_shape berechnet
                        )
                        new_shape_ids.append(edge_shape_id)

                        # Mapping speichern: Sketch-Element-ID -> Edge-ShapeUUID
                        sketch_edge_mappings[elem_id] = edge_shape_id.uuid

                        if is_enabled("tnp_debug_logging"):
                            logger.debug(
                                f"TNP v4.1: Sketch {elem_type} '{elem_id}' -> "
                                f"Edge {edge_shape_id.uuid[:8]}..."
                            )

            # OperationRecord erstellen
            op_record = OperationRecord(
                operation_type="SKETCH_EXTRUDE",
                feature_id=feature_id,
                input_shape_ids=[],  # Sketch-Elemente haben keine 3D-Shapes vor Extrusion
                output_shape_ids=new_shape_ids,
                occt_history=None,
                manual_mappings={},  # Direct mappings stored in sketch_edge_mappings
                metadata={
                    "distance": distance,
                    "direction": direction,
                    "plane_origin": plane_origin,
                    "plane_normal": plane_normal,
                    "sketch_elements_mapped": len(sketch_edge_mappings),
                    "mapping_mode": "sketch_to_3d",
                }
            )

            self.record_operation(op_record)

            if is_enabled("tnp_debug_logging"):
                logger.success(
                    f"TNP v4.1: Sketch-Extrusion getrackt - "
                    f"{len(sketch_edge_mappings)} Elemente -> 3D Edges"
                )

            # Rückgabe auch des Mapping-Dictionaries für ExtrudeFeature
            return op_record

        except Exception as e:
            if is_enabled("tnp_debug_logging"):
                logger.error(f"TNP v4.1: Sketch-Extrusion Tracking fehlgeschlagen: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _find_exact_shape_id_by_ocp_shape(self, ocp_shape: Any) -> Optional[ShapeID]:
        """
        Findet eine ShapeID per exakter OCP-Topologie-Identität (IsSame).
        Hilfsmethode für History-Tracking Deduplizierung.
        """
        try:
            for record in reversed(list(self._shapes.values())):
                if record.ocp_shape is None:
                    continue
                try:
                    if record.ocp_shape.IsSame(ocp_shape):
                        return record.shape_id
                except Exception:
                    continue
        except Exception:
            pass
        return None


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
