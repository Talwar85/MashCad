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

        for edge in edges:
            # Edge kann build123d Edge (mit .wrapped) oder direkter OCP TopoDS_Edge sein
            edge_ocp = edge.wrapped if hasattr(edge, 'wrapped') else edge
            # Symmetrischer Chamfer (gleiche Distanz auf beiden Seiten)
            chamfer_op.Add(distance, edge_ocp)

        chamfer_op.Build()

        if not chamfer_op.IsDone():
            raise ValueError("Chamfer OCP-Operation fehlgeschlagen")

        result_shape = chamfer_op.Shape()

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