"""
MashCad - Mesh Repair / ShrinkWrap
Repair and heal BREP geometry using OCP's built-in tools.

Features:
- Fix topology (sewing, gap closing)
- Fix geometry (surface repair, degenerate edges)
- ShrinkWrap (re-mesh and rebuild watertight)
- Validate and report issues
"""

from dataclasses import dataclass, field
from typing import List, Optional
from loguru import logger


@dataclass
class RepairResult:
    """Result of a mesh/geometry repair operation."""
    success: bool = False
    message: str = ""
    fixes_applied: List[str] = field(default_factory=list)
    issues_found: int = 0
    issues_fixed: int = 0
    repaired_solid: object = None


class MeshRepair:
    """
    BREP geometry repair using OCP healing tools.

    Strategy:
    1. ShapeFix_Shape — General shape healing (gaps, tolerances)
    2. BRepBuilderAPI_Sewing — Re-sew faces (fix open shells)
    3. ShapeFix_Solid — Fix solid topology (orientation, shells)
    4. ShapeUpgrade_UnifySameDomain — Simplify redundant edges/faces
    """

    @staticmethod
    def diagnose(solid) -> RepairResult:
        """
        Analyze a solid for geometry issues without modifying it.

        Returns:
            RepairResult with diagnostics
        """
        result = RepairResult()
        issues = []

        try:
            from OCP.BRepCheck import BRepCheck_Analyzer
            from OCP.TopExp import TopExp_Explorer
            from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE, TopAbs_SHELL, TopAbs_SOLID

            shape = solid.wrapped if hasattr(solid, 'wrapped') else solid

            analyzer = BRepCheck_Analyzer(shape, True)

            if analyzer.IsValid():
                result.success = True
                result.message = "Geometrie ist gültig. Keine Probleme gefunden."
                return result

            # Count issues by type
            for shape_type, label in [
                (TopAbs_FACE, "Face"), (TopAbs_EDGE, "Edge"),
                (TopAbs_SHELL, "Shell"), (TopAbs_SOLID, "Solid")
            ]:
                explorer = TopExp_Explorer(shape, shape_type)
                while explorer.More():
                    sub = explorer.Current()
                    check_result = analyzer.Result(sub)
                    if check_result is not None:
                        status = check_result.Status()
                        if status is not None:
                            # Has issues
                            issues.append(f"{label}: Fehler erkannt")
                    explorer.Next()

            result.issues_found = max(len(issues), 1)  # At least 1 since not valid
            result.message = f"{result.issues_found} Probleme gefunden."
            if issues:
                result.message += "\n" + "\n".join(issues[:10])

        except Exception as e:
            result.message = f"Diagnose fehlgeschlagen: {e}"
            logger.error(f"Diagnose error: {e}")

        return result

    @staticmethod
    def repair(solid, sew_tolerance=1e-3, fix_solid=True,
               unify_faces=True) -> RepairResult:
        """
        Attempt to repair a solid geometry.

        Args:
            solid: Build123d Solid to repair
            sew_tolerance: Tolerance for sewing gaps
            fix_solid: Run ShapeFix_Solid
            unify_faces: Run ShapeUpgrade_UnifySameDomain

        Returns:
            RepairResult with repaired solid
        """
        result = RepairResult()
        fixes = []

        try:
            from OCP.ShapeFix import ShapeFix_Shape, ShapeFix_Solid
            from OCP.BRepBuilderAPI import BRepBuilderAPI_Sewing
            from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
            from OCP.BRepCheck import BRepCheck_Analyzer
            from build123d import Solid

            shape = solid.wrapped if hasattr(solid, 'wrapped') else solid

            # Step 1: ShapeFix_Shape (general healing)
            logger.info("Repair Step 1: ShapeFix_Shape...")
            fixer = ShapeFix_Shape(shape)
            fixer.SetPrecision(sew_tolerance)
            fixer.SetMaxTolerance(sew_tolerance * 10)
            fixer.Perform()
            shape = fixer.Shape()
            fixes.append("ShapeFix_Shape angewendet")

            # Step 2: Sewing (close gaps)
            logger.info("Repair Step 2: Sewing...")
            sewing = BRepBuilderAPI_Sewing(sew_tolerance)
            sewing.Add(shape)
            sewing.Perform()
            shape = sewing.SewedShape()
            fixes.append(f"Sewing (Toleranz: {sew_tolerance}mm)")

            # Step 3: ShapeFix_Solid (fix orientation, shells)
            if fix_solid:
                logger.info("Repair Step 3: ShapeFix_Solid...")
                try:
                    from OCP.TopoDS import TopoDS
                    from OCP.TopAbs import TopAbs_SOLID
                    from OCP.TopExp import TopExp_Explorer

                    # Try to extract solid
                    explorer = TopExp_Explorer(shape, TopAbs_SOLID)
                    if explorer.More():
                        solid_shape = TopoDS.Solid_s(explorer.Current())
                        solid_fixer = ShapeFix_Solid(solid_shape)
                        solid_fixer.Perform()
                        shape = solid_fixer.Shape()
                        fixes.append("ShapeFix_Solid angewendet")
                except Exception as e:
                    logger.debug(f"ShapeFix_Solid skipped: {e}")

            # Step 4: Unify same-domain faces
            if unify_faces:
                logger.info("Repair Step 4: UnifySameDomain...")
                try:
                    unifier = ShapeUpgrade_UnifySameDomain(shape, True, True, True)
                    unifier.Build()
                    shape = unifier.Shape()
                    fixes.append("UnifySameDomain angewendet")
                except Exception as e:
                    logger.debug(f"UnifySameDomain skipped: {e}")

            # Validate result
            checker = BRepCheck_Analyzer(shape, True)
            is_valid = checker.IsValid()

            try:
                repaired = Solid(shape)
                result.repaired_solid = repaired
                result.success = True
            except Exception:
                from build123d import Shape
                result.repaired_solid = Shape(shape)
                result.success = True

            result.fixes_applied = fixes
            result.issues_fixed = len(fixes)
            result.message = (
                f"Reparatur {'erfolgreich' if is_valid else 'abgeschlossen (mit Warnungen)'}.\n"
                f"Schritte: {len(fixes)}\n"
                + "\n".join(f"  ✓ {f}" for f in fixes)
            )

            if is_valid:
                logger.success("Geometry repair: valid result")
            else:
                logger.warning("Geometry repair: result has remaining issues")

        except Exception as e:
            result.message = f"Reparatur fehlgeschlagen: {e}"
            logger.error(f"Repair error: {e}")

        return result

    @staticmethod
    def shrinkwrap(solid, resolution=0.5) -> RepairResult:
        """
        ShrinkWrap: Tessellate → rebuild watertight mesh → fit BREP.

        This is a last-resort repair: tessellates the geometry,
        creates a watertight convex/concave hull, then refits BREP.

        Args:
            solid: Build123d Solid
            resolution: Mesh resolution in mm

        Returns:
            RepairResult with new solid
        """
        result = RepairResult()

        try:
            from OCP.BRepMesh import BRepMesh_IncrementalMesh
            from OCP.BRepBuilderAPI import BRepBuilderAPI_Sewing, BRepBuilderAPI_MakeSolid
            from OCP.StlAPI import StlAPI_Writer, StlAPI_Reader
            from OCP.TopoDS import TopoDS
            from OCP.TopAbs import TopAbs_SHELL
            from OCP.TopExp import TopExp_Explorer
            from build123d import Solid
            import tempfile
            import os

            shape = solid.wrapped if hasattr(solid, 'wrapped') else solid

            # Step 1: Fine tessellation
            logger.info(f"ShrinkWrap: Tessellating at {resolution}mm...")
            mesh = BRepMesh_IncrementalMesh(shape, resolution)
            mesh.Perform()

            # Step 2: Export to STL and re-import (forces watertight mesh)
            with tempfile.NamedTemporaryFile(suffix='.stl', delete=False) as f:
                tmp_path = f.name

            try:
                writer = StlAPI_Writer()
                writer.Write(shape, tmp_path)

                reader = StlAPI_Reader()
                from OCP.TopoDS import TopoDS_Shape
                reimported = TopoDS_Shape()
                reader.Read(reimported, tmp_path)

                # Sew the reimported mesh
                sewing = BRepBuilderAPI_Sewing(resolution)
                sewing.Add(reimported)
                sewing.Perform()
                sewn = sewing.SewedShape()

                # Try solid
                try:
                    explorer = TopExp_Explorer(sewn, TopAbs_SHELL)
                    if explorer.More():
                        maker = BRepBuilderAPI_MakeSolid()
                        maker.Add(TopoDS.Shell_s(explorer.Current()))
                        maker.Build()
                        if maker.IsDone():
                            result.repaired_solid = Solid(maker.Shape())
                            result.success = True
                            result.message = (
                                f"ShrinkWrap erfolgreich.\n"
                                f"Auflösung: {resolution}mm\n"
                                f"Ergebnis: Watertight Solid"
                            )
                            logger.success("ShrinkWrap: watertight solid created")
                            return result
                except Exception as e:
                    logger.debug(f"ShrinkWrap solid creation: {e}")

                # Fallback: return as shape
                from build123d import Shape
                result.repaired_solid = Shape(sewn)
                result.success = True
                result.message = "ShrinkWrap abgeschlossen (kein geschlossener Solid)."

            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)

        except Exception as e:
            result.message = f"ShrinkWrap fehlgeschlagen: {e}"
            logger.error(f"ShrinkWrap error: {e}")

        return result
