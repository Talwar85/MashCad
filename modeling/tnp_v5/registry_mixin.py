"""
TNP v5.0 - Registry Mixin

Extracted from monolithic ShapeNamingService (tnp_system.py).
Provides shape registration, seeding, and registry management.
"""

from typing import Dict, List, Optional, Tuple, Any
from loguru import logger
from config.feature_flags import is_enabled
import numpy as np

try:
    from OCP.TopoDS import TopoDS_Shape, TopoDS_Edge, TopoDS_Face
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_VERTEX
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    HAS_OCP = True
except ImportError:
    HAS_OCP = False

from .types import ShapeID, ShapeRecord, ShapeType, SelectionContext
from .spatial import SpatialIndex, Bounds, compute_bounds_from_signature
from .semantic_matcher import SemanticMatcher


class RegistryMixin:
    """Mixin for shape registration, seeding, and registry management.

    Expects the following instance attributes (set by TNPService.__init__):
        _shapes: Dict[str, ShapeRecord]
        _by_feature: Dict[str, List[ShapeID]]
        _spatial_index: Dict[ShapeType, List[Tuple[np.ndarray, ShapeID]]]
        _semantic_spatial_index: SpatialIndex
        _semantic_matcher: SemanticMatcher
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register_shape(
        self,
        ocp_shape: Any,
        shape_type: ShapeType,
        feature_id: str,
        local_index: int,
        geometry_data: Optional[Tuple] = None,
        context: Optional[SelectionContext] = None,
    ) -> ShapeID:
        """Register a new shape in the TNP registry.

        Reuses existing ShapeID slots per (feature_id, shape_type, local_index)
        so that UUIDs remain stable across rebuilds.

        Args:
            ocp_shape: OCP TopoDS_Shape to register.
            shape_type: EDGE, FACE, VERTEX, etc.
            feature_id: Owning feature identifier.
            local_index: Index within the feature.
            geometry_data: Pre-computed geometry tuple (optional).
            context: v5.0 SelectionContext for semantic matching (optional).

        Returns:
            The (possibly reused) ShapeID for this shape.

        Raises:
            ValueError: If ocp_shape is None.
        """
        if ocp_shape is None:
            raise ValueError("ocp_shape cannot be None")

        if geometry_data is None and HAS_OCP:
            geometry_data = self._extract_geometry_data(ocp_shape, shape_type)

        # --- find or create ShapeID ---
        feature_bucket = self._by_feature.setdefault(feature_id, [])
        existing_shape_id = None
        existing_index = None
        for idx in range(len(feature_bucket) - 1, -1, -1):
            sid = feature_bucket[idx]
            if sid.shape_type != shape_type:
                continue
            if int(getattr(sid, "local_index", -1)) == int(local_index):
                existing_shape_id = sid
                existing_index = idx
                break

        if existing_shape_id is not None:
            shape_id = existing_shape_id
        else:
            shape_id = ShapeID.create(
                shape_type=shape_type,
                feature_id=feature_id,
                local_index=local_index,
                geometry_data=geometry_data or (),
            )

        # v5.0: attach semantic context
        if context is not None:
            shape_id = shape_id.with_context(context)

        # Update feature bucket
        if existing_index is not None:
            feature_bucket[existing_index] = shape_id
        elif existing_shape_id is None:
            feature_bucket.append(shape_id)

        # Build record
        record = ShapeRecord(shape_id=shape_id, ocp_shape=ocp_shape, is_valid=True)
        record.geometric_signature = record.compute_signature()
        if context is not None:
            record.selection_context = context

        self._shapes[shape_id.uuid] = record
        self._update_spatial_index(shape_id, record)

        return shape_id

    def seed_shape(self, shape_id: ShapeID, ocp_shape: Any) -> None:
        """Register an existing ShapeID -> Shape mapping (e.g. after load).

        Unlike :meth:`register_shape` this does NOT create a new UUID.

        Args:
            shape_id: Pre-existing ShapeID (e.g. from deserialization).
            ocp_shape: The OCP shape to associate.
        """
        if shape_id is None or not getattr(shape_id, "uuid", ""):
            return

        record = ShapeRecord(shape_id=shape_id, ocp_shape=ocp_shape, is_valid=True)
        record.geometric_signature = record.compute_signature()

        # Remove previous spatial entries for the same UUID
        for shape_type_key in self._spatial_index:
            self._spatial_index[shape_type_key] = [
                (pos, sid)
                for pos, sid in self._spatial_index[shape_type_key]
                if sid.uuid != shape_id.uuid
            ]

        self._shapes[shape_id.uuid] = record

        feature_bucket = self._by_feature.setdefault(shape_id.feature_id, [])
        if not any(existing.uuid == shape_id.uuid for existing in feature_bucket):
            feature_bucket.append(shape_id)

        self._update_spatial_index(shape_id, record)

    def register_solid_edges(self, solid: Any, feature_id: str) -> int:
        """Register ALL edges from a solid using IndexedMap for dedup.

        Args:
            solid: Build123d or OCP solid.
            feature_id: Owning feature identifier.

        Returns:
            Number of edges registered.
        """
        if not HAS_OCP:
            return 0

        try:
            from OCP.TopTools import TopTools_IndexedMapOfShape
            from OCP.TopExp import TopExp
            from OCP.TopoDS import TopoDS

            solid_wrapped = solid.wrapped if hasattr(solid, "wrapped") else solid
            edge_map = TopTools_IndexedMapOfShape()
            TopExp.MapShapes_s(solid_wrapped, TopAbs_EDGE, edge_map)

            count = 0
            for i in range(1, edge_map.Extent() + 1):
                edge = TopoDS.Edge_s(edge_map.FindKey(i))
                self.register_shape(edge, ShapeType.EDGE, feature_id, i - 1)
                count += 1

            if is_enabled("tnp_debug_logging"):
                logger.info(
                    f"TNP: {count} Edges for feature '{feature_id}' registered"
                )
            return count
        except Exception as e:
            logger.warning(f"register_solid_edges failed: {e}")
            return 0

    def register_solid_faces(self, solid: Any, feature_id: str) -> int:
        """Register ALL faces from a solid using IndexedMap for dedup.

        Args:
            solid: Build123d or OCP solid.
            feature_id: Owning feature identifier.

        Returns:
            Number of faces registered.
        """
        if not HAS_OCP:
            return 0

        try:
            from OCP.TopTools import TopTools_IndexedMapOfShape
            from OCP.TopExp import TopExp
            from OCP.TopoDS import TopoDS

            solid_wrapped = solid.wrapped if hasattr(solid, "wrapped") else solid
            face_map = TopTools_IndexedMapOfShape()
            TopExp.MapShapes_s(solid_wrapped, TopAbs_FACE, face_map)

            count = 0
            for i in range(1, face_map.Extent() + 1):
                face = TopoDS.Face_s(face_map.FindKey(i))
                self.register_shape(face, ShapeType.FACE, feature_id, i - 1)
                count += 1

            if is_enabled("tnp_debug_logging"):
                logger.info(
                    f"TNP: {count} Faces for feature '{feature_id}' registered"
                )
            return count
        except Exception as e:
            logger.warning(f"register_solid_faces failed: {e}")
            return 0

    def invalidate_feature(self, feature_id: str) -> None:
        """Remove all shapes belonging to *feature_id*.

        Cleans up ``_shapes``, ``_by_feature``, ``_spatial_index`` and
        rebuilds the semantic spatial index afterwards.

        Args:
            feature_id: Feature whose shapes should be removed.
        """
        if feature_id in self._by_feature:
            for shape_id in self._by_feature[feature_id]:
                if shape_id.uuid in self._shapes:
                    del self._shapes[shape_id.uuid]
            del self._by_feature[feature_id]

            for shape_type_key in self._spatial_index:
                self._spatial_index[shape_type_key] = [
                    (pos, sid)
                    for pos, sid in self._spatial_index[shape_type_key]
                    if sid.feature_id != feature_id
                ]

            if is_enabled("tnp_debug_logging"):
                logger.info(f"TNP: Feature '{feature_id}' invalidated")

        self._rebuild_semantic_index()

    def compact(self, current_solid: Any) -> int:
        """Remove shapes no longer present in *current_solid*.

        Also rebuilds the semantic spatial index.

        Args:
            current_solid: The current Build123d/OCP solid to check against.

        Returns:
            Number of stale shapes removed.
        """
        to_remove: List[str] = []
        for uuid, record in self._shapes.items():
            if record.ocp_shape and not self._shape_exists_in_solid(
                record.ocp_shape, current_solid
            ):
                to_remove.append(uuid)

        for uuid in to_remove:
            feat_id = self._shapes[uuid].shape_id.feature_id
            del self._shapes[uuid]
            if feat_id in self._by_feature:
                self._by_feature[feat_id] = [
                    sid for sid in self._by_feature[feat_id] if sid.uuid != uuid
                ]

        if to_remove:
            removed_set = set(to_remove)
            for shape_type_key in self._spatial_index:
                self._spatial_index[shape_type_key] = [
                    (pos, sid)
                    for pos, sid in self._spatial_index[shape_type_key]
                    if sid.uuid not in removed_set
                ]

        if is_enabled("tnp_debug_logging"):
            logger.info(f"TNP compact: {len(to_remove)} stale shapes removed")

        self._rebuild_semantic_index()
        return len(to_remove)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _extract_geometry_data(
        self, ocp_shape: Any, shape_type: ShapeType
    ) -> Tuple:
        """Extract geometry data for hashing (center, length/area).

        Args:
            ocp_shape: OCP TopoDS_Shape.
            shape_type: EDGE or FACE.

        Returns:
            Tuple of floats describing the geometry, or empty tuple.
        """
        if not HAS_OCP:
            return ()

        try:
            if shape_type == ShapeType.EDGE:
                from OCP.BRepAdaptor import BRepAdaptor_Curve
                from OCP.GProp import GProp_GProps
                from OCP.BRepGProp import BRepGProp
                from OCP.TopoDS import TopoDS
                from OCP.TopAbs import TopAbs_EDGE as _TopAbs_EDGE

                if ocp_shape.ShapeType() == _TopAbs_EDGE:
                    edge = TopoDS.Edge_s(ocp_shape)
                else:
                    return ()

                adaptor = BRepAdaptor_Curve(edge)
                u_mid = (adaptor.FirstParameter() + adaptor.LastParameter()) / 2
                pnt = adaptor.Value(u_mid)

                props = GProp_GProps()
                BRepGProp.LinearProperties_s(edge, props)

                return (pnt.X(), pnt.Y(), pnt.Z(), props.Mass())

            elif shape_type == ShapeType.FACE:
                from OCP.BRepGProp import BRepGProp
                from OCP.GProp import GProp_GProps

                props = GProp_GProps()
                BRepGProp.SurfaceProperties_s(ocp_shape, props)

                center = props.CentreOfMass()
                return (center.X(), center.Y(), center.Z(), props.Mass())

        except Exception as e:
            logger.debug(f"Geometry data extraction failed: {e}")

        return ()

    def _update_spatial_index(self, shape_id: ShapeID, record: ShapeRecord) -> None:
        """Update both the legacy spatial index and the semantic spatial index.

        Args:
            shape_id: The ShapeID being indexed.
            record: Corresponding ShapeRecord with geometric_signature.
        """
        # Remove old entries from legacy spatial index
        for shape_type_key in self._spatial_index:
            self._spatial_index[shape_type_key] = [
                (pos, sid)
                for pos, sid in self._spatial_index[shape_type_key]
                if sid.uuid != shape_id.uuid
            ]

        center = record.geometric_signature.get("center")
        if center is not None:
            self._spatial_index[shape_id.shape_type].append(
                (np.array(center), shape_id)
            )

        # Update semantic spatial index (v5.0)
        if hasattr(self, "_semantic_spatial_index"):
            self._semantic_spatial_index.remove(shape_id.uuid)
            bounds = compute_bounds_from_signature(record.geometric_signature)
            if bounds is None and center is not None:
                bounds = Bounds.from_center(tuple(center), 0.5)
            if bounds is not None:
                self._semantic_spatial_index.insert(
                    shape_id=shape_id.uuid,
                    bounds=bounds,
                    shape_data={
                        "shape_type": shape_id.shape_type.name,
                        "feature_id": shape_id.feature_id,
                        "local_index": int(shape_id.local_index),
                        "shape": record.ocp_shape,
                    },
                )

    def _rebuild_semantic_index(self) -> None:
        """Rebuild the semantic spatial index from all current shapes."""
        self._semantic_spatial_index = SpatialIndex()
        self._semantic_matcher = SemanticMatcher(self._semantic_spatial_index)

        for record in self._shapes.values():
            if record is None or record.ocp_shape is None:
                continue
            bounds = compute_bounds_from_signature(record.geometric_signature)
            if bounds is None and "center" in record.geometric_signature:
                bounds = Bounds.from_center(
                    tuple(record.geometric_signature["center"]), 0.5
                )
            if bounds is None:
                continue
            self._semantic_spatial_index.insert(
                shape_id=record.shape_id.uuid,
                bounds=bounds,
                shape_data={
                    "shape_type": record.shape_id.shape_type.name,
                    "feature_id": record.shape_id.feature_id,
                    "local_index": int(record.shape_id.local_index),
                    "shape": record.ocp_shape,
                },
            )
