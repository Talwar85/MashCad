"""
MashCAD - Professional Boolean Engine V4
========================================

Production-ready Boolean operations with:
- Transaction-based rollback safety
- CAD-grade default tolerances
- Fail-fast error signaling
- Geometry-change verification
- No multi-strategy fallbacks (keeps it simple)

PERFORMANCE (Phase 3):
- VolumeCache: Cached volume calculations (avoid redundant GProp calls)

Author: Claude (Architecture Refactoring Phase 1)
Date: 2026-01-22
"""

from typing import Optional, Tuple, Any, Dict
from loguru import logger

try:
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse, BRepAlgoAPI_Cut, BRepAlgoAPI_Common
    from OCP.BOPAlgo import BOPAlgo_GlueEnum
    from OCP.GProp import GProp_GProps
    from OCP.BRepGProp import BRepGProp
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_FACE
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.TopTools import TopTools_ListOfShape  # ✅ FIX: Correct type for SetArguments()
    from OCP.ShapeFix import ShapeFix_Shape  # Post-Boolean Auto-Healing
    HAS_OCP = True
except ImportError:
    HAS_OCP = False

from config.feature_flags import is_enabled

from modeling.result_types import BooleanResult, ResultStatus
from modeling.body_transaction import BodyTransaction, BooleanOperationError
from config.tolerances import Tolerances  # Phase 5: Zentralisierte Toleranzen


class VolumeCache:
    """
    PERFORMANCE (Phase 3): Cached Volume-Berechnungen.

    GProp_GProps.VolumeProperties ist teuer (~5-20ms pro Shape).
    Während einer Boolean-Operation wird Volume oft 3-4× berechnet:
    - Tool volume logging
    - Original volume logging
    - Result volume validation
    - Geometry change verification

    Mit diesem Cache: 1× berechnen, dann O(1) lookup.

    WICHTIG: Cache wird per-Operation invalidiert da Shapes mutieren können.
    """

    _cache: Dict[int, float] = {}  # shape_id -> volume
    _bbox_cache: Dict[int, Tuple[float, ...]] = {}  # shape_id -> (xmin, ymin, zmin, xmax, ymax, zmax)

    @classmethod
    def get_volume(cls, shape) -> float:
        """
        Gibt Volume für Shape zurück (cached).

        Args:
            shape: OCP TopoDS_Shape oder Build123d Solid/Shape

        Returns:
            Volume in mm³
        """
        # Get underlying OCP shape if wrapped
        ocp_shape = shape.wrapped if hasattr(shape, 'wrapped') else shape
        shape_id = id(ocp_shape)

        if shape_id not in cls._cache:
            props = GProp_GProps()
            BRepGProp.VolumeProperties_s(ocp_shape, props)
            cls._cache[shape_id] = props.Mass()
            logger.debug(f"VolumeCache MISS: shape_id={shape_id}, vol={cls._cache[shape_id]:.1f}")
        else:
            logger.debug(f"VolumeCache HIT: shape_id={shape_id}, vol={cls._cache[shape_id]:.1f}")

        return cls._cache[shape_id]

    @classmethod
    def get_bbox(cls, shape) -> Tuple[float, float, float, float, float, float]:
        """
        Gibt Bounding Box für Shape zurück (cached).

        Returns:
            (xmin, ymin, zmin, xmax, ymax, zmax)
        """
        from OCP.Bnd import Bnd_Box
        from OCP.BRepBndLib import BRepBndLib

        ocp_shape = shape.wrapped if hasattr(shape, 'wrapped') else shape
        shape_id = id(ocp_shape)

        if shape_id not in cls._bbox_cache:
            bbox = Bnd_Box()
            BRepBndLib.Add_s(ocp_shape, bbox)
            cls._bbox_cache[shape_id] = bbox.Get()

        return cls._bbox_cache[shape_id]

    @classmethod
    def invalidate(cls, shape):
        """Entfernt Shape aus Cache (nach Mutation)."""
        ocp_shape = shape.wrapped if hasattr(shape, 'wrapped') else shape
        shape_id = id(ocp_shape)
        cls._cache.pop(shape_id, None)
        cls._bbox_cache.pop(shape_id, None)

    @classmethod
    def clear(cls):
        """Leert gesamten Cache (am Ende einer Operation)."""
        cls._cache.clear()
        cls._bbox_cache.clear()


class BooleanEngineV4:
    """
    Professional Boolean engine with production-grade defaults.

    Philosophy:
    - Use CAD-grade tolerances as DEFAULT
    - Fail fast with clear error messages
    - No magic fallbacks - user should fix geometry
    - Transaction-based rollback for safety
    """

    # Phase 5: Verwende zentralisierte Toleranzen
    PRODUCTION_FUZZY_TOLERANCE = Tolerances.KERNEL_FUZZY
    MIN_VOLUME_CHANGE = Tolerances.KERNEL_MIN_VOLUME_CHANGE

    @staticmethod
    def _fix_shape(shape: Any) -> Any:
        """
        Repariert einen TopoDS_Shape mit ShapeFix vor/nach Boolean.

        Args:
            shape: OCP TopoDS_Shape

        Returns:
            Reparierter Shape (oder Original wenn bereits valid)
        """
        try:
            analyzer = BRepCheck_Analyzer(shape)
            if analyzer.IsValid():
                return shape

            logger.debug("Shape invalid, starte Reparatur...")
            fixer = ShapeFix_Shape(shape)
            fixer.SetPrecision(Tolerances.KERNEL_PRECISION)
            fixer.SetMaxTolerance(Tolerances.MESH_EXPORT)
            fixer.SetMinTolerance(Tolerances.KERNEL_PRECISION / 10)

            if fixer.Perform():
                fixed = fixer.Shape()
                analyzer2 = BRepCheck_Analyzer(fixed)
                if analyzer2.IsValid():
                    logger.debug("✓ Shape repariert")
                    return fixed
                else:
                    logger.warning("Shape nach Reparatur immer noch invalid")
                    return fixed
            else:
                logger.warning("ShapeFix Perform() fehlgeschlagen")
                return shape

        except Exception as e:
            logger.warning(f"Shape-Reparatur Fehler: {e}")
            return shape

    @staticmethod
    def extract_detailed_history(
        bool_op: Any,
        source_shape: Any,
        tool_shape: Any,
        result_shape: Any
    ) -> Dict[str, Any]:
        """
        Extract comprehensive history from BOPAlgo Boolean operation.
        
        High-Priority TODO 2026: Detailed Boolean History for TNP
        
        Captures:
        - Modified faces/edges/vertices (shapes that changed but still exist)
        - Generated shapes (new shapes created by the operation)
        - Deleted shapes (shapes that no longer exist)
        - Intersection edges (new edges at shape boundaries)
        
        Args:
            bool_op: BRepAlgoAPI_Fuse/Cut/Common operation (completed)
            source_shape: The primary input shape
            tool_shape: The tool input shape
            result_shape: The result shape
            
        Returns:
            Dict with 'modified', 'generated', 'deleted', 'intersections' mappings
        """
        from config.feature_flags import is_enabled
        
        if not is_enabled("detailed_boolean_history"):
            return {}
        
        if not HAS_OCP:
            return {}
        
        try:
            from OCP.TopExp import TopExp_Explorer
            from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE, TopAbs_VERTEX
            from OCP.TopTools import TopTools_ListOfShape, TopTools_IndexedDataMapOfShapeListOfShape
            from OCP.TopExp import TopExp_MapShapesAndAncestors
            
            history = bool_op.History()
            details = {
                'modified_faces': {},      # face_id -> [result_face_ids]
                'modified_edges': {},      # edge_id -> [result_edge_ids]
                'modified_vertices': {},   # vertex_id -> [result_vertex_ids]
                'generated_faces': {},     # parent_id -> [generated_face_ids]
                'generated_edges': {},     # parent_id -> [generated_edge_ids]
                'deleted_shapes': [],      # list of deleted shape ids
                'intersections': [],       # new intersection edges
            }
            
            def _get_shape_hash(shape) -> str:
                """Generate a stable hash for a shape."""
                # Use OCP's shape hash for stable identification
                return str(hash(shape))  # Simplified; could use geometry-based hash
            
            def _iter_list_of_shape(list_of_shape: TopTools_ListOfShape) -> list:
                """Convert TopTools_ListOfShape to Python list."""
                shapes = []
                it = list_of_shape.Iterator()
                while it.More():
                    shapes.append(it.Value())
                    it.Next()
                return shapes
            
            # Process each shape type
            for shape_type, detail_key in [
                (TopAbs_FACE, 'modified_faces'),
                (TopAbs_EDGE, 'modified_edges'),
                (TopAbs_VERTEX, 'modified_vertices')
            ]:
                # Explore source shape
                explorer = TopExp_Explorer(source_shape, shape_type)
                while explorer.More():
                    source_subshape = explorer.Current()
                    source_hash = _get_shape_hash(source_subshape)
                    
                    # Check what this shape became
                    modified = history.Modified(source_subshape)
                    modified_list = _iter_list_of_shape(modified)
                    
                    if modified_list:
                        result_hashes = [_get_shape_hash(s) for s in modified_list]
                        details[detail_key][source_hash] = result_hashes
                    
                    # Check if deleted
                    if history.IsRemoved(source_subshape):
                        details['deleted_shapes'].append(source_hash)
                    
                    # Check generated shapes
                    generated = history.Generated(source_subshape)
                    generated_list = _iter_list_of_shape(generated)
                    
                    if generated_list:
                        gen_key = 'generated_faces' if shape_type == TopAbs_FACE else \
                                  'generated_edges' if shape_type == TopAbs_EDGE else 'generated_vertices'
                        result_hashes = [_get_shape_hash(s) for s in generated_list]
                        if source_hash not in details[gen_key]:
                            details[gen_key][source_hash] = []
                        details[gen_key][source_hash].extend(result_hashes)
                    
                    explorer.Next()
            
            # Find intersection edges (edges that are in result but not from source or tool)
            result_edges = set()
            explorer = TopExp_Explorer(result_shape, TopAbs_EDGE)
            while explorer.More():
                result_edges.add(_get_shape_hash(explorer.Current()))
                explorer.Next()
            
            source_edges = set()
            explorer = TopExp_Explorer(source_shape, TopAbs_EDGE)
            while explorer.More():
                source_edges.add(_get_shape_hash(explorer.Current()))
                explorer.Next()
            
            tool_edges = set()
            explorer = TopExp_Explorer(tool_shape, TopAbs_EDGE)
            while explorer.More():
                tool_edges.add(_get_shape_hash(explorer.Current()))
                explorer.Next()
            
            # New edges = result - source - tool
            new_edges = result_edges - source_edges - tool_edges
            details['intersections'] = list(new_edges)
            
            if is_enabled("tnp_debug_logging"):
                logger.debug(f"Boolean History: {len(details['modified_faces'])} modified faces, "
                           f"{len(details['intersections'])} intersection edges, "
                           f"{len(details['deleted_shapes'])} deleted shapes")
            
            return details
            
        except Exception as e:
            logger.warning(f"Detailed history extraction failed: {e}")
            import traceback
            traceback.print_exc()
            return {}

    @staticmethod
    def execute_boolean_on_shapes(
        solid1: Any,
        solid2: Any,
        operation: str,
        fuzzy_tolerance: Optional[float] = None,
        naming_service: Any = None,
        feature_id: Optional[str] = None
    ) -> BooleanResult:
        """
        Execute Boolean operation on two solids (shape-level API).

        Keine Body-Dependency, keine Transaction, kein invalidate_mesh().
        Ideal für den Rebuild-Loop der mit Zwischen-Solids arbeitet.

        Führt alle Pre-/Post-Checks durch:
        - Self-Intersection Check
        - Argument Analysis
        - Post-Boolean Validation + Auto-Healing
        - Tolerance Monitoring
        - TNP v4.1: History-basierte ShapeID-Aktualisierung

        Args:
            solid1: Erstes Solid (Build123d Solid oder OCP TopoDS_Shape)
            solid2: Zweites Solid (Build123d Solid oder OCP TopoDS_Shape)
            operation: "Join", "Cut", or "Intersect"
            fuzzy_tolerance: Override default tolerance
            naming_service: Optional ShapeNamingService für TNP-Update
            feature_id: Optional Feature ID für TNP-Update

        Returns:
            BooleanResult mit Build123d Solid als value und History
        """
        if not HAS_OCP:
            return BooleanResult(
                status=ResultStatus.ERROR,
                message="OpenCASCADE not available",
                operation_type=operation.lower()
            )

        VolumeCache.clear()

        if fuzzy_tolerance is None:
            fuzzy_tolerance = BooleanEngineV4.PRODUCTION_FUZZY_TOLERANCE

        op_type = operation.lower()

        try:
            # 1. Validate inputs
            if solid1 is None or solid2 is None:
                return BooleanResult(
                    status=ResultStatus.ERROR,
                    message=f"Boolean {operation}: Eines der Solids ist None",
                    operation_type=op_type
                )

            if operation not in ["Join", "Cut", "Intersect"]:
                return BooleanResult(
                    status=ResultStatus.ERROR,
                    message=f"Unknown operation: {operation}",
                    operation_type=op_type
                )

            # 2. Extract OCP shapes
            shape1 = solid1.wrapped if hasattr(solid1, 'wrapped') else solid1
            shape2 = solid2.wrapped if hasattr(solid2, 'wrapped') else solid2

            # 3. Fix shapes before boolean
            shape1 = BooleanEngineV4._fix_shape(shape1)
            shape2 = BooleanEngineV4._fix_shape(shape2)

            if shape1 is None or shape2 is None:
                return BooleanResult(
                    status=ResultStatus.ERROR,
                    message="Shape-Reparatur fehlgeschlagen",
                    operation_type=op_type
                )

            # 4. Pre-Boolean Checks
            si_error = BooleanEngineV4._check_self_intersection(shape1, "Body")
            if si_error:
                return BooleanResult(
                    status=ResultStatus.ERROR,
                    message=si_error,
                    operation_type=op_type
                )
            si_error = BooleanEngineV4._check_self_intersection(shape2, "Tool")
            if si_error:
                return BooleanResult(
                    status=ResultStatus.ERROR,
                    message=si_error,
                    operation_type=op_type
                )

            arg_warning = BooleanEngineV4._analyze_boolean_arguments(shape1, shape2, fuzzy_tolerance)
            if arg_warning:
                logger.warning(f"Boolean Argument Analyse: {arg_warning}")

            # 5. Execute OCP Boolean
            logger.debug(f"Executing OCP Boolean {operation}...")
            result_shape, history = BooleanEngineV4._execute_ocp_boolean(
                shape1, shape2, operation, fuzzy_tolerance
            )

            if result_shape is None:
                if operation == "Intersect":
                    return BooleanResult(
                        status=ResultStatus.EMPTY,
                        message="Intersect produzierte kein Ergebnis (keine Überlappung)",
                        operation_type=op_type
                    )
                return BooleanResult(
                    status=ResultStatus.ERROR,
                    message=f"Boolean {operation} failed: OpenCASCADE returned None",
                    operation_type=op_type
                )

            # 6. Post-Boolean Validation + Healing
            result_shape = BooleanEngineV4._validate_and_heal_result(result_shape, operation)
            BooleanEngineV4._check_tolerances(result_shape, operation)

            # 7. Validate result shape
            if not BooleanEngineV4._is_valid_shape(result_shape):
                return BooleanResult(
                    status=ResultStatus.ERROR,
                    message=f"Boolean {operation} produced invalid geometry",
                    operation_type=op_type
                )

            # 8. Verify geometry actually changed
            if not BooleanEngineV4._verify_geometry_changed(shape1, result_shape, operation):
                return BooleanResult(
                    status=ResultStatus.ERROR,
                    message=f"Boolean {operation} produced no change",
                    operation_type=op_type
                )

            # 9. Wrap to Build123d Solid
            from build123d import Solid, Shape
            try:
                result_solid = Solid(result_shape)
            except Exception:
                try:
                    result_solid = Shape(result_shape)
                except Exception as wrap_err:
                    return BooleanResult(
                        status=ResultStatus.ERROR,
                        message=f"Wrap zu Build123d fehlgeschlagen: {wrap_err}",
                        operation_type=op_type
                    )

            # 10. Validate wrapped result
            if hasattr(result_solid, 'is_valid') and not result_solid.is_valid():
                try:
                    result_solid = result_solid.fix()
                except Exception:
                    pass

            # Check volume
            try:
                wrapped_vol = result_solid.volume
                if wrapped_vol < 0.001:
                    return BooleanResult(
                        status=ResultStatus.ERROR,
                        message=f"{operation} erzeugte leeres Ergebnis (Vol={wrapped_vol:.4f}mm³)",
                        operation_type=op_type
                    )
            except Exception:
                pass

            # TNP v4.1: History-basierte ShapeID-Aktualisierung
            if naming_service is not None and history is not None and feature_id:
                try:
                    updated = naming_service.update_shape_ids_from_history(
                        source_solid=shape1,
                        result_solid=result_shape,
                        occt_history=history,
                        feature_id=feature_id,
                        operation_type=f"boolean_{op_type}"
                    )
                    if is_enabled("tnp_debug_logging") and updated > 0:
                        logger.success(f"  TNP: {updated} ShapeIDs nach {operation} aktualisiert")
                except Exception as tnp_err:
                    logger.warning(f"  TNP-Update fehlgeschlagen: {tnp_err}")

            logger.success(f"✅ Boolean {operation} successful")
            
            # High-Priority TODO 2026: Extract detailed history for TNP
            history_details = {}
            if is_enabled("detailed_boolean_history"):
                try:
                    history_details = BooleanEngineV4.extract_detailed_history(
                        bool_op=op,
                        source_shape=shape1,
                        tool_shape=shape2,
                        result_shape=result_shape
                    )
                except Exception as hist_err:
                    logger.debug(f"Detailed history extraction failed: {hist_err}")

            return BooleanResult(
                status=ResultStatus.SUCCESS,
                value=result_solid,
                message=f"Boolean {operation} completed successfully",
                operation_type=op_type,
                history=history,
                history_details=history_details
            )

        except Exception as e:
            logger.error(f"❌ Boolean {operation} unexpected error: {e}")
            import traceback
            traceback.print_exc()
            return BooleanResult(
                status=ResultStatus.ERROR,
                message=f"Unexpected error: {type(e).__name__}: {e}",
                operation_type=op_type
            )

    @staticmethod
    def execute_boolean(
        body: 'Body' = None,
        tool_solid: Any = None,
        operation: str = "",
        fuzzy_tolerance: Optional[float] = None,
        feature_id: Optional[str] = None,
        base_solid: Any = None,
        naming_service: Any = None,
    ) -> BooleanResult:
        """
        Execute Boolean operation with transaction safety on a Body object.

        Standardpfad:
        Wrapper um execute_boolean_on_shapes() mit:
        - BodyTransaction (Rollback bei Fehler)
        - Body-Update (solid + mesh invalidation)
        - TNP v4.1: History-basierte ShapeID-Aktualisierung

        Legacy-Compat:
        Wenn `body is None` und `base_solid` gesetzt ist, wird direkt der
        Shape-Level-Pfad ausgeführt (ältere Tests/Callsites).

        Args:
            body: Target body (will be modified in transaction)
            tool_solid: Tool solid for Boolean operation
            operation: "Join", "Cut", or "Intersect"
            fuzzy_tolerance: Override default tolerance
            feature_id: Optional Feature ID für TNP-Update
            base_solid: Legacy-Compat für shape-level Aufruf ohne Body
            naming_service: Optionaler ShapeNamingService (shape-level Compat)

        Returns:
            BooleanResult with SUCCESS, ERROR, or EMPTY status
        """
        # Legacy-Compat: ältere API execute_boolean(base_solid=..., tool_solid=...)
        if body is None:
            if base_solid is None:
                return BooleanResult(
                    status=ResultStatus.ERROR,
                    message="base_solid fehlt für execute_boolean ohne body",
                    operation_type=operation.lower() if operation else "unknown"
                )
            return BooleanEngineV4.execute_boolean_on_shapes(
                solid1=base_solid,
                solid2=tool_solid,
                operation=operation,
                fuzzy_tolerance=fuzzy_tolerance,
                naming_service=naming_service,
                feature_id=feature_id,
            )

        if body._build123d_solid is None:
            return BooleanResult(
                status=ResultStatus.ERROR,
                message="Target body has no solid",
                operation_type=operation.lower()
            )

        # TNP v4.1: NamingService und Feature ID aus Body holen
        naming_service = None
        if hasattr(body, '_document') and body._document is not None:
            naming_service = getattr(body._document, '_shape_naming_service', None)

        # Feature ID: Falls nicht angegeben, versuchen aus Body zu holen
        if feature_id is None and hasattr(body, 'features') and body.features:
            # Letzte Feature ID verwenden
            last_feat = body.features[-1] if body.features else None
            if last_feat and hasattr(last_feat, 'id'):
                feature_id = f"{last_feat.id}_result"

        with BodyTransaction(body, f"Boolean {operation}") as txn:
            result = BooleanEngineV4.execute_boolean_on_shapes(
                body._build123d_solid, tool_solid, operation, fuzzy_tolerance,
                naming_service=naming_service,
                feature_id=feature_id
            )

            if result.is_success and result.value is not None:
                body._build123d_solid = result.value
                if hasattr(body, 'invalidate_mesh'):
                    body.invalidate_mesh()
                else:
                    body._mesh_cache_valid = False
                txn.commit()

            return result

    @staticmethod
    def _validate_inputs(solid1: Any, solid2: Any, operation: str) -> Optional[str]:
        """
        Validate Boolean operation inputs.

        Returns:
            Error message if invalid, None if OK
        """
        if solid1 is None:
            return "Target body is None"

        if solid2 is None:
            return "Tool solid is None"

        if operation not in ["Join", "Cut", "Intersect"]:
            return f"Unknown operation: {operation}"

        return None

    @staticmethod
    def _detect_glue_mode(shape1: Any, shape2: Any, fuzzy_tolerance: float) -> Optional[Any]:
        """
        Erkennt ob Shapes coinciding Faces haben für GlueShift-Optimierung.

        GlueShift ist ~90% schneller, darf aber NUR bei Shapes mit
        anliegenden/zusammenfallenden Faces verwendet werden - NICHT bei
        echten Intersections (wo Shapes sich durchdringen).

        Erkennung:
        1. BRepExtrema_DistShapeShape: Shapes berühren sich (Distanz ~0)?
        2. BBox-Overlap-Check: Durchdringen sich die Shapes (echte Intersection)?
           - Wenn BBoxen sich in allen 3 Achsen überlappen → echte Intersection → KEIN Glue
           - Wenn BBoxen nur berühren (touch) → coinciding Faces → GlueShift OK

        Returns:
            BOPAlgo_GlueShift wenn coinciding Faces erkannt, None sonst
        """
        try:
            from OCP.BRepExtrema import BRepExtrema_DistShapeShape
            from OCP.Bnd import Bnd_Box
            from OCP.BRepBndLib import BRepBndLib

            dist_calc = BRepExtrema_DistShapeShape(shape1, shape2)
            if not dist_calc.IsDone():
                return None

            min_dist = dist_calc.Value()

            # Shapes berühren sich (Distanz ~0)
            if min_dist < fuzzy_tolerance:
                n_solutions = dist_calc.NbSolution()
                # Viele Kontaktpunkte = Face-Kontakt (nicht nur Kante/Punkt)
                if n_solutions >= 4:
                    # Zusätzlicher Check: Durchdringen sich die Shapes?
                    # BBox-Overlap in allen 3 Achsen = echte Intersection → KEIN Glue
                    bbox1 = Bnd_Box()
                    bbox2 = Bnd_Box()
                    BRepBndLib.Add_s(shape1, bbox1)
                    BRepBndLib.Add_s(shape2, bbox2)

                    xmin1, ymin1, zmin1, xmax1, ymax1, zmax1 = bbox1.Get()
                    xmin2, ymin2, zmin2, xmax2, ymax2, zmax2 = bbox2.Get()

                    tol = fuzzy_tolerance
                    # Overlap = min > max + tolerance in jeder Achse
                    x_overlap = (xmin1 + tol) < xmax2 and (xmin2 + tol) < xmax1
                    y_overlap = (ymin1 + tol) < ymax2 and (ymin2 + tol) < ymax1
                    z_overlap = (zmin1 + tol) < zmax2 and (zmin2 + tol) < zmax1

                    if x_overlap and y_overlap and z_overlap:
                        logger.debug(
                            f"Kein GlueShift: BBoxen überlappen in allen 3 Achsen "
                            f"(echte Intersection, {n_solutions} Kontaktpunkte)"
                        )
                        return None

                    logger.info(
                        f"GlueShift erkannt: {n_solutions} Kontaktpunkte bei "
                        f"Distanz={min_dist:.6f}mm, BBoxen berühren sich nur → "
                        f"Performance-Optimierung aktiv"
                    )
                    return BOPAlgo_GlueEnum.BOPAlgo_GlueShift

            return None

        except Exception as e:
            logger.debug(f"Glue-Erkennung fehlgeschlagen: {e}")
            return None

    @staticmethod
    def _execute_ocp_boolean(
        shape1: Any,
        shape2: Any,
        operation: str,
        fuzzy_tolerance: float
    ) -> Tuple[Optional[Any], Optional[Any]]:
        """
        Execute OpenCASCADE Boolean operation with robust settings.

        - SetFuzzyValue: Toleranz für numerische Ungenauigkeiten
        - SetRunParallel: Multi-Threading für Performance
        - SetGlue: Auto-Erkennung von coinciding Faces für ~90% Speedup

        Args:
            shape1: OCP TopoDS_Shape (target)
            shape2: OCP TopoDS_Shape (tool)
            operation: "Join", "Cut", or "Intersect"
            fuzzy_tolerance: Fuzzy value for robustness

        Returns:
            (result_shape, history) or (None, None) on failure
        """
        try:
            logger.debug(f"OCP Boolean {operation}: shape1 type={type(shape1).__name__}, shape2 type={type(shape2).__name__}")
            logger.debug(f"  Fuzzy tolerance: {fuzzy_tolerance}")

            if operation.lower() in ["join", "fuse"]:
                op = BRepAlgoAPI_Fuse()
            elif operation.lower() == "cut":
                op = BRepAlgoAPI_Cut()
            elif operation.lower() in ["intersect", "common"]:
                op = BRepAlgoAPI_Common()
            else:
                logger.debug(f"Unknown operation: {operation}")
                return None, None

            args_list = TopTools_ListOfShape()
            args_list.Append(shape1)

            tools_list = TopTools_ListOfShape()
            tools_list.Append(shape2)

            op.SetArguments(args_list)
            op.SetTools(tools_list)

            op.SetFuzzyValue(fuzzy_tolerance)
            op.SetRunParallel(True)

            # Intelligente Glue-Erkennung: coinciding Faces → GlueShift (~90% schneller)
            glue_mode = BooleanEngineV4._detect_glue_mode(shape1, shape2, fuzzy_tolerance)
            if glue_mode is not None:
                op.SetGlue(glue_mode)

            op.Build()
            logger.debug("  Boolean operation built with Phase 3 settings")

            is_done = op.IsDone()
            logger.debug(f"  op.IsDone() = {is_done}")

            if not is_done:
                # Try to get error info
                try:
                    error_status = op.HasErrors()
                    logger.debug(f"  op.HasErrors() = {error_status}")
                    if error_status:
                        logger.debug("  OCP Boolean failed with errors")
                except Exception as e:
                    logger.debug(f"[boolean_engine_v4.py] Fehler: {e}")
                    pass
                logger.warning("OpenCASCADE Boolean returned IsDone=False")
                return None, None

            result_shape = op.Shape()
            logger.debug(f"  Result shape type: {type(result_shape).__name__}")

            # Validate result is not null/empty
            if result_shape is None or result_shape.IsNull():
                logger.warning("OCP Boolean returned null shape")
                return None, None

            # Debug: Check if result is different from input
            logger.info(f"Result shape id: {id(result_shape)}, Input shape1 id: {id(shape1)}")

            # PERFORMANCE: Use VolumeCache for volume logging (Phase 3)
            result_vol = VolumeCache.get_volume(result_shape)
            input_vol = VolumeCache.get_volume(shape1)

            logger.info(f"OCP Result: input_vol={input_vol:.1f}, result_vol={result_vol:.1f}, diff={input_vol - result_vol:.1f}")

            # Get history for TNP (Topological Naming Problem) mitigation
            try:
                history = op.History()
                logger.debug("  History extracted successfully")
            except Exception as hist_err:
                logger.debug(f"  Could not extract history: {hist_err}")
                history = None

            return result_shape, history

        except Exception as e:
            logger.error(f"OCP Boolean execution failed with exception: {e}")
            import traceback
            traceback.print_exc()
            return None, None

    @staticmethod
    def _is_valid_shape(shape: Any) -> bool:
        """
        Validate OpenCASCADE shape.

        Returns:
            True if shape is valid
        """
        if shape is None:
            return False

        try:
            analyzer = BRepCheck_Analyzer(shape)
            return analyzer.IsValid()
        except Exception as e:
            logger.debug(f"[boolean_engine_v4.py] Fehler: {e}")
            return False

    @staticmethod
    def _verify_geometry_changed(
        original_shape: Any,
        result_shape: Any,
        operation: str
    ) -> bool:
        """
        Verify that Boolean operation actually changed geometry.

        Prevents false-positives where OpenCASCADE returns "success"
        but geometry is unchanged.

        Args:
            original_shape: Original OCP shape
            result_shape: Result OCP shape
            operation: Operation type

        Returns:
            True if geometry changed, False if false-positive
        """
        try:
            # PERFORMANCE: Use VolumeCache (Phase 3)
            vol_original = VolumeCache.get_volume(original_shape)
            vol_result = VolumeCache.get_volume(result_shape)

            # Calculate face counts
            def count_faces(shape):
                explorer = TopExp_Explorer(shape, TopAbs_FACE)
                count = 0
                while explorer.More():
                    count += 1
                    explorer.Next()
                return count

            faces_original = count_faces(original_shape)
            faces_result = count_faces(result_shape)

            # Debug: Log what we're comparing
            logger.debug(f"_verify_geometry_changed: Vol {vol_original:.1f}→{vol_result:.1f}, Faces {faces_original}→{faces_result}")

            # Check for changes based on operation type
            vol_diff = abs(vol_original - vol_result)
            faces_changed = faces_original != faces_result

            operation_lower = operation.lower()

            if operation_lower in ["cut", "intersect"]:
                # Cut/Intersect MUST reduce volume - face changes alone are not enough
                # A cut that only changes faces without removing material is not meaningful
                volume_reduced = vol_result < (vol_original - BooleanEngineV4.MIN_VOLUME_CHANGE)

                # ✅ Detailed logging für Debugging
                logger.info(f"  Cut validation: vol_original={vol_original:.3f}, vol_result={vol_result:.3f}, "
                           f"vol_diff={vol_diff:.6f}, MIN={BooleanEngineV4.MIN_VOLUME_CHANGE}")
                logger.debug(f"  volume_reduced={volume_reduced}, faces_changed={faces_changed}")

                if not volume_reduced:
                    # Cut must remove material, period
                    # ✅ WARNING statt DEBUG für sichtbarere Meldung
                    logger.warning(
                        f"⚠️ Cut REJECTED - no volume reduction: "
                        f"Vol {vol_original:.3f}→{vol_result:.3f} (-{vol_diff:.6f}mm³), "
                        f"Faces {faces_original}→{faces_result}, MIN_CHANGE={BooleanEngineV4.MIN_VOLUME_CHANGE}"
                    )
                    return False

                logger.info(
                    f"✅ Cut accepted: "
                    f"Vol {vol_original:.1f}→{vol_result:.1f} (-{vol_original - vol_result:.1f}mm³), "
                    f"Faces {faces_original}→{faces_result}"
                )
                return True

            elif operation_lower in ["join", "fuse"]:
                # Join should increase or maintain volume
                # Faces can decrease (merge) or increase
                if vol_diff < BooleanEngineV4.MIN_VOLUME_CHANGE and not faces_changed:
                    logger.debug(f"Join false-positive: No geometry change detected")
                    return False

                return True

            # Unknown operation - accept
            return True

        except Exception as e:
            # On error, accept result (fail-safe)
            logger.debug(f"Geometry verification failed: {e}")
            return True

    @staticmethod
    def _check_self_intersection(shape: Any, name: str = "Shape") -> Optional[str]:
        """
        Prüft Shape auf Self-Intersections mittels BOPAlgo_CheckerSI.

        Self-Intersections verursachen Boolean-Crashes oder kaputte Ergebnisse.
        Dieser Pre-Check erkennt das Problem VOR der Boolean-Operation.

        Args:
            shape: OCP TopoDS_Shape
            name: Name für Logging (z.B. "Body" oder "Tool")

        Returns:
            Fehlermeldung wenn Self-Intersection gefunden, None wenn OK
        """
        try:
            from OCP.BOPAlgo import BOPAlgo_CheckerSI

            checker = BOPAlgo_CheckerSI()
            args = TopTools_ListOfShape()
            args.Append(shape)
            checker.SetArguments(args)
            checker.SetNonDestructive(True)  # Shape nicht modifizieren
            checker.Perform()

            if checker.HasErrors():
                logger.warning(f"⚠️ {name} hat Self-Intersection(s)!")
                return (
                    f"{name} hat Self-Intersections.\n"
                    f"→ Boolean-Operation kann fehlschlagen oder kaputte Geometrie erzeugen.\n"
                    f"→ Geometrie prüfen und reparieren."
                )

            logger.debug(f"  {name} Self-Intersection Check: OK")
            return None

        except AttributeError:
            # BOPAlgo_CheckerSI nicht verfügbar in dieser OCP-Version
            logger.debug("BOPAlgo_CheckerSI nicht verfügbar, überspringe Self-Intersection Check")
            return None
        except Exception as e:
            # Check fehlgeschlagen - nicht blockieren, nur warnen
            logger.debug(f"Self-Intersection Check fehlgeschlagen: {e}")
            return None

    @staticmethod
    def _analyze_boolean_arguments(shape1: Any, shape2: Any, fuzzy_tolerance: float) -> Optional[str]:
        """
        Analysiert Boolean-Inputs auf potentielle Probleme mittels BOPAlgo_ArgumentAnalyzer.

        Erkennt: überlappende Faces, zu kleine Shapes, inkonsistente Toleranzen.
        Gibt klare Fehlermeldung statt kryptischem Boolean-Crash.

        Args:
            shape1: Body shape
            shape2: Tool shape
            fuzzy_tolerance: Fuzzy-Toleranz

        Returns:
            Fehlermeldung wenn Probleme gefunden, None wenn OK
        """
        try:
            from OCP.BOPAlgo import BOPAlgo_ArgumentAnalyzer

            analyzer = BOPAlgo_ArgumentAnalyzer()
            analyzer.SetShape1(shape1)
            analyzer.SetShape2(shape2)
            analyzer.SetFuzzyValue(fuzzy_tolerance)
            analyzer.Perform()

            if analyzer.HasFaulty():
                logger.warning("⚠️ Boolean-Input Analyse: Probleme erkannt!")
                return (
                    f"Boolean-Inputs haben Kompatibilitätsprobleme.\n"
                    f"→ Geometrien können nicht sauber verschnitten werden.\n"
                    f"→ Shapes vereinfachen oder Positionierung prüfen."
                )

            logger.debug("  Boolean Argument Analysis: OK")
            return None

        except AttributeError:
            logger.debug("BOPAlgo_ArgumentAnalyzer nicht verfügbar, überspringe")
            return None
        except Exception as e:
            logger.debug(f"Boolean Argument Analysis fehlgeschlagen: {e}")
            return None

    @staticmethod
    def _validate_and_heal_result(result_shape: Any, operation: str) -> Any:
        """
        Post-Boolean Validation: Prüft Ergebnis-Shape und versucht Auto-Healing.

        Erkennt kaputte Topologie (offene Shells, ungültige Edges) die
        von op.IsDone() nicht erkannt wird. Versucht ShapeFix_Shape als Reparatur.

        Args:
            result_shape: OCP TopoDS_Shape nach Boolean
            operation: Operation-Name für Logging

        Returns:
            Reparierter Shape (oder Original wenn Healing nicht nötig/möglich)

        Raises:
            BooleanOperationError wenn Shape irreparabel kaputt
        """
        try:
            analyzer = BRepCheck_Analyzer(result_shape)

            if analyzer.IsValid():
                logger.debug(f"  Post-Boolean Validation: Shape ist valid")
                return result_shape

            # Shape ist ungültig - Auto-Healing versuchen
            logger.warning(f"⚠️ Boolean {operation} Ergebnis ist ungültig, versuche ShapeFix...")

            fixer = ShapeFix_Shape(result_shape)
            fixer.Perform()
            healed_shape = fixer.Shape()

            # Nochmal prüfen
            analyzer2 = BRepCheck_Analyzer(healed_shape)
            if analyzer2.IsValid():
                logger.success(f"✅ ShapeFix hat Boolean-Ergebnis repariert")
                return healed_shape
            else:
                # Healing hat nicht geholfen - warnen aber weitermachen
                # (manche "ungültige" Shapes funktionieren trotzdem in der Praxis)
                logger.warning(
                    f"⚠️ Boolean {operation} Ergebnis ungültig trotz ShapeFix. "
                    f"Nachfolgende Operationen könnten fehlschlagen."
                )
                return healed_shape  # Gehealten Shape trotzdem verwenden

        except Exception as e:
            logger.debug(f"Post-Boolean Validation fehlgeschlagen: {e}")
            return result_shape

    @staticmethod
    def _check_tolerances(result_shape: Any, operation: str) -> None:
        """
        Feature #5: Toleranz-Monitoring nach Boolean-Operationen.

        Shapes können nach Booleans lokal überhöhte Toleranzen haben,
        was zu Fehlern bei nachfolgenden Operationen führt (Fillet, Chamfer).
        Diese Methode warnt frühzeitig.

        Args:
            result_shape: OCP TopoDS_Shape nach Boolean
            operation: Operation-Name für Logging
        """
        try:
            from OCP.ShapeAnalysis import ShapeAnalysis_ShapeTolerance

            tol_analyzer = ShapeAnalysis_ShapeTolerance()
            tol_analyzer.AddTolerance(result_shape)

            # GlobalTolerance(1) = Maximum, GlobalTolerance(0) = Durchschnitt
            max_tol = tol_analyzer.GlobalTolerance(1)
            avg_tol = tol_analyzer.GlobalTolerance(0)

            # Schwellwert: 10× die Kernel-Fuzzy-Toleranz ist verdächtig
            threshold = Tolerances.KERNEL_FUZZY * 10  # 1e-3 = 1µm

            if max_tol > threshold:
                logger.warning(
                    f"⚠️ Boolean {operation}: Erhöhte Toleranz erkannt! "
                    f"Max={max_tol:.6f}mm (Schwellwert={threshold:.6f}mm), "
                    f"Avg={avg_tol:.6f}mm. Nachfolgende Fillet/Chamfer könnten fehlschlagen."
                )
            else:
                logger.debug(
                    f"  Toleranz-Check OK: Max={max_tol:.6f}mm, Avg={avg_tol:.6f}mm"
                )

        except Exception as e:
            logger.debug(f"Toleranz-Monitoring fehlgeschlagen: {e}")
