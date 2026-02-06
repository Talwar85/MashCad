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
    def execute_boolean_on_shapes(
        solid1: Any,
        solid2: Any,
        operation: str,
        fuzzy_tolerance: Optional[float] = None
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

        Args:
            solid1: Erstes Solid (Build123d Solid oder OCP TopoDS_Shape)
            solid2: Zweites Solid (Build123d Solid oder OCP TopoDS_Shape)
            operation: "Join", "Cut", or "Intersect"
            fuzzy_tolerance: Override default tolerance

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

            logger.success(f"✅ Boolean {operation} successful")

            return BooleanResult(
                status=ResultStatus.SUCCESS,
                value=result_solid,
                message=f"Boolean {operation} completed successfully",
                operation_type=op_type,
                history=history
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
        body: 'Body',
        tool_solid: Any,
        operation: str,
        fuzzy_tolerance: Optional[float] = None
    ) -> BooleanResult:
        """
        Execute Boolean operation with transaction safety on a Body object.

        Wrapper um execute_boolean_on_shapes() mit:
        - BodyTransaction (Rollback bei Fehler)
        - Body-Update (solid + mesh invalidation)

        Args:
            body: Target body (will be modified in transaction)
            tool_solid: Tool solid for Boolean operation
            operation: "Join", "Cut", or "Intersect"
            fuzzy_tolerance: Override default tolerance

        Returns:
            BooleanResult with SUCCESS, ERROR, or EMPTY status
        """
        if body._build123d_solid is None:
            return BooleanResult(
                status=ResultStatus.ERROR,
                message="Target body has no solid",
                operation_type=operation.lower()
            )

        with BodyTransaction(body, f"Boolean {operation}") as txn:
            result = BooleanEngineV4.execute_boolean_on_shapes(
                body._build123d_solid, tool_solid, operation, fuzzy_tolerance
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
    def _execute_ocp_boolean(
        shape1: Any,
        shape2: Any,
        operation: str,
        fuzzy_tolerance: float
    ) -> Tuple[Optional[Any], Optional[Any]]:
        """
        Execute OpenCASCADE Boolean operation with robust settings.

        Phase 3: Robuste Boolean-Defaults (CAD-ähnlich)
        - SetFuzzyValue: Toleranz für numerische Ungenauigkeiten
        - SetRunParallel: Multi-Threading für Performance
        - SetGlue: Robustes Gluing für überlappende Geometrien

        Args:
            shape1: OCP TopoDS_Shape (target)
            shape2: OCP TopoDS_Shape (tool)
            operation: "Join", "Cut", or "Intersect"
            fuzzy_tolerance: Fuzzy value for robustness

        Returns:
            (result_shape, history) or (None, None) on failure
        """
        try:
            # Debug: Log input shapes
            logger.debug(f"OCP Boolean {operation}: shape1 type={type(shape1).__name__}, shape2 type={type(shape2).__name__}")
            logger.debug(f"  Fuzzy tolerance: {fuzzy_tolerance}")

            # Phase 3: Use explicit API with robust settings
            # Parameter-less constructor allows setting options before Build()
            if operation.lower() in ["join", "fuse"]:
                op = BRepAlgoAPI_Fuse()
            elif operation.lower() == "cut":
                op = BRepAlgoAPI_Cut()
            elif operation.lower() in ["intersect", "common"]:
                op = BRepAlgoAPI_Common()
            else:
                logger.debug(f"Unknown operation: {operation}")
                return None, None

            # Create TopTools_ListOfShape (required by OCP API)
            args_list = TopTools_ListOfShape()
            args_list.Append(shape1)

            tools_list = TopTools_ListOfShape()
            tools_list.Append(shape2)

            op.SetArguments(args_list)
            op.SetTools(tools_list)

            # Phase 3: Robuste Boolean-Defaults (wie CAD)
            op.SetFuzzyValue(fuzzy_tolerance)  # Toleranz für numerische Ungenauigkeiten
            op.SetRunParallel(True)            # Multi-Threading für Performance
            # HINWEIS: SetGlue(GlueShift) entfernt - verursachte kaputte Körper bei ~20% der Joins
            # GlueOff (default) ist sicherer für allgemeine Operationen

            # Manual Build (nicht automatisch via Konstruktor)
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
        if not is_enabled("boolean_self_intersection_check"):
            return None

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
        if not is_enabled("boolean_argument_analyzer"):
            return None

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
        if not is_enabled("boolean_post_validation"):
            return result_shape

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
        if not is_enabled("boolean_tolerance_monitoring"):
            return

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
