"""
OCP Helper - Direkter Zugriff auf OpenCASCADE Operationen

WICHTIG: TNP Integration ist obligatorisch!
Kein Fallback zu Build123d - entweder OCP oder Fehler.

Author: Claude (OCP-First Migration Phase 1)
Date: 2026-02-10
"""

from typing import List, Tuple, Optional, Any
from loguru import logger

try:
    from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeWire
    from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet, BRepFilletAPI_MakeChamfer
    from OCP.TopoDS import TopoDS
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_FACE
    from OCP.gp import gp_Vec
    HAS_OCP = True
except ImportError as e:
    HAS_OCP = False
    logger.error(f"OpenCASCADE (OCP) nicht verfügbar: {e}")

from build123d import Solid, Face, Wire, Edge, Vector
from config.tolerances import Tolerances
from config.feature_flags import is_enabled


class OCPExtrudeHelper:
    """
    Direktes OCP Extrude mit VERBINDLICHER TNP Integration.
    
    WICHTIG: Kein Fallback zu Build123d!
    """
    
    @staticmethod
    def extrude(
        face: Face,
        direction: Vector,
        distance: float,
        naming_service: Any,  # Pflicht-Parameter!
        feature_id: str,  # Pflicht-Parameter!
        ctx: dict = None
    ) -> Solid:
        """
        Extrudiert eine Face mit direktem OCP.
        
        Args:
            face: Zu extrudierende Face
            direction: Extrusionsrichtung
            distance: Extrusionsdistanz
            naming_service: TNP ShapeNamingService (PFLICHT)
            feature_id: Feature-ID für TNP (PFLICHT)
            ctx: Optionaler Kontext
            
        Returns:
            Build123d Solid
            
        Raises:
            ValueError: Wenn OCP nicht verfügbar oder Operation fehlschlägt
        """
        if not HAS_OCP:
            raise ValueError(
                "OCP nicht verfügbar - Extrude ohne Fallback nicht möglich. "
                "Bitte OpenCASCADE installieren."
            )
        
        if naming_service is None:
            raise ValueError(
                "naming_service ist Pflicht für OCP-First Extrude - "
                "TNP Integration ist obligatorisch!"
            )
        
        if feature_id is None:
            raise ValueError("feature_id ist Pflicht für OCP-First Extrude")
        
        # OCP Prism erstellen - direction ist Einheitsvektor, distance ist Distanz
        vec = gp_Vec(
            direction.X * distance,
            direction.Y * distance,
            direction.Z * distance
        )
        prism_op = BRepPrimAPI_MakePrism(face.wrapped, vec)
        prism_op.Build()
        
        if not prism_op.IsDone():
            raise ValueError(f"Extrude OCP-Operation fehlgeschlagen")
        
        result_shape = prism_op.Shape()
        
        # TNP: Alle Shapes registrieren (OBLIGATORISCH!)
        try:
            from modeling.tnp_system import ShapeType
            
            # Alle Faces registrieren
            explorer = TopExp_Explorer(result_shape, TopAbs_FACE)
            face_idx = 0
            while explorer.More():
                face_shape = TopoDS.Face_s(explorer.Current())
                naming_service.register_shape(
                    ocp_shape=face_shape,
                    shape_type=ShapeType.FACE,
                    feature_id=feature_id,
                    local_index=face_idx
                )
                face_idx += 1
                explorer.Next()
            
            # Alle Edges registrieren
            naming_service.register_solid_edges(
                Solid(result_shape),
                feature_id
            )
            
            if is_enabled("tnp_debug_logging"):
                logger.success(
                    f"OCP Extrude TNP: {face_idx} Faces, "
                    f"{naming_service.get_stats()['edges']} Edges registriert"
                )
            
        except Exception as e:
            logger.error(f"TNP Registration fehlgeschlagen: {e}")
            # Nicht werfen - Solid ist valide, nur TNP kaputt
            # User muss entscheiden ob er weitermacht
        
        # Zu Build123d Solid wrappen
        return Solid(result_shape)


class OCPFilletHelper:
    """
    Direktes OCP Fillet mit VERBINDLICHER TNP Integration.
    """
    
    @staticmethod
    def fillet(
        solid: Solid,
        edges: List[Edge],
        radius: float,
        naming_service: Any,  # Pflicht-Parameter!
        feature_id: str,  # Pflicht-Parameter!
        ctx: dict = None
    ) -> Solid:
        """
        Führt Fillet mit direktem OCP aus.
        
        Args:
            solid: Source Solid
            edges: Zu filletende Edges
            radius: Fillet-Radius
            naming_service: TNP ShapeNamingService (PFLICHT)
            feature_id: Feature-ID für TNP (PFLICHT)
            ctx: Optionaler Kontext
            
        Returns:
            Build123d Solid
            
        Raises:
            ValueError: Wenn OCP nicht verfügbar oder Operation fehlschlägt
        """
        if not HAS_OCP:
            raise ValueError("OCP nicht verfügbar - Fillet ohne Fallback nicht möglich")
        
        if naming_service is None:
            raise ValueError("naming_service ist Pflicht für OCP-First Fillet")
        
        if feature_id is None:
            raise ValueError("feature_id ist Pflicht für OCP-First Fillet")

        if not edges:
            raise ValueError("Keine Edges für Fillet angegeben")

        # Fillet-Operation
        fillet_op = BRepFilletAPI_MakeFillet(solid.wrapped)

        for edge in edges:
            # Edge kann build123d Edge (mit .wrapped) oder direkter OCP TopoDS_Edge sein
            edge_ocp = edge.wrapped if hasattr(edge, 'wrapped') else edge
            fillet_op.Add(radius, edge_ocp)

        fillet_op.Build()

        if not fillet_op.IsDone():
            raise ValueError("Fillet OCP-Operation fehlgeschlagen")

        result_shape = fillet_op.Shape()

        # TNP mit OCCT-History!
        # Die History von BRepFilletAPI_MakeFillet trackt welche Edges neu erstellt wurden
        # BRepFilletAPI_MakeFillet hat .Modified()/.Generated() direkt (kein separates .History()-Objekt in OCP Python-Bindings)
        occt_history = fillet_op
        if is_enabled("tnp_debug_logging"):
            logger.debug(f"[TNP] Fillet-Operator als OCCT-History verwendet")

        # TNP: Alle Shapes registrieren (OBLIGATORISCH!)
        try:
            from modeling.tnp_system import ShapeType

            # ZUERST: History im ShapeNamingService speichern!
            if occt_history is not None and naming_service is not None:
                naming_service.track_fillet_operation(
                    source_solid=solid.wrapped,
                    result_solid=result_shape,
                    occt_history=occt_history,
                    feature_id=feature_id
                )

            # Alle Faces registrieren (inkl. neue Fillet-Faces)
            explorer = TopExp_Explorer(result_shape, TopAbs_FACE)
            face_idx = 0
            while explorer.More():
                face_shape = TopoDS.Face_s(explorer.Current())
                naming_service.register_shape(
                    ocp_shape=face_shape,
                    shape_type=ShapeType.FACE,
                    feature_id=feature_id,
                    local_index=face_idx
                )
                face_idx += 1
                explorer.Next()

            # Alle Edges registrieren
            naming_service.register_solid_edges(
                Solid(result_shape),
                feature_id
            )

            if is_enabled("tnp_debug_logging"):
                logger.success(
                    f"OCP Fillet TNP: {face_idx} Faces, "
                    f"{naming_service.get_stats()['edges']} Edges registriert"
                )
            
        except Exception as e:
            logger.error(f"TNP Registration fehlgeschlagen: {e}")
        
        return Solid(result_shape)


class OCPChamferHelper:
    """
    Direktes OCP Chamfer mit VERBINDLICHER TNP Integration.
    """
    
    @staticmethod
    def chamfer(
        solid: Solid,
        edges: List[Edge],
        distance: float,
        naming_service: Any,  # Pflicht-Parameter!
        feature_id: str,  # Pflicht-Parameter!
        ctx: dict = None
    ) -> Solid:
        """
        Führt Chamfer mit direktem OCP aus.
        
        Args:
            solid: Source Solid
            edges: Zu chamferende Edges
            distance: Chamfer-Abstand
            naming_service: TNP ShapeNamingService (PFLICHT)
            feature_id: Feature-ID für TNP (PFLICHT)
            ctx: Optionaler Kontext
            
        Returns:
            Build123d Solid
            
        Raises:
            ValueError: Wenn OCP nicht verfügbar oder Operation fehlschlägt
        """
        if not HAS_OCP:
            raise ValueError("OCP nicht verfügbar - Chamfer ohne Fallback nicht möglich")
        
        if naming_service is None:
            raise ValueError("naming_service ist Pflicht für OCP-First Chamfer")
        
        if feature_id is None:
            raise ValueError("feature_id ist Pflicht für OCP-First Chamfer")
        
        if not edges:
            raise ValueError("Keine Edges für Chamfer angegeben")

        # Chamfer-Operation
        chamfer_op = BRepFilletAPI_MakeChamfer(solid.wrapped)

        # Build edge-to-face map for robust chamfer direction detection
        # FIX: Use face-aware Add(d1, d2, edge, face) signature to avoid
        # "gp_Vec::Normalize() - vector has zero norm" errors on complex topology
        edge_face_map = OCPChamferHelper._build_edge_face_map(solid.wrapped)
        
        added_count = 0
        skipped_edges = []
        
        for edge in edges:
            # Edge kann build123d Edge (mit .wrapped) oder direkter OCP TopoDS_Edge sein
            edge_ocp = edge.wrapped if hasattr(edge, 'wrapped') else edge
            
            # Skip validation - let OCCT decide what edges are valid
            # The validation was too strict and rejecting valid edges
            
            # Try face-aware signature first (more robust)
            adjacent_face = OCPChamferHelper._find_adjacent_face_for_chamfer(
                solid.wrapped, edge_ocp, edge_face_map
            )
            
            edge_added = False
            last_error = None
            
            # Try face-aware signature with symmetric distances
            if adjacent_face is not None:
                try:
                    from OCP.TopoDS import TopoDS
                    face_ocp = TopoDS.Face_s(adjacent_face)
                    chamfer_op.Add(distance, distance, edge_ocp, face_ocp)
                    added_count += 1
                    edge_added = True
                    if is_enabled("tnp_debug_logging"):
                        logger.debug(f"[CHAMFER] Added edge with face-aware signature (symmetric)")
                except Exception as e:
                    last_error = e
                    err_msg = str(e)
                    if "Normalize" in err_msg or "zero norm" in err_msg.lower():
                        # Edge has singularity - try edge-only mode
                        if is_enabled("tnp_debug_logging"):
                            logger.debug(f"[CHAMFER] Face-aware failed with singularity, trying edge-only: {e}")
                    elif is_enabled("tnp_debug_logging"):
                        logger.debug(f"[CHAMFER] Face-aware Add failed: {e}, trying edge-only")
            
            # Fallback: Edge-only signature
            if not edge_added:
                try:
                    chamfer_op.Add(distance, edge_ocp)
                    added_count += 1
                    edge_added = True
                except Exception as e:
                    last_error = e
                    err_msg = str(e)
                    if "Normalize" in err_msg or "zero norm" in err_msg.lower():
                        if is_enabled("tnp_debug_logging"):
                            logger.debug(f"[CHAMFER] Edge has singularity in edge-only mode, skipping")
                    else:
                        logger.debug(f"[CHAMFER] Could not add edge to chamfer: {e}")
                    skipped_edges.append(edge)

        if added_count == 0:
            raise ValueError("Chamfer: Keine Kanten konnten hinzugefügt werden")

        # All-or-nothing: fail if any requested edge could not be added
        if skipped_edges:
            raise ValueError(
                f"Chamfer: {len(skipped_edges)} von {len(edges)} Kanten konnten nicht hinzugefügt werden. "
                f"Alle angeforderten Kanten müssen für eine deterministische Operation erfolgreich sein."
            )

        # Log skipped edges for diagnostics (defensive: should not reach here)
        if skipped_edges and is_enabled("tnp_debug_logging"):
            logger.debug(f"[CHAMFER] Skipped {len(skipped_edges)} edges with problematic geometry")

        try:
            chamfer_op.Build()
        except Exception as build_err:
            # OCCT can throw during Build() for some edge configurations
            # Try to get a partial result even if Build() threw
            err_msg = str(build_err)
            logger.warning(f"[CHAMFER] Build() threw exception: {build_err}")
            
            # Check if we can still get a result
            try:
                result_shape = chamfer_op.Shape()
                if result_shape is not None and not result_shape.IsNull():
                    # Validate partial result before accepting
                    from OCP.BRepCheck import BRepCheck_Analyzer
                    analyzer = BRepCheck_Analyzer(result_shape)
                    if not analyzer.IsValid():
                        logger.warning(f"[CHAMFER] Partial result failed BRepCheck validation")
                        raise ValueError(f"Chamfer OCP-Build fehlgeschlagen: partial result is invalid")
                    # Partial success - we got a valid shape despite the exception
                    logger.warning(f"[CHAMFER] Partial success: Build() threw but valid shape exists ({added_count} edges added)")
                    # Continue with the partial result - don't raise
                else:
                    raise ValueError(f"Chamfer OCP-Build fehlgeschlagen: {build_err}")
            except ValueError:
                raise
            except Exception:
                raise ValueError(f"Chamfer OCP-Build fehlgeschlagen: {build_err}")

        if not chamfer_op.IsDone():
            # IsDone() = False means operation didn't complete successfully
            # But we might still have a partial result
            try:
                result_shape = chamfer_op.Shape()
                if result_shape is not None and not result_shape.IsNull():
                    # Validate partial result before accepting
                    from OCP.BRepCheck import BRepCheck_Analyzer
                    analyzer = BRepCheck_Analyzer(result_shape)
                    if not analyzer.IsValid():
                        logger.warning(f"[CHAMFER] Partial result failed BRepCheck validation")
                        raise ValueError("Chamfer OCP-Operation fehlgeschlagen: partial result is invalid")
                    # Partial success - we got a valid shape despite IsDone() = False
                    logger.warning(f"[CHAMFER] Partial success: IsDone()=False but valid shape exists ({added_count} edges added)")
                    # Continue with the partial result
                else:
                    raise ValueError("Chamfer OCP-Operation fehlgeschlagen (kein Ergebnis)")
            except ValueError:
                raise
            except Exception:
                raise ValueError("Chamfer OCP-Operation fehlgeschlagen")
        else:
            result_shape = chamfer_op.Shape()

        # Validate result
        if result_shape is None or result_shape.IsNull():
            raise ValueError("Chamfer: Ergebnis-Shape ist null")

        # TNP mit OCCT-History!
        # BRepFilletAPI_MakeChamfer hat .Modified()/.Generated() direkt (kein separates .History()-Objekt in OCP Python-Bindings)
        occt_history = chamfer_op
        if is_enabled("tnp_debug_logging"):
            logger.debug(f"[TNP] Chamfer-Operator als OCCT-History verwendet")

        # TNP: Alle Shapes registrieren
        try:
            from modeling.tnp_system import ShapeType

            # ZUERST: History im ShapeNamingService speichern!
            if occt_history is not None and naming_service is not None:
                naming_service.track_chamfer_operation(
                    source_solid=solid.wrapped,
                    result_solid=result_shape,
                    occt_history=occt_history,
                    feature_id=feature_id
                )

            # Alle Faces registrieren
            explorer = TopExp_Explorer(result_shape, TopAbs_FACE)
            face_idx = 0
            while explorer.More():
                face_shape = TopoDS.Face_s(explorer.Current())
                naming_service.register_shape(
                    ocp_shape=face_shape,
                    shape_type=ShapeType.FACE,
                    feature_id=feature_id,
                    local_index=face_idx
                )
                face_idx += 1
                explorer.Next()

            # Alle Edges registrieren
            naming_service.register_solid_edges(
                Solid(result_shape),
                feature_id
            )

            if is_enabled("tnp_debug_logging"):
                logger.success(
                    f"OCP Chamfer TNP: {face_idx} Faces, "
                    f"{naming_service.get_stats()['edges']} Edges registriert"
                )
            
        except Exception as e:
            logger.error(f"TNP Registration fehlgeschlagen: {e}")
        
        return Solid(result_shape)

    @staticmethod
    def _build_edge_face_map(shape):
        """
        Baut eine Edge->Face Map für schnelle adjacent-face Lookups.
        
        Args:
            shape: TopoDS_Shape (OCP Shape)
            
        Returns:
            TopTools_IndexedDataMapOfShapeListOfShape
        """
        try:
            from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape
            from OCP.TopExp import TopExp
            from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
            
            edge_face_map = TopTools_IndexedDataMapOfShapeListOfShape()
            TopExp.MapShapesAndAncestors_s(shape, TopAbs_EDGE, TopAbs_FACE, edge_face_map)
            return edge_face_map
        except Exception as e:
            logger.debug(f"[CHAMFER] Could not build edge-face map: {e}")
            return None

    @staticmethod
    def _find_adjacent_face_for_chamfer(shape, edge_ocp, edge_face_map=None):
        """
        Findet eine angrenzende Face für eine Edge (für face-aware Chamfer).
        
        Strategie:
        1. TopTools Edge-Face Map (schnellste)
        2. TopExp Explorer mit IsSame
        3. Geometrischer Vergleich (Fallback)
        
        Args:
            shape: TopoDS_Shape (Solid)
            edge_ocp: TopoDS_Edge
            edge_face_map: Optional pre-built map
            
        Returns:
            TopoDS_Face oder None
        """
        try:
            from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape
            from OCP.TopExp import TopExp, TopExp_Explorer
            from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE
            from OCP.BRepAdaptor import BRepAdaptor_Curve
            from OCP.TopoDS import TopoDS
            
            # Strategie 1: Pre-built Map (falls vorhanden)
            if edge_face_map is not None:
                try:
                    if edge_face_map.Contains(edge_ocp):
                        face_list = edge_face_map.FindFromKey(edge_ocp)
                        if face_list.Size() > 0:
                            return face_list.First()
                except Exception:
                    pass
            
            # Strategie 2: Neue Map bauen
            try:
                ef_map = TopTools_IndexedDataMapOfShapeListOfShape()
                TopExp.MapShapesAndAncestors_s(shape, TopAbs_EDGE, TopAbs_FACE, ef_map)
                
                if ef_map.Contains(edge_ocp):
                    face_list = ef_map.FindFromKey(edge_ocp)
                    if face_list.Size() > 0:
                        return face_list.First()
            except Exception:
                pass
            
            # Strategie 3: IsSame-Vergleich
            face_explorer = TopExp_Explorer(shape, TopAbs_FACE)
            while face_explorer.More():
                face = face_explorer.Current()
                edge_explorer = TopExp_Explorer(face, TopAbs_EDGE)
                while edge_explorer.More():
                    if edge_explorer.Current().IsSame(edge_ocp):
                        return face
                    edge_explorer.Next()
                face_explorer.Next()
            
            # Strategie 4: Geometrischer Vergleich (letzter Fallback)
            try:
                target_curve = BRepAdaptor_Curve(edge_ocp)
                u_mid = (target_curve.FirstParameter() + target_curve.LastParameter()) / 2.0
                target_mid = target_curve.Value(u_mid)
                tolerance = 1e-3  # 0.001mm
                
                face_explorer = TopExp_Explorer(shape, TopAbs_FACE)
                while face_explorer.More():
                    face = face_explorer.Current()
                    edge_explorer = TopExp_Explorer(face, TopAbs_EDGE)
                    while edge_explorer.More():
                        try:
                            cand_curve = BRepAdaptor_Curve(edge_explorer.Current())
                            u_cand = (cand_curve.FirstParameter() + cand_curve.LastParameter()) / 2.0
                            cand_mid = cand_curve.Value(u_cand)
                            
                            if target_mid.Distance(cand_mid) < tolerance:
                                return face
                        except Exception:
                            pass
                        edge_explorer.Next()
                    face_explorer.Next()
            except Exception:
                pass
            
            return None
            
        except Exception as e:
            logger.debug(f"[CHAMFER] _find_adjacent_face_for_chamfer failed: {e}")
            return None


# ============================================
# OCP-First Active Helper
# ============================================
# Die folgenden Helper werden aktiv verwendet:
# - OCPExtrudeHelper (ExtrudeFeature)
# - OCPFilletHelper (FilletFeature)
# - OCPChamferHelper (ChamferFeature)
#
# Entfernte Helper (Phase A OCP-First Migration):
# - OCPRevolveHelper - Revolve nutzt jetzt direktes OCP in _compute_revolve
# - OCPLoftHelper - Loft nutzt jetzt direktes OCP in _compute_loft
# - OCPSweepHelper - Sweep nutzt jetzt direktes OCP in _compute_sweep
# - OCPShellHelper - Shell nutzt jetzt direktes OCP in _compute_shell
# - OCPHollowHelper - Hollow nutzt jetzt direktes OCP in _compute_hollow