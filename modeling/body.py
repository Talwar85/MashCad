"""
Body - 3D-Körper (Body) mit RobustPartBuilder Logik

Phase 2 TNP: Integrierter TNP-Tracker für robuste Shape-Referenzierung.
"""

from dataclasses import asdict, dataclass, field
import tempfile
from typing import List, Optional, Tuple, Union, Any
from enum import Enum, auto
import math
import uuid
import sys
import os
import traceback
from loguru import logger

# Import HAS_OCP and HAS_BUILD123D flags
HAS_BUILD123D = False
HAS_OCP = False

try:
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
    from OCP.BRepBuilderAPI import (
        BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire, BRepBuilderAPI_MakeFace,
        BRepBuilderAPI_MakeSolid, BRepBuilderAPI_Sewing
    )
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse, BRepAlgoAPI_Cut, BRepAlgoAPI_Common
    from OCP.BRepOffsetAPI import BRepOffsetAPI_MakePipe
    from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet, BRepFilletAPI_MakeChamfer
    from OCP.StlAPI import StlAPI_Writer
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.TopoDS import TopoDS_Shape, TopoDS_Solid, TopoDS_Face, TopoDS_Edge, TopoDS_Wire
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE, TopAbs_SOLID
    from OCP.gp import gp_Pnt, gp_Vec, gp_Dir, gp_Ax1, gp_Ax2, gp_Pln, gp_Trsf
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.ShapeFix import ShapeFix_Shape, ShapeFix_Solid
    from OCP.BRepCheck import BRepCheck_Analyzer
    HAS_OCP = True
except ImportError as e:
    logger.warning(f"! OCP nicht gefunden: {e}")

try:
    from build123d import (
        Box, Cylinder, Sphere, Solid, Shape,
        extrude, revolve, fillet, chamfer,
        loft, sweep, offset,
        Axis, Plane, Locations, Vector,
        BoundBox,
        BuildPart, BuildSketch, BuildLine,
        Part, Sketch as B123Sketch,
        Rectangle as B123Rect, Circle as B123Circle,
        Polyline, Polygon, make_face, Mode,
        export_stl, export_step,
        GeomType
    )
    HAS_BUILD123D = True
    if not hasattr(BoundBox, "bounding_box"):
        @staticmethod
        def _compat_bounding_box(shape):
            return shape.bounding_box() if hasattr(shape, "bounding_box") else BoundBox(shape)
        BoundBox.bounding_box = _compat_bounding_box
    def _compat_geomtype_call(self):
        return self
    GeomType.__call__ = _compat_geomtype_call
except ImportError as e:
    logger.warning(f"! build123d nicht gefunden: {e}")

# Core imports
from . import brep_cache
from modeling.cad_tessellator import CADTessellator
from config.tolerances import Tolerances
from config.feature_flags import is_enabled
from meshconverter.direct_mesh_converter import DirectMeshConverter
from meshconverter.brep_optimizer import BRepOptimizer
from modeling.mesh_converter import MeshToBREPConverter
from modeling.result_types import OperationResult, BooleanResult, ResultStatus
from modeling.geometry_validator import GeometryValidator, ValidationResult, ValidationLevel
from modeling.geometry_healer import GeometryHealer, HealingResult, HealingStrategy
from modeling.nurbs import NURBSCurve, NURBSSurface, ContinuityMode, CurveType
from modeling.step_io import STEPWriter, STEPReader, STEPSchema, export_step as step_export
from modeling.feature_dependency import FeatureDependencyGraph, get_dependency_graph
from modeling.boolean_engine_v4 import BooleanEngineV4

# TNP v4.0
from modeling.tnp_system import (
    ShapeNamingService, ShapeID, ShapeType,
    OperationRecord
)

# OCP-First Migration
from modeling.ocp_helpers import (
    OCPExtrudeHelper,
    OCPFilletHelper,
    OCPChamferHelper
)

# Body Serialization (extracted module)
from modeling.body_serialization import (
    body_to_dict,
    body_from_dict,
    _normalize_status_details_for_load,
)

# Body Mixins (extracted modules)
from modeling.body_rebuild import BodyRebuildMixin
from modeling.body_resolve import BodyResolveMixin
from modeling.body_extrude import BodyExtrudeMixin
from modeling.body_compute_mixin import BodyComputeMixin
from modeling.body_compute_extended import BodyComputeExtendedMixin

# AR-002/AR-003 extracted modules
from modeling.geometry_utils import (
    solid_metrics,
    canonicalize_indices,
    get_face_center,
    get_face_area,
    validate_plane_normal,
    format_index_refs_for_error,
    format_shape_refs_for_error,
    collect_feature_reference_diagnostics,
    collect_feature_reference_payload,
    _solid_metrics,
    _canonicalize_indices,
    _get_face_center,
    _get_face_area,
    _format_index_refs_for_error,
    _format_shape_refs_for_error,
    _collect_feature_reference_diagnostics,
    _collect_feature_reference_payload,
)

from modeling.shape_builders import (
    convert_legacy_nsided_edge_selectors,
    convert_legacy_edge_selectors,
    convert_line_profiles_to_polygons,
    filter_profiles_by_selector,
    get_plane_from_sketch,
    lookup_geometry_for_polygon,
    make_wire_from_mixed_geometry,
    _convert_legacy_nsided_edge_selectors,
    _convert_legacy_edge_selectors,
    _convert_line_profiles_to_polygons,
    _filter_profiles_by_selector,
    _get_plane_from_sketch,
    _lookup_geometry_for_polygon,
    _make_wire_from_mixed_geometry,
)

from modeling.feature_operations import (
    record_tnp_failure,
    consume_tnp_failure,
    classify_error_code,
    default_next_action_for_code,
    build_operation_error_details,
    normalize_status_details_for_load,
    safe_operation,
    _record_tnp_failure,
    _consume_tnp_failure,
    _classify_error_code,
    _default_next_action_for_code,
    _build_operation_error_details,
    _normalize_status_details_for_load,
    _safe_operation,
)

from modeling.body_state import (
    serialize_shape_id,
    deserialize_shape_id,
    serialize_shape_ids,
    deserialize_shape_ids,
    serialize_feature,
    serialize_feature_base,
    compare_body_states,
    body_state_summary,
    serialize_brep,
    deserialize_brep,
    _serialize_shape_id,
    _deserialize_shape_id,
    _serialize_shape_ids,
    _deserialize_shape_ids,
    _serialize_feature,
    _serialize_feature_base,
    _compare_body_states,
    _body_state_summary,
    _serialize_brep,
    _deserialize_brep,
)

# Feature imports
from modeling.features.base import Feature, FeatureType
from modeling.features.extrude import ExtrudeFeature, PushPullFeature
from modeling.features.revolve import RevolveFeature
from modeling.features.fillet_chamfer import FilletFeature, ChamferFeature
from modeling.features.pattern import PatternFeature
from modeling.features.boolean import BooleanFeature
from modeling.features.transform import TransformFeature
from modeling.features.advanced import (
    LoftFeature, SweepFeature, ShellFeature, HoleFeature,
    DraftFeature, SplitFeature, ThreadFeature, HollowFeature,
    NSidedPatchFeature, SurfaceTextureFeature, PrimitiveFeature,
    LatticeFeature
)
from modeling.features.import_feature import ImportFeature
from modeling.construction import ConstructionPlane

# Sketch import
from sketcher import Sketch


class Body(BodyRebuildMixin, BodyResolveMixin, BodyExtrudeMixin, BodyComputeMixin, BodyComputeExtendedMixin):
    """
    3D-KÃ¶rper (Body) mit RobustPartBuilder Logik.

    Phase 2 TNP: Integrierter TNP-Tracker fÃ¼r robuste Shape-Referenzierung.
    
    Note: Methods are organized in mixins:
    - BodyRebuildMixin: _rebuild() and related methods
    - BodyResolveMixin: _resolve_* methods for TNP
    - BodyExtrudeMixin: _extrude_* and _compute_extrude_* methods
    - BodyComputeMixin: _compute_revolve, _compute_loft
    - BodyComputeExtendedMixin: _compute_sweep, _compute_shell, etc.
    """

    _shared_tessellation_manager = None

    def __init__(self, name: str = "Body", document=None):
        self.name = name
        self.id = str(uuid.uuid4())[:8]
        self.features: List[Feature] = []
        self.rollback_index: Optional[int] = None  # None = all features active
        
        # Referenz zum Document (fÃ¼r TNP v4.0 Naming Service)
        self._document = document

        # === Multi-Body Split-Tracking (AGENTS.md Phase 2) ===
        # Wenn dieser Body via Split entstanden ist:
        self.source_body_id: Optional[str] = None  # ID des Original-Bodies vor Split
        self.split_index: Optional[int] = None      # Index des Split-Features in der Historie
        self.split_side: Optional[str] = None       # "above" oder "below"

        # CAD Kernel Objekte
        self._build123d_solid = None
        self.shape = None

        # === TNP v4.0: Shape Naming Service (im Document) ===
        # Nicht mehr hier - Service ist jetzt im Document zentralisiert
        
        # NOTE: Altes TNP-System (Phase 8.2/3) deaktiviert - v4.0 aktiv

        # === PHASE 7: Feature Dependency Graph ===
        self._dependency_graph = FeatureDependencyGraph()
        self._solid_checkpoints: dict = {}  # {feature_index: solid} - In-Memory Checkpoints
        
        # === TNP v3.0: Solid Generation Tracking ===
        # Wird inkrementiert wenn sich Solid durch Boolean Ã¤ndert
        # Features merken sich auf welcher Generation sie basieren
        self._solid_generation = 0
        self._last_boolean_feature_index = -1  # Index des letzten Boolean-Features

        # === PHASE 2: Single Source of Truth ===
        # PyVista/VTK Objekte - LAZY LOADED aus _build123d_solid
        self._mesh_cache = None       # pv.PolyData (Faces) - privat!
        self._edges_cache = None      # pv.PolyData (Edges) - privat!
        self._face_info_cache = {}    # {face_id: {"normal": (x,y,z), "center": (x,y,z)}} - B-Rep Info!
        self._mesh_cache_valid = False  # Invalidiert wenn Solid sich Ã¤ndert

        # Kosmetische Gewinde-Linien (Helix-Visualisierung ohne echte Geometrie)
        self._cosmetic_lines_cache = None   # pv.PolyData (Helix-Linien)
        self._cosmetic_lines_valid = False

        # Legacy Visualisierungs-Daten (Nur als Fallback)
        self._mesh_vertices: List[Tuple[float, float, float]] = []
        self._mesh_triangles: List[Tuple[int, int, int]] = []
        self._mesh_normals = []
        self._mesh_edges = []
        self._last_operation_error = ""
        self._last_operation_error_details = {}
        self._pending_tnp_failure = None
        self._async_tessellation_generation = 0

    @classmethod
    def _get_tessellation_manager(cls):
        """Lazy singleton manager for async tessellation requests."""
        if cls._shared_tessellation_manager is None:
            from gui.workers.tessellation_worker import TessellationManager
            cls._shared_tessellation_manager = TessellationManager()
        return cls._shared_tessellation_manager

    def _get_face_center(self, face):
        """Helper for TNP registration - delegates to geometry_utils."""
        return get_face_center(face)

    def _get_face_area(self, face):
        """Helper for TNP registration - delegates to geometry_utils."""
        return get_face_area(face)

    # NOTE: Static methods below delegate to shape_builders module for maintainability
    # These are kept as static methods for backward compatibility with existing code
    
    @staticmethod
    def _convert_legacy_nsided_edge_selectors(edge_selectors: Optional[List]) -> List[dict]:
        """Delegates to shape_builders module - see convert_legacy_nsided_edge_selectors."""
        return convert_legacy_nsided_edge_selectors(edge_selectors)

    @staticmethod
    def _convert_legacy_edge_selectors(edge_selectors: Optional[List]) -> List[dict]:
        """Delegates to shape_builders module - see convert_legacy_edge_selectors."""
        return convert_legacy_edge_selectors(edge_selectors)

    @staticmethod
    def from_solid(solid, name: str = "Imported Body", document=None) -> 'Body':
        """
        Create a Body from a Build123d Solid object.

        This is used by importers (STEP, CadQuery, etc.) to create
        Body objects from raw Build123d solids.

        Args:
            solid: Build123d Solid object
            name: Name for the new body
            document: Optional Document instance

        Returns:
            Body instance with the solid set
        """
        body = Body(name, document=document)
        body._build123d_solid = solid
        body.invalidate_mesh()
        return body

    # === PHASE 2: Lazy-Loaded Properties ===
    @property
    def vtk_mesh(self):
        """Lazy-loaded mesh from solid (Single Source of Truth)"""
        if not self._mesh_cache_valid or self._mesh_cache is None:
            self._regenerate_mesh()
        return self._mesh_cache

    @vtk_mesh.setter
    def vtk_mesh(self, value):
        """Setter fÃ¼r importierte Meshes (vor BREP-Konvertierung)"""
        self._mesh_cache = value
        self._mesh_cache_valid = True

    @property
    def vtk_edges(self):
        """Lazy-loaded edges from solid (Single Source of Truth)"""
        if not self._mesh_cache_valid or self._edges_cache is None:
            self._regenerate_mesh()
        return self._edges_cache

    @property
    def face_info(self):
        """B-Rep Face Info: {face_id: {"normal": (x,y,z), "center": (x,y,z)}}"""
        if not self._mesh_cache_valid:
            self._regenerate_mesh()
        return self._face_info_cache

    def get_brep_normal(self, face_id: int):
        """Gibt die B-Rep Normale fÃ¼r eine Face-ID zurÃ¼ck (oder None)."""
        info = self.face_info.get(face_id)
        if info:
            return info.get("normal")
        return None

    def _regenerate_mesh(self):
        """Single point of mesh generation - called automatically when needed"""
        if self._build123d_solid is None:
            self._mesh_cache = None
            self._edges_cache = None
            self._mesh_cache_valid = True
            return

        # Generate from solid via CADTessellator WITH FACE IDs!
        # Dies ermÃ¶glicht exakte Face-Selektion (statt Heuristik nach Normalen)
        self._mesh_cache, self._edges_cache, self._face_info_cache = CADTessellator.tessellate_with_face_ids(
            self._build123d_solid
        )
        self._mesh_cache_valid = True
        n_pts = self._mesh_cache.n_points if self._mesh_cache else 0
        n_edges = self._edges_cache.n_lines if self._edges_cache else 0
        n_faces = len(self._face_info_cache) if self._face_info_cache else 0
        logger.debug(f"Mesh regenerated for '{self.name}': {n_pts} pts, {n_edges} edges, {n_faces} B-Rep faces")

    @property
    def vtk_cosmetic_lines(self):
        """Lazy-loaded kosmetische Gewinde-Linien (Helix-Visualisierung)."""
        if not self._cosmetic_lines_valid:
            self._regenerate_cosmetic_lines()
        return self._cosmetic_lines_cache

    def _regenerate_cosmetic_lines(self):
        """Erzeugt Helix-Linien fÃ¼r alle kosmetischen ThreadFeatures."""
        self._cosmetic_lines_valid = True
        cosmetic_threads = [f for f in self.features
                            if isinstance(f, ThreadFeature) and f.cosmetic]
        if not cosmetic_threads:
            self._cosmetic_lines_cache = None
            return

        try:
            import numpy as np
            import pyvista as pv
            from build123d import Helix

            all_points = []
            all_lines = []
            offset = 0

            for feat in cosmetic_threads:
                r = feat.diameter / 2.0
                H = 0.8660254 * feat.pitch
                groove_depth = 0.625 * H

                # Zwei Helix-Linien: Innen- und AuÃŸenradius des Gewindes
                for radius in [r - groove_depth, r]:
                    helix = Helix(
                        pitch=feat.pitch,
                        height=feat.depth,
                        radius=radius,
                        center=tuple(feat.position),
                        direction=tuple(feat.direction)
                    )
                    # Sample Punkte entlang der Helix
                    n_samples = max(20, int(feat.depth / feat.pitch * 12))
                    pts = []
                    for j in range(n_samples + 1):
                        t = j / n_samples
                        pt = helix.position_at(t)
                        pts.append([pt.X, pt.Y, pt.Z])

                    pts_arr = np.array(pts)
                    n_pts = len(pts_arr)
                    all_points.append(pts_arr)

                    # Polyline: [n_pts, idx0, idx1, ..., idx_n-1]
                    line = [n_pts] + list(range(offset, offset + n_pts))
                    all_lines.extend(line)
                    offset += n_pts

            if all_points:
                points = np.vstack(all_points)
                self._cosmetic_lines_cache = pv.PolyData(points, lines=all_lines)
                logger.debug(f"[COSMETIC] {len(cosmetic_threads)} thread(s) â†’ "
                             f"{points.shape[0]} pts helix lines")
            else:
                self._cosmetic_lines_cache = None
        except Exception as e:
            logger.warning(f"Cosmetic thread lines failed: {e}")
            self._cosmetic_lines_cache = None

    def _get_solid_with_threads(self):
        """Berechnet echte Gewinde auf einer Kopie des Solids (fÃ¼r Export).

        Iteriert Ã¼ber alle kosmetischen ThreadFeatures und wendet
        _compute_thread() auf eine Kopie an. Original bleibt unverÃ¤ndert.
        """
        if self._build123d_solid is None:
            return None

        cosmetic_threads = [f for f in self.features
                            if isinstance(f, ThreadFeature) and f.cosmetic]
        if not cosmetic_threads:
            return self._build123d_solid

        logger.info(f"[EXPORT] Computing {len(cosmetic_threads)} real thread(s) for export...")
        current = self._build123d_solid
        for feat in cosmetic_threads:
            try:
                current = self._compute_thread(feat, current)
                logger.debug(f"[EXPORT] Thread {feat.name} applied")
            except Exception as e:
                logger.warning(f"[EXPORT] Thread {feat.name} failed: {e}")

        return current

    def invalidate_mesh(self):
        """Invalidiert Mesh-Cache - nÃ¤chster Zugriff regeneriert automatisch"""
        self._mesh_cache_valid = False
        self._cosmetic_lines_valid = False

        # WICHTIG: Auch Face-Info-Cache lÃ¶schen!
        # Sonst bleiben alte Face-IDs bestehen die nach Boolean ungÃ¼ltig sind
        self._face_info_cache = {}

        # Phase 4.3: Auch Topology-Cache invalidieren
        if self._build123d_solid is not None:
            try:
                CADTessellator.invalidate_topology_cache(id(self._build123d_solid.wrapped))
            except Exception as e:
                logger.debug(f"[__init__.py] Fehler: {e}")
                pass  # Solid hat kein wrapped (selten)

    def request_async_tessellation(self, on_ready=None, priority: int = 0):
        """
        Phase 9: Startet Tessellation im Hintergrund (Non-Blocking).

        Das Mesh wird asynchron generiert und via Callback zurÃ¼ckgegeben.
        vtk_mesh Property bleibt synchron (fÃ¼r KompatibilitÃ¤t).

        Args:
            on_ready: Optional callback(body_id, mesh, edges, face_info)
                      Wenn None, wird das Mesh direkt in den Cache geschrieben.
            priority: Scheduling-Priorität (höher = früherer Start)
        """
        if self._build123d_solid is None:
            return None

        self._async_tessellation_generation += 1
        generation = self._async_tessellation_generation

        def _on_mesh_ready(body_id, mesh, edges, face_info):
            """Callback: Mesh ist fertig, in Body-Cache schreiben."""
            if generation != self._async_tessellation_generation:
                logger.debug(
                    f"Ignore stale async mesh for '{self.name}' "
                    f"(generation {generation} != {self._async_tessellation_generation})"
                )
                return
            self._mesh_cache = mesh
            self._edges_cache = edges
            self._face_info_cache = face_info
            self._mesh_cache_valid = True
            n_pts = mesh.n_points if mesh else 0
            logger.debug(f"Async Mesh ready for '{self.name}': {n_pts} pts")
            if on_ready:
                on_ready(body_id, mesh, edges, face_info)

        def _on_mesh_error(body_id, error_message):
            if generation != self._async_tessellation_generation:
                return
            logger.warning(f"Async Tessellation error for '{self.name}': {error_message}")

        manager = self._get_tessellation_manager()
        worker = manager.request_tessellation(
            body_id=self.id,
            solid=self._build123d_solid,
            on_ready=_on_mesh_ready,
            on_error=_on_mesh_error,
            priority=int(priority),
        )

        # Worker-Referenz halten, damit er nicht garbage-collected wird
        self._tessellation_worker = worker
        return worker

    def add_feature(self, feature: Feature, rebuild: bool = True):
        """Feature hinzufÃ¼gen und optional Geometrie neu berechnen.

        Args:
            feature: Das Feature das hinzugefÃ¼gt werden soll
            rebuild: Wenn False, wird das Feature nur zur Liste hinzugefÃ¼gt
                     ohne _rebuild() aufzurufen. NÃ¼tzlich wenn das Solid
                     bereits durch eine direkte Operation (z.B. BRepFeat)
                     aktualisiert wurde.
        """
        self.features.append(feature)

        # Phase 7: Feature im Dependency Graph registrieren
        self._dependency_graph.add_feature(feature.id, len(self.features) - 1)

        if rebuild:
            self._rebuild(changed_feature_id=feature.id)

    def remove_feature(self, feature: Feature):
        if feature in self.features:
            feature_index = self.features.index(feature)

            # Phase 7: Checkpoints nach diesem Feature invalidieren
            self._dependency_graph.remove_feature(feature.id)
            # LÃ¶sche Checkpoints ab diesem Index
            for idx in list(self._solid_checkpoints.keys()):
                if idx >= feature_index:
                    del self._solid_checkpoints[idx]

            self.features.remove(feature)
            self._rebuild()

    def update_feature(self, feature: Feature):
        """
        Phase 7: Aktualisiert ein Feature und triggert inkrementellen Rebuild.

        Nutzt den Dependency Graph um nur die betroffenen Features neu zu berechnen.

        Args:
            feature: Das geÃ¤nderte Feature (muss bereits in self.features sein)
        """
        if feature not in self.features:
            logger.error(f"Feature '{feature.id}' nicht in Body '{self.name}' gefunden")
            return

        feature_index = self.features.index(feature)

        # Checkpoints ab diesem Feature invalidieren
        for idx in list(self._solid_checkpoints.keys()):
            if idx >= feature_index:
                del self._solid_checkpoints[idx]

        # Inkrementeller Rebuild
        self._rebuild(changed_feature_id=feature.id)
            
    def convert_to_brep(self, mode: str = "auto"):
        """
        Wandelt Mesh in CAD-Solid um.

        Verwendet DirectMeshConverter + BRepOptimizer fÃ¼r zuverlÃ¤ssige Konvertierung.
        Faces werden zu BREP konvertiert und dann mit UnifySameDomain optimiert.
        """
        if self._build123d_solid is not None:
            logger.info(f"Body '{self.name}' ist bereits BREP.")
            return True

        if self.vtk_mesh is None:
            logger.warning("Keine Mesh-Daten vorhanden.")
            return False

        logger.info(f"Starte Mesh-zu-BREP Konvertierung fÃ¼r '{self.name}'...")
        logger.info(f"  Mesh: {self.vtk_mesh.n_points} Punkte, {self.vtk_mesh.n_cells} Faces")

        try:
            # 1. DirectMeshConverter: Mesh -> BREP (1:1 Faces)
            from meshconverter.direct_mesh_converter import DirectMeshConverter
            from meshconverter.brep_optimizer import optimize_brep

            converter = DirectMeshConverter(unify_faces=False)
            result = converter.convert(self.vtk_mesh)

            if result.solid is None:
                logger.error(f"DirectMeshConverter fehlgeschlagen: {result.message}")
                return False

            logger.info(f"  BREP erstellt: {result.stats.get('faces_created', '?')} Faces")

            # 2. BRepOptimizer: Face-Reduktion + Primitiv-Erkennung
            optimized, opt_stats = optimize_brep(result.solid)

            faces_before = opt_stats.get('faces_before', 0)
            faces_after = opt_stats.get('faces_after', 0)
            reduction = faces_before - faces_after

            logger.info(f"  Optimiert: {faces_before} -> {faces_after} Faces ({reduction} reduziert)")
            if opt_stats.get('cylinders_detected', 0) > 0:
                logger.info(f"  Zylinder erkannt: {opt_stats['cylinders_detected']}")
            if opt_stats.get('spheres_detected', 0) > 0:
                logger.info(f"  Kugeln erkannt: {opt_stats['spheres_detected']}")

            # 3. In Build123d Solid wrappen
            from build123d import Solid
            solid = Solid(optimized)

            if solid and hasattr(solid, 'wrapped') and not solid.wrapped.IsNull():
                self._build123d_solid = solid
                self.shape = solid.wrapped

                # TNP v4.0: ShapeID-Registrierung fÃ¼r konvertierte Geometrie
                try:
                    if self._document and hasattr(self._document, '_shape_naming_service'):
                        service = self._document._shape_naming_service
                        if service is not None:
                            feature_id = f"mesh_convert_{self.id}"

                            # Alle Edges registrieren
                            edge_count = service.register_solid_edges(solid, feature_id)

                            # Alle Faces registrieren
                            try:
                                from OCP.TopTools import TopTools_IndexedMapOfShape
                                from OCP.TopExp import TopExp
                                from OCP.TopoDS import TopoDS
                                from modeling.tnp_system import ShapeType

                                face_map = TopTools_IndexedMapOfShape()
                                TopExp.MapShapes_s(solid.wrapped, TopAbs_FACE, face_map)

                                for fi in range(1, face_map.Extent() + 1):
                                    face_shape = TopoDS.Face_s(face_map.FindKey(fi))
                                    service.register_shape(
                                        ocp_shape=face_shape,
                                        shape_type=ShapeType.FACE,
                                        feature_id=feature_id,
                                        local_index=fi - 1
                                    )

                                logger.info(f"  [TNP] {edge_count} Edges, {face_map.Extent()} Faces registriert")
                            except Exception as e:
                                logger.debug(f"[TNP] Face-Registrierung fehlgeschlagen: {e}")
                except Exception as e:
                    logger.debug(f"[TNP] Registrierung fehlgeschlagen: {e}")

                # === NEU: ImportFeature erstellen fÃ¼r Rebuild-Support ===
                # BREP serialisieren (via BytesIO Stream)
                try:
                    from OCP.BRepTools import BRepTools
                    import io

                    # BRepTools.Write_s braucht einen BytesIO Stream
                    stream = io.BytesIO()
                    BRepTools.Write_s(solid.wrapped, stream)
                    brep_string = stream.getvalue().decode('utf-8')

                    if brep_string:
                        # ImportFeature erstellen
                        import_feature = ImportFeature(
                            name=f"Import ({self.name})",
                            brep_string=brep_string,
                            source_file=getattr(self, 'source_file', self.name),
                            source_type="mesh_convert"
                        )

                        # Alte Features lÃ¶schen und ImportFeature als Basis setzen
                        self.features.clear()
                        self.features.append(import_feature)

                        logger.info(f"  ImportFeature erstellt ({len(brep_string)} bytes BREP)")
                except Exception as e:
                    logger.warning(f"ImportFeature Erstellung fehlgeschlagen: {e}")
                    # Konvertierung war trotzdem erfolgreich, nur ohne Rebuild-Support

                logger.success(f"Body '{self.name}' erfolgreich konvertiert!")

                # Mesh neu berechnen (vom BREP abgeleitet fÃ¼r Konsistenz)
                self._update_mesh_from_solid(solid)
                return True
            else:
                logger.warning("Konvertierung lieferte kein gÃ¼ltiges Solid.")
                return False

        except Exception as e:
            logger.error(f"Konvertierung fehlgeschlagen: {e}")
            traceback.print_exc()
            return False
            
    # NOTE: These static methods delegate to geometry_utils module for maintainability
    # They are kept here for backward compatibility with existing code
    
    @staticmethod
    def _format_index_refs_for_error(label: str, refs, max_items: int = 3) -> str:
        """Delegates to geometry_utils module."""
        return format_index_refs_for_error(label, refs, max_items)

    @staticmethod
    def _format_shape_refs_for_error(label: str, refs, max_items: int = 3) -> str:
        """Delegates to geometry_utils module."""
        return format_shape_refs_for_error(label, refs, max_items)

    def _collect_feature_reference_diagnostics(self, feature, max_parts: int = 6) -> str:
        """Delegates to geometry_utils module."""
        return collect_feature_reference_diagnostics(feature, max_parts)

    @staticmethod
    def _collect_feature_reference_payload(feature) -> dict:
        """Delegates to geometry_utils module."""
        return collect_feature_reference_payload(feature)

    def _record_tnp_failure(
        self,
        *,
        feature,
        category: str,
        reference_kind: str,
        reason: str,
        expected: Optional[int] = None,
        resolved: Optional[int] = None,
        strict: bool = False,
    ) -> None:
        """Merkt die letzte TNP-Fehlerkategorie, damit _safe_operation sie envelope-n kann."""
        if feature is None:
            self._pending_tnp_failure = None
            return

        category_norm = str(category or "").strip().lower() or "missing_ref"
        if category_norm not in {"missing_ref", "mismatch", "drift"}:
            category_norm = "missing_ref"

        kind_norm = str(reference_kind or "").strip().lower() or "reference"
        next_action_map = {
            "missing_ref": f"{kind_norm.capitalize()}-Referenz neu waehlen und Feature erneut ausfuehren.",
            "mismatch": f"{kind_norm.capitalize()}-ShapeID und Index stimmen nicht ueberein. Referenz neu waehlen.",
            "drift": "Referenzierte Geometrie ist gedriftet. Feature mit kleineren Werten erneut anwenden.",
        }

        payload = {
            "category": category_norm,
            "reference_kind": kind_norm,
            "reason": str(reason or "").strip() or "unspecified",
            "strict": bool(strict),
            "next_action": next_action_map.get(
                category_norm,
                "Referenzen pruefen und Feature erneut ausfuehren.",
            ),
            "feature_id": getattr(feature, "id", ""),
            "feature_name": getattr(feature, "name", ""),
            "feature_class": feature.__class__.__name__,
        }
        if expected is not None:
            try:
                payload["expected"] = max(0, int(expected))
            except Exception:
                pass
        if resolved is not None:
            try:
                payload["resolved"] = max(0, int(resolved))
            except Exception:
                pass
        self._pending_tnp_failure = payload

    def _consume_tnp_failure(self, feature=None) -> Optional[dict]:
        """Liefert und leert die letzte TNP-Fehlerkategorie (feature-gebunden)."""
        pending = self._pending_tnp_failure
        self._pending_tnp_failure = None
        if not pending:
            return None
        if feature is None:
            return dict(pending)

        pending_feature_id = str(pending.get("feature_id") or "")
        feature_id = str(getattr(feature, "id", "") or "")
        if pending_feature_id and feature_id and pending_feature_id != feature_id:
            return None
        return dict(pending)

    @staticmethod
    def _classify_error_code(error_code: str) -> tuple[str, str]:
        """Mappt Error-Code auf stabile Envelope-Klassen fuer UI/QA."""
        code_norm = str(error_code or "").strip().lower()
        warning_codes = {
            "fallback_used",
            "tnp_ref_drift",
        }
        blocked_codes = {
            "blocked_by_upstream_error",
            "fallback_blocked_strict",
        }
        critical_codes = {
            "rebuild_finalize_failed",
        }
        if code_norm in critical_codes:
            return "CRITICAL", "critical"
        if code_norm in warning_codes:
            return "WARNING_RECOVERABLE", "warning"
        if code_norm in blocked_codes:
            return "BLOCKED", "blocked"
        return "ERROR", "error"

    @staticmethod
    def _default_next_action_for_code(error_code: str) -> str:
        defaults = {
            "operation_failed": "Parameter pruefen oder Referenz neu auswaehlen und erneut ausfuehren.",
            "fallback_used": "Ergebnis wurde via Fallback erzeugt. Geometrie pruefen und Parameter/Referenz ggf. nachziehen.",
            "fallback_failed": "Feature vereinfachen und mit kleineren Werten erneut versuchen.",
            "fallback_blocked_strict": "Feature neu referenzieren oder self_heal_strict deaktivieren.",
            "blocked_by_upstream_error": "Zuerst das vorherige fehlgeschlagene Feature beheben.",
            "no_result_solid": "Eingaben/Referenzen pruefen, da kein Ergebnis-Solid erzeugt wurde.",
            "self_heal_rollback_invalid_result": "Featureparameter reduzieren oder Referenzflaeche anpassen.",
            "self_heal_rollback_geometry_drift": "Lokalen Modifier mit kleineren Werten erneut anwenden.",
            "self_heal_blocked_topology_warning": "Topologie-Referenzen pruefen und Feature neu auswaehlen.",
            "tnp_ref_missing": "Topologie-Referenz neu waehlen und Rebuild erneut ausfuehren.",
            "tnp_ref_mismatch": "ShapeID/Index-Referenz stimmt nicht ueberein. Referenz neu waehlen.",
            "tnp_ref_drift": "Referenzierte Geometrie ist gedriftet. Feature mit kleineren Werten erneut anwenden.",
            "rebuild_finalize_failed": "Rebuild erneut ausfuehren oder letzte stabile Aenderung rueckgaengig machen.",
            "ocp_api_unavailable": "OCP-Build pruefen oder alternative Operation verwenden.",
        }
        return defaults.get(
            error_code,
            "Fehlerdetails pruefen und den letzten gueltigen Bearbeitungsschritt wiederholen.",
        )

    @classmethod
    def _normalize_status_details_for_load(cls, status_details: Any) -> dict:
        """
        Backward-Compat fuer persistierte status_details.

        Legacy-Dateien koennen `code` ohne `status_class`/`severity` enthalten.
        Beim Laden werden diese Felder deterministisch nachgezogen.
        """
        if not isinstance(status_details, dict):
            return {}

        normalized = dict(status_details)
        code = str(normalized.get("code", "") or "").strip()
        if code:
            normalized.setdefault("schema", "error_envelope_v1")
        has_status_class = bool(str(normalized.get("status_class", "") or "").strip())
        has_severity = bool(str(normalized.get("severity", "") or "").strip())
        if code and (not has_status_class or not has_severity):
            status_class, severity = cls._classify_error_code(code)
            normalized.setdefault("status_class", status_class)
            normalized.setdefault("severity", severity)

        hint = str(normalized.get("hint", "") or "").strip()
        next_action = str(normalized.get("next_action", "") or "").strip()
        if hint and not next_action:
            normalized["next_action"] = hint
            next_action = hint
        if next_action and not hint:
            normalized["hint"] = next_action
            hint = next_action
        if code and not hint and not next_action:
            action = cls._default_next_action_for_code(code)
            if action:
                normalized["hint"] = action
                normalized["next_action"] = action
        return normalized

    def _build_operation_error_details(
        self,
        *,
        op_name: str,
        code: str,
        message: str,
        feature=None,
        hint: str = "",
        fallback_error: str = "",
    ) -> dict:
        status_class, severity = self._classify_error_code(code)
        details = {
            "schema": "error_envelope_v1",
            "code": code,
            "operation": op_name,
            "message": message,
            "status_class": status_class,
            "severity": severity,
        }
        if feature is not None:
            details["feature"] = {
                "id": getattr(feature, "id", ""),
                "name": getattr(feature, "name", ""),
                "class": feature.__class__.__name__,
            }
        refs = self._collect_feature_reference_payload(feature)
        if refs:
            details["refs"] = refs
        next_action = hint or self._default_next_action_for_code(code)
        if next_action:
            details["hint"] = next_action
            details["next_action"] = next_action
        if fallback_error:
            details["fallback_error"] = fallback_error
        return details

    def _safe_operation(self, op_name, op_func, fallback_func=None, feature=None):
        """
        Wrapper fÃ¼r kritische CAD-Operationen.
        FÃ¤ngt Crashes ab und erlaubt Fallbacks.
        """
        try:
            self._last_operation_error = ""
            self._last_operation_error_details = {}
            self._pending_tnp_failure = None
            result = op_func()
            
            if result is None:
                raise ValueError("Operation returned None")
            
            if hasattr(result, 'is_valid') and not result.is_valid():
                raise ValueError("Result geometry is invalid")

            tnp_notice = self._consume_tnp_failure(feature)
            notice_category = (
                str((tnp_notice or {}).get("category") or "").strip().lower()
                if isinstance(tnp_notice, dict)
                else ""
            )
            if notice_category == "drift":
                notice_reason = str(tnp_notice.get("reason") or "").strip()
                notice_msg = "TNP-Referenzdrift erkannt; Geometric-Fallback wurde verwendet."
                if notice_reason:
                    notice_msg = f"{notice_msg} reason={notice_reason}"
                self._last_operation_error = notice_msg
                drift_hint = str(tnp_notice.get("next_action") or "").strip()
                self._last_operation_error_details = self._build_operation_error_details(
                    op_name=op_name,
                    code="tnp_ref_drift",
                    message=notice_msg,
                    feature=feature,
                    hint=drift_hint,
                )
                self._last_operation_error_details["tnp_failure"] = tnp_notice
                return result, "WARNING"

            return result, "SUCCESS"
            
        except Exception as e:
            err_msg = str(e).strip() or e.__class__.__name__
            ref_diag = self._collect_feature_reference_diagnostics(feature)
            if ref_diag and "refs:" not in err_msg:
                err_msg = f"{err_msg} | refs: {ref_diag}"
            self._last_operation_error = err_msg
            tnp_failure = self._consume_tnp_failure(feature)
            tnp_code_by_category = {
                "missing_ref": "tnp_ref_missing",
                "mismatch": "tnp_ref_mismatch",
                "drift": "tnp_ref_drift",
            }
            tnp_category = (
                str((tnp_failure or {}).get("category") or "").strip().lower()
                if isinstance(tnp_failure, dict)
                else ""
            )
            error_code = tnp_code_by_category.get(tnp_category, "operation_failed")
            dependency_error = None
            if error_code == "operation_failed":
                dep_msg = str(e).strip() or e.__class__.__name__
                dep_msg_lower = dep_msg.lower()
                is_direct_dep_error = isinstance(e, (ImportError, ModuleNotFoundError, AttributeError))
                ocp_markers = (
                    "ocp",
                    "no module named 'ocp",
                    "cannot import name",
                    "has no attribute",
                )
                is_ocp_dependency_error = is_direct_dep_error and any(marker in dep_msg_lower for marker in ocp_markers)
                if (not is_ocp_dependency_error) and any(marker in dep_msg_lower for marker in ("cannot import name", "no module named", "has no attribute")):
                    # Wrapped dependency error (e.g. RuntimeError with import text)
                    is_ocp_dependency_error = "ocp" in dep_msg_lower
                if is_ocp_dependency_error:
                    error_code = "ocp_api_unavailable"
                    dependency_error = {
                        "kind": "ocp_api",
                        "exception": e.__class__.__name__,
                        "detail": dep_msg,
                    }
            tnp_hint = ""
            if isinstance(tnp_failure, dict):
                tnp_hint = str(tnp_failure.get("next_action") or "").strip()
            self._last_operation_error_details = self._build_operation_error_details(
                op_name=op_name,
                code=error_code,
                message=err_msg,
                feature=feature,
                hint=tnp_hint,
            )
            if isinstance(tnp_failure, dict):
                self._last_operation_error_details["tnp_failure"] = tnp_failure
            if dependency_error:
                self._last_operation_error_details["runtime_dependency"] = dependency_error
            logger.warning(f"Feature '{op_name}' fehlgeschlagen: {err_msg}")
            
            if fallback_func:
                strict_self_heal = is_enabled("self_heal_strict")
                strict_topology_policy = is_enabled("strict_topology_fallback_policy")
                has_topology_refs = self._feature_has_topological_references(feature) if feature is not None else False
                if has_topology_refs and (strict_self_heal or strict_topology_policy):
                    policy_reason = (
                        "Strict Self-Heal"
                        if strict_self_heal
                        else "strict_topology_fallback_policy"
                    )
                    self._last_operation_error = (
                        f"PrimÃ¤rpfad fehlgeschlagen: {err_msg}; "
                        f"{policy_reason} blockiert Fallback bei Topologie-Referenzen"
                    )
                    self._last_operation_error_details = self._build_operation_error_details(
                        op_name=op_name,
                        code="fallback_blocked_strict",
                        message=self._last_operation_error,
                        feature=feature,
                        hint="Feature neu referenzieren oder Parameter reduzieren.",
                    )
                    if isinstance(tnp_failure, dict):
                        self._last_operation_error_details["tnp_failure"] = tnp_failure
                    logger.error(
                        f"{policy_reason}: Fallback fÃ¼r '{op_name}' blockiert "
                        "(Topologie-Referenzen aktiv)."
                    )
                    return None, "ERROR"
                logger.debug(f"â†’ Versuche Fallback fÃ¼r '{op_name}'...")
                try:
                    res_fallback = fallback_func()
                    if res_fallback:
                        self._last_operation_error = f"PrimÃ¤rpfad fehlgeschlagen: {err_msg}; Fallback wurde verwendet"
                        self._last_operation_error_details = self._build_operation_error_details(
                            op_name=op_name,
                            code="fallback_used",
                            message=self._last_operation_error,
                            feature=feature,
                        )
                        logger.debug(f"âœ“ Fallback fÃ¼r '{op_name}' erfolgreich.")
                        return res_fallback, "WARNING"
                except Exception as e2:
                    fallback_msg = str(e2).strip() or e2.__class__.__name__
                    self._last_operation_error = (
                        f"PrimÃ¤rpfad fehlgeschlagen: {err_msg}; Fallback fehlgeschlagen: {fallback_msg}"
                    )
                    self._last_operation_error_details = self._build_operation_error_details(
                        op_name=op_name,
                        code="fallback_failed",
                        message=self._last_operation_error,
                        feature=feature,
                        fallback_error=fallback_msg,
                    )
                    logger.error(f"âœ— Auch Fallback fehlgeschlagen: {fallback_msg}")
            
            return None, "ERROR"

    def _register_boolean_history(self, bool_result: BooleanResult, feature, operation_name: str = ""):
        """
        Registriert Boolean-History fÃ¼r TNP v4.0.

        Wird nach erfolgreichen Boolean-Operationen aufgerufen um
        die BRepTools_History an die TNP-Systeme weiterzugeben.

        Args:
            bool_result: BooleanResult mit history-Attribut
            feature: Das Feature das die Boolean-Operation ausgelÃ¶st hat
            operation_name: Name der Operation (Join/Cut/Intersect)
        """
        boolean_history = getattr(bool_result, 'history', None)
        if boolean_history is None:
            return

        # TNP v4.0: ShapeNamingService
        if self._document and hasattr(self._document, '_shape_naming_service'):
            try:
                service = self._document._shape_naming_service
                service.record_operation(
                    OperationRecord(
                        operation_id=str(uuid.uuid4())[:8],
                        operation_type=f"BOOLEAN_{operation_name.upper()}",
                        feature_id=getattr(feature, 'id', 'unknown'),
                        occt_history=boolean_history,
                    )
                )
                if is_enabled("tnp_debug_logging"):
                    logger.debug(f"TNP v4.0: Boolean {operation_name} History registriert")
            except Exception as tnp_e:
                if is_enabled("tnp_debug_logging"):
                    logger.debug(f"TNP v4.0 History-Registrierung fehlgeschlagen: {tnp_e}")

    def _register_fillet_chamfer_history(self, result_solid, history, feature, operation_type: str = "FILLET"):
        """
        Registriert Fillet/Chamfer History fÃ¼r TNP v4.0.

        Phase 12: Nutzt BRepFilletAPI_MakeFillet.History() fÃ¼r prÃ¤zises Shape-Tracking
        nach Fillet/Chamfer-Operationen.

        Args:
            result_solid: Das resultierende Build123d Solid
            history: BRepTools_History von der Fillet/Chamfer-Operation
            feature: Das FilletFeature/ChamferFeature
            operation_type: "FILLET" oder "CHAMFER"
        """
        if history is None:
            return

        # TNP v4.0: ShapeNamingService
        if self._document and hasattr(self._document, '_shape_naming_service'):
            try:
                service = self._document._shape_naming_service
                service.record_operation(
                    OperationRecord(
                        operation_id=str(uuid.uuid4())[:8],
                        operation_type=operation_type,
                        feature_id=getattr(feature, 'id', 'unknown'),
                        occt_history=history,
                    )
                )
                if is_enabled("tnp_debug_logging"):
                    logger.debug(f"TNP v4.0: {operation_type} History registriert")
            except Exception as tnp_e:
                if is_enabled("tnp_debug_logging"):
                    logger.debug(f"TNP v4.0 {operation_type} History-Registrierung fehlgeschlagen: {tnp_e}")

    @staticmethod
    def _build_history_from_make_shape(make_shape_op, input_shape):
        """
        Baut ein BRepTools_History aus einer BRepBuilderAPI_MakeShape-Operation.

        Phase 12: BRepFilletAPI_MakeFillet/MakeChamfer erben von BRepBuilderAPI_MakeShape
        und haben Generated()/Modified()/IsDeleted() aber kein direktes History().
        Diese Methode konstruiert die History manuell.

        Args:
            make_shape_op: BRepBuilderAPI_MakeShape (z.B. BRepFilletAPI_MakeFillet)
            input_shape: Das Original-Shape vor der Operation

        Returns:
            BRepTools_History mit allen Zuordnungen
        """
        from OCP.BRepTools import BRepTools_History
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_VERTEX

        history = BRepTools_History()

        for shape_type in (TopAbs_FACE, TopAbs_EDGE, TopAbs_VERTEX):
            explorer = TopExp_Explorer(input_shape, shape_type)
            count = 0
            while explorer.More():
                count += 1
                sub_shape = explorer.Current()
                
                # Helper to check history for a shape and its reverse
                def _check_and_add(s):
                    # Generated
                    try:
                        gen = list(make_shape_op.Generated(s))
                        if gen:
                            if is_enabled("tnp_debug_logging"):
                                 logger.debug(f"TNP History: Generated for {s} (Ori={s.Orientation()}): {len(gen)} items")
                            for res in gen:
                                history.AddGenerated(sub_shape, res) # Always map FROM the original sub_shape
                    except Exception:
                        pass
                    
                    # Modified
                    try:
                        mod = list(make_shape_op.Modified(s))
                        if mod:
                            if is_enabled("tnp_debug_logging"):
                                 logger.debug(f"TNP History: Modified for {s} (Ori={s.Orientation()}): {len(mod)} items")
                            for res in mod:
                                history.AddModified(sub_shape, res)
                    except Exception:
                        pass
                        
                    # Deleted
                    try:
                        if make_shape_op.IsDeleted(s):
                            if is_enabled("tnp_debug_logging"):
                                 logger.debug(f"TNP History: Deleted {s} (Ori={s.Orientation()})")
                            history.Remove(sub_shape)
                    except Exception:
                        pass

                _check_and_add(sub_shape)
                if sub_shape.Orientation() != 0: # Check reverse only if orientation is not "EXTERNAL" (0)? TopAbs orientation is enum.
                     # TopAbs_FORWARD=0, TopAbs_REVERSED=1. 
                     # Safe to just check Reversed() always.
                     _check_and_add(sub_shape.Reversed())
                
                explorer.Next()
            
            if is_enabled("tnp_debug_logging"):
                 logger.debug(f"TNP History: Scanned {count} items of type {shape_type}")

        return history

        return history

    def _fix_shape_ocp(self, shape):
        """Repariert einen TopoDS_Shape mit OCP ShapeFix."""
        try:
            from OCP.ShapeFix import ShapeFix_Shape, ShapeFix_Solid
            from OCP.BRepCheck import BRepCheck_Analyzer

            # PrÃ¼fe ob Shape valide ist
            analyzer = BRepCheck_Analyzer(shape)
            if analyzer.IsValid():
                return shape

            logger.debug("Shape invalid, starte Reparatur...")

            # ShapeFix_Shape fÃ¼r allgemeine Reparaturen - Phase 5: Zentralisierte Toleranzen
            fixer = ShapeFix_Shape(shape)
            fixer.SetPrecision(Tolerances.KERNEL_PRECISION)
            fixer.SetMaxTolerance(Tolerances.MESH_EXPORT)
            fixer.SetMinTolerance(Tolerances.KERNEL_PRECISION / 10)

            # HINWEIS: FixSolidMode() etc. sind GETTER, nicht Setter!
            # Die Standardwerte sind bereits True fÃ¼r die meisten Modi.
            # Wir verlassen uns auf die Defaults.

            if fixer.Perform():
                fixed_shape = fixer.Shape()

                # Validiere repariertes Shape
                analyzer2 = BRepCheck_Analyzer(fixed_shape)
                if analyzer2.IsValid():
                    logger.debug("âœ“ Shape repariert")
                    return fixed_shape
                else:
                    logger.warning("Shape nach Reparatur immer noch invalid")
                    # Gib es trotzdem zurÃ¼ck - manchmal funktioniert es dennoch
                    return fixed_shape
            else:
                logger.warning("ShapeFix Perform() fehlgeschlagen")
                return shape  # Gib Original zurÃ¼ck

        except Exception as e:
            logger.warning(f"Shape-Reparatur Fehler: {e}")
            return shape  # Gib Original zurÃ¼ck

    # ==================== PHASE 6: COMPUTE METHODS ====================
    # NOTE: _ocp_fillet und _ocp_chamfer wurden in OCP-AMP2 entfernt
    # (Doppelte Implementierungen, werden durch OCPFilletHelper/OCPChamferHelper ersetzt)

    # ==================== PHASE 6: COMPUTE METHODS ====================

    def update_feature_references(self, feature_id: str, old_solid, new_solid):
        """
        KompatibilitÃ¤ts-Hook bei Feature-Ã„nderungen.

        Args:
            feature_id: ID des modifizierten Features
            old_solid: Solid VOR der Ã„nderung
            new_solid: Solid NACH der Ã„nderung
        """
        if is_enabled("tnp_debug_logging"):
            logger.debug(f"TNP v4.0: Feature {feature_id} wurde modifiziert")

    def reorder_features(self, old_index: int, new_index: int) -> bool:
        """
        Verschiebt ein Feature in der Liste und fÃ¼hrt Migration durch.

        Args:
            old_index: Aktuelle Position
            new_index: Neue Position

        Returns:
            True bei Erfolg
        """
        if old_index < 0 or old_index >= len(self.features):
            return False
        if new_index < 0 or new_index >= len(self.features):
            return False
        if old_index == new_index:
            return True

        # Speichere alte Referenzen
        old_solid = self._build123d_solid

        # Feature verschieben
        feature = self.features.pop(old_index)
        self.features.insert(new_index, feature)

        logger.info(f"Feature '{feature.name}' verschoben: {old_index} â†’ {new_index}")

        # Rebuild ausfÃ¼hren (inkl. automatischer Migration)
        try:
            self._rebuild()
            return True
        except Exception as e:
            logger.error(f"Rebuild nach Feature-Verschiebung fehlgeschlagen: {e}")
            # RÃ¼ckgÃ¤ngig machen
            feature = self.features.pop(new_index)
            self.features.insert(old_index, feature)
            self._rebuild()
            return False

    def _convert_line_profiles_to_polygons(self, line_profiles: list) -> list:
        """Delegates to shape_builders module - see convert_line_profiles_to_polygons."""
        return convert_line_profiles_to_polygons(line_profiles)

    def _filter_profiles_by_selector(self, profiles: list, selector: list, tolerance: float = 5.0) -> list:
        """Delegates to shape_builders module - see filter_profiles_by_selector."""
        return filter_profiles_by_selector(profiles, selector, tolerance)

    def _lookup_geometry_for_polygon(self, poly, sketch):
        """Delegates to shape_builders module - see lookup_geometry_for_polygon."""
        return lookup_geometry_for_polygon(poly, sketch)

    def _get_plane_from_sketch(self, sketch):
        """Delegates to shape_builders module - see get_plane_from_sketch."""
        return get_plane_from_sketch(sketch)

    def _update_mesh_from_solid(self, solid):
        """
        Phase 2: Invalidiert Mesh-Cache - Mesh wird lazy regeneriert bei Zugriff.
        (Single Source of Truth Pattern)
        """
        if not solid:
            return

        # Invalidiere Cache - nÃ¤chster Zugriff auf vtk_mesh/vtk_edges regeneriert
        self.invalidate_mesh()

        # Legacy Support leeren
        self._mesh_vertices = []
        self._mesh_triangles = []

    def export_stl(self, filename: str) -> bool:
        """STL Export via Kernel (Build123d). Kein Mesh-Fallback."""
        if not HAS_BUILD123D or self._build123d_solid is None:
            logger.error("STL-Export fehlgeschlagen: Kein Build123d-Solid vorhanden")
            return False

        # OCP Feature Audit: Offene-Kanten-Check vor Export
        self._check_free_bounds_before_export()

        try:
            export_stl(self._build123d_solid, filename)
            return True
        except Exception as e:
            logger.error(f"STL-Export fehlgeschlagen: {e}")
            return False

    def _check_free_bounds_before_export(self):
        """
        OCP Feature Audit: PrÃ¼ft ob Body offene Kanten hat vor Export.

        Offene Shells erzeugen STL-Dateien mit LÃ¶chern, die fÃ¼r 3D-Druck
        unbrauchbar sind. Diese Warnung hilft dem User das Problem zu erkennen.
        """
        from config.feature_flags import is_enabled
        if not is_enabled("export_free_bounds_check"):
            return

        try:
            from OCP.ShapeAnalysis import ShapeAnalysis_FreeBounds
            from OCP.TopExp import TopExp_Explorer
            from OCP.TopAbs import TopAbs_WIRE

            fb = ShapeAnalysis_FreeBounds(self._build123d_solid.wrapped)
            closed_compound = fb.GetClosedWires()
            open_compound = fb.GetOpenWires()

            # GetClosedWires/GetOpenWires geben TopoDS_Compound zurÃ¼ck
            def count_wires(compound):
                exp = TopExp_Explorer(compound, TopAbs_WIRE)
                n = 0
                while exp.More():
                    n += 1
                    exp.Next()
                return n

            n_closed = count_wires(closed_compound)
            n_open = count_wires(open_compound)

            if n_open > 0:
                logger.warning(
                    f"âš ï¸ Body '{self.name}' hat {n_open} offene Kante(n)! "
                    f"STL kÃ¶nnte LÃ¶cher haben â†’ 3D-Druck problematisch."
                )
            elif n_closed > 0:
                logger.warning(
                    f"âš ï¸ Body '{self.name}' hat {n_closed} geschlossene freie Wire(s). "
                    f"MÃ¶gliches internes Shell-Problem."
                )
            else:
                logger.debug(f"Export Free-Bounds Check: Body '{self.name}' ist geschlossen (OK)")

        except Exception as e:
            logger.debug(f"Free-Bounds Check fehlgeschlagen: {e}")

    def _export_stl_simple(self, filename: str) -> bool:
        """Primitiver STL Export aus Mesh-Daten (Letzter Ausweg)"""
        try:
            with open(filename, 'w') as f:
                f.write(f"solid {self.name}\n")
                for tri in self._mesh_triangles:
                    v0 = self._mesh_vertices[tri[0]]
                    v1 = self._mesh_vertices[tri[1]]
                    v2 = self._mesh_vertices[tri[2]]
                    f.write(f"  facet normal 0 0 1\n")
                    f.write(f"    outer loop\n")
                    f.write(f"      vertex {v0[0]} {v0[1]} {v0[2]}\n")
                    f.write(f"      vertex {v1[0]} {v1[1]} {v1[2]}\n")
                    f.write(f"      vertex {v2[0]} {v2[1]} {v2[2]}\n")
                    f.write(f"    endloop\n")
                    f.write(f"  endfacet\n")
                f.write(f"endsolid {self.name}\n")
            return True
        except Exception as e:
            logger.error(f"Legacy STL-Export fehlgeschlagen: {e}")
            return False

    # === PHASE 8.2: Persistente Speicherung fÃ¼r TNP ===
    # (Serialization methods delegated to body_serialization module)

    def to_dict(self) -> dict:
        """
        Serialisiert Body zu Dictionary fÃ¼r persistente Speicherung.
        
        Delegates to body_serialization.body_to_dict module.
        """
        return body_to_dict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'Body':
        """
        Deserialisiert Body aus Dictionary.
        
        Delegates to body_serialization.body_from_dict module.
        """
        return body_from_dict(cls, data, cls)

    @classmethod
    def _normalize_status_details_for_load(cls, status_details: Any) -> dict:
        """Delegate to body_serialization module."""
        return _normalize_status_details_for_load(status_details)


__all__ = ['Body', 'HAS_OCP', 'HAS_BUILD123D']
