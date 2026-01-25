"""
MashCad - Solid Builder
=======================

Näht BREP Faces zusammen und erstellt wasserdichtes Solid.
Verwendet BRepBuilderAPI_Sewing, ShapeFix, und ShapeUpgrade.
"""

import numpy as np
from typing import List, Optional
from loguru import logger

try:
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Sewing, BRepBuilderAPI_MakeSolid
    from OCP.ShapeFix import ShapeFix_Solid, ShapeFix_Shell, ShapeFix_Shape
    from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.TopoDS import TopoDS, TopoDS_Face, TopoDS_Shell, TopoDS_Solid, TopoDS_Shape
    from OCP.TopAbs import TopAbs_SHELL, TopAbs_SOLID, TopAbs_COMPOUND, TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    from build123d import Solid, Shell, Shape
    HAS_OCP = True
except ImportError:
    HAS_OCP = False
    logger.warning("OCP/build123d nicht verfügbar")

from meshconverter.mesh_converter_v10 import ConversionResult, ConversionStatus


class SolidBuilder:
    """
    Baut wasserdichtes Solid aus BREP Faces.

    Pipeline:
    1. BRepBuilderAPI_Sewing - Faces zusammennähen
    2. ShapeFix_Solid - Reparatur bei Bedarf
    3. ShapeUpgrade_UnifySameDomain - Coplanare Faces mergen
    4. BRepCheck_Analyzer - Validierung
    """

    def __init__(
        self,
        tolerance: float = 0.1,             # mm - Sewing Toleranz
        unify_faces: bool = True,           # Coplanare Faces mergen
        unify_linear_tolerance: float = 0.01,  # mm
        unify_angular_tolerance: float = 0.5,  # Grad
        multi_pass_sewing: bool = True,     # Multi-Pass Sewing für komplexe Meshes
        max_tolerance: float = 2.0          # Maximum Sewing-Toleranz in mm
    ):
        """
        Args:
            tolerance: Sewing-Toleranz in mm
            unify_faces: Coplanare Faces mergen (ShapeUpgrade_UnifySameDomain)
            unify_linear_tolerance: Toleranz für UnifySameDomain (mm)
            unify_angular_tolerance: Winkeltoleranz für UnifySameDomain (Grad)
            multi_pass_sewing: Versuche mit steigender Toleranz bei vielen freien Kanten
            max_tolerance: Maximum Toleranz für Multi-Pass Sewing
        """
        self.sewing_tol = tolerance
        self.unify_faces = unify_faces
        self.unify_linear_tol = unify_linear_tolerance
        self.unify_angular_tol = np.radians(unify_angular_tolerance)
        self.multi_pass_sewing = multi_pass_sewing
        self.max_tolerance = max_tolerance

    def build(self, faces: List['TopoDS_Face']) -> ConversionResult:
        """
        Baut Solid aus Faces.

        Args:
            faces: Liste von TopoDS_Face

        Returns:
            ConversionResult mit Status und Solid/Shell
        """
        if not HAS_OCP:
            return ConversionResult(
                status=ConversionStatus.FAILED,
                message="OCP nicht verfügbar"
            )

        if not faces:
            return ConversionResult(
                status=ConversionStatus.FAILED,
                message="Keine Faces zum Zusammennähen"
            )

        stats = {'input_faces': len(faces)}
        logger.debug(f"Baue Solid aus {len(faces)} Faces...")

        # 1. Sewing
        sewed_shape = self._sew_faces(faces)
        if sewed_shape is None:
            return ConversionResult(
                status=ConversionStatus.FAILED,
                message="Sewing fehlgeschlagen",
                stats=stats
            )

        # Analysiere Shape-Typ
        shape_type = sewed_shape.ShapeType()
        logger.debug(f"Sewed Shape Type: {shape_type}")

        # 2. Zu Solid konvertieren
        solid_result = self._make_solid(sewed_shape)

        if solid_result is None:
            # Kein wasserdichtes Solid möglich - Shell zurückgeben
            logger.warning("Nicht wasserdicht - gebe Shell zurück")
            return self._return_shell(sewed_shape, stats)

        solid = solid_result
        stats['solid_created'] = True

        # 3. Optional: UnifySameDomain
        if self.unify_faces:
            unified = self._unify_faces(solid)
            if unified is not None:
                solid = unified
                stats['faces_unified'] = True

        # 4. Validierung
        is_valid, validation_message = self._validate_shape(solid)
        stats['is_valid'] = is_valid

        # Konvertiere zu Build123d Solid
        b123d_solid = self._to_build123d_solid(solid)

        if not is_valid:
            logger.warning(f"Validierung fehlgeschlagen: {validation_message}")
            # Trotzdem Solid zurückgeben, aber mit PARTIAL Status
            return ConversionResult(
                status=ConversionStatus.PARTIAL,
                solid=b123d_solid,
                message=f"Validierung fehlgeschlagen: {validation_message}",
                stats=stats
            )

        # Erfolg!
        logger.success("Solid erfolgreich erstellt und validiert")
        return ConversionResult(
            status=ConversionStatus.SUCCESS,
            solid=b123d_solid,
            stats=stats
        )

    def _to_build123d_solid(self, shape: 'TopoDS_Shape') -> 'Solid':
        """
        Konvertiert TopoDS_Shape zu Build123d Solid.
        """
        try:
            shape_type = shape.ShapeType()

            if shape_type == TopAbs_SOLID:
                return Solid(TopoDS.Solid_s(shape))

            # Wenn kein Solid, versuche zu konvertieren
            if shape_type == TopAbs_SHELL:
                # Versuche Shell zu Solid
                maker = BRepBuilderAPI_MakeSolid(TopoDS.Shell_s(shape))
                if maker.IsDone():
                    return Solid(maker.Solid())

            if shape_type == TopAbs_COMPOUND:
                # Suche Solid in Compound
                explorer = TopExp_Explorer(shape, TopAbs_SOLID)
                if explorer.More():
                    return Solid(TopoDS.Solid_s(explorer.Current()))

                # Suche Shell und konvertiere
                explorer = TopExp_Explorer(shape, TopAbs_SHELL)
                if explorer.More():
                    shell = TopoDS.Shell_s(explorer.Current())
                    maker = BRepBuilderAPI_MakeSolid(shell)
                    if maker.IsDone():
                        return Solid(maker.Solid())

            # Fallback: Wrap als Shape (kann volume nicht haben)
            logger.warning(f"Konnte Shape-Typ {shape_type} nicht zu Solid konvertieren")
            return Solid.make_solid(Shell(shape)) if shape_type == TopAbs_SHELL else Shape(shape)

        except Exception as e:
            logger.warning(f"Build123d Solid Konvertierung fehlgeschlagen: {e}")
            return Shape(shape)

    def _sew_faces(self, faces: List['TopoDS_Face']) -> Optional['TopoDS_Shape']:
        """
        Näht Faces zusammen.

        Bei Multi-Pass-Sewing werden verschiedene Toleranzen versucht,
        um die beste Verbindung zu erreichen.
        """
        try:
            # Zähle gültige Faces
            valid_faces = [f for f in faces if f is not None and not f.IsNull()]
            if len(valid_faces) == 0:
                logger.error("Keine gültigen Faces zum Sewing")
                return None

            logger.debug(f"  Sewing {len(valid_faces)} Faces...")

            # Multi-Pass Sewing: Versuche verschiedene Toleranzen
            if self.multi_pass_sewing:
                return self._multi_pass_sew(valid_faces)
            else:
                return self._single_pass_sew(valid_faces, self.sewing_tol)

        except Exception as e:
            logger.error(f"Sewing fehlgeschlagen: {e}")
            return None

    def _single_pass_sew(
        self,
        faces: List['TopoDS_Face'],
        tolerance: float
    ) -> tuple:
        """
        Führt einen einzelnen Sewing-Durchgang durch.

        Returns:
            (sewed_shape, n_free_edges) oder (None, -1) bei Fehler
        """
        try:
            sewer = BRepBuilderAPI_Sewing(tolerance)

            for face in faces:
                sewer.Add(face)

            sewer.Perform()
            sewed_shape = sewer.SewedShape()

            if sewed_shape.IsNull():
                return None, -1

            n_free = sewer.NbFreeEdges()
            n_multiple = sewer.NbMultipleEdges()
            n_degenerated = sewer.NbDegeneratedShapes()

            logger.debug(f"    Tol={tolerance:.2f}mm: {n_free} free, "
                        f"{n_multiple} multiple, {n_degenerated} degenerated")

            return sewed_shape, n_free

        except Exception as e:
            logger.debug(f"    Sewing bei Tol={tolerance}mm fehlgeschlagen: {e}")
            return None, -1

    def _multi_pass_sew(self, faces: List['TopoDS_Face']) -> Optional['TopoDS_Shape']:
        """
        Multi-Pass Sewing mit steigender Toleranz.

        Strategie:
        1. Beginne mit initialer Toleranz
        2. Wenn zu viele freie Kanten: verdoppele Toleranz
        3. Wiederhole bis max_tolerance erreicht oder keine freien Kanten
        4. Wähle das Ergebnis mit den wenigsten freien Kanten
        """
        tolerances = []
        tol = self.sewing_tol
        while tol <= self.max_tolerance:
            tolerances.append(tol)
            tol *= 2  # Verdopple Toleranz

        # Auch max_tolerance hinzufügen falls nicht bereits enthalten
        if tolerances[-1] < self.max_tolerance:
            tolerances.append(self.max_tolerance)

        logger.debug(f"  Multi-Pass Sewing mit Toleranzen: {tolerances}")

        best_shape = None
        best_free_edges = float('inf')
        best_tol = self.sewing_tol

        for tol in tolerances:
            shape, n_free = self._single_pass_sew(faces, tol)

            if shape is None:
                continue

            if n_free < best_free_edges:
                best_shape = shape
                best_free_edges = n_free
                best_tol = tol

            # Perfekt: Keine freien Kanten
            if n_free == 0:
                logger.debug(f"  → Perfektes Sewing bei Tol={tol:.2f}mm")
                break

            # Akzeptabel: Weniger als 5% freie Kanten relativ zur Face-Anzahl
            acceptable_threshold = max(5, len(faces) * 0.05)
            if n_free <= acceptable_threshold:
                logger.debug(f"  → Akzeptables Sewing bei Tol={tol:.2f}mm ({n_free} free edges)")
                break

        if best_shape is not None:
            if best_free_edges > 0:
                logger.warning(f"  Bestes Sewing: Tol={best_tol:.2f}mm mit {best_free_edges} freien Kanten")
            else:
                logger.debug(f"  Sewing erfolgreich bei Tol={best_tol:.2f}mm")

        return best_shape

    def _make_solid(self, shape: 'TopoDS_Shape') -> Optional['TopoDS_Solid']:
        """
        Versucht aus Shape ein Solid zu machen.
        """
        shape_type = shape.ShapeType()

        try:
            # Wenn bereits Solid
            if shape_type == TopAbs_SOLID:
                return TopoDS.Solid_s(shape)

            # Wenn Shell
            if shape_type == TopAbs_SHELL:
                return self._shell_to_solid(TopoDS.Shell_s(shape))

            # Wenn Compound - suche Shells/Solids
            if shape_type == TopAbs_COMPOUND:
                # Erst nach Solids suchen
                explorer = TopExp_Explorer(shape, TopAbs_SOLID)
                if explorer.More():
                    return TopoDS.Solid_s(explorer.Current())

                # Dann nach Shells
                explorer = TopExp_Explorer(shape, TopAbs_SHELL)
                if explorer.More():
                    shell = TopoDS.Shell_s(explorer.Current())
                    return self._shell_to_solid(shell)

            logger.warning(f"Kann Shape-Typ {shape_type} nicht zu Solid konvertieren")
            return None

        except Exception as e:
            logger.error(f"Make Solid fehlgeschlagen: {e}")
            return None

    def _shell_to_solid(self, shell: 'TopoDS_Shell') -> Optional['TopoDS_Solid']:
        """
        Konvertiert Shell zu Solid.
        """
        try:
            # Direkt MakeSolid versuchen
            maker = BRepBuilderAPI_MakeSolid(shell)
            if maker.IsDone():
                logger.debug("  MakeSolid erfolgreich")
                return maker.Solid()

            # Wenn fehlgeschlagen: ShapeFix versuchen
            logger.debug("  MakeSolid fehlgeschlagen, versuche ShapeFix...")

            # Shell reparieren
            shell_fixer = ShapeFix_Shell(shell)
            shell_fixer.Perform()
            fixed_shell = shell_fixer.Shell()

            # Nochmal MakeSolid
            maker = BRepBuilderAPI_MakeSolid(fixed_shell)
            if maker.IsDone():
                logger.debug("  MakeSolid nach ShapeFix_Shell erfolgreich")
                return maker.Solid()

            # ShapeFix_Solid als letzter Versuch
            solid_fixer = ShapeFix_Solid()
            solid_fixer.Init(shell)
            solid_fixer.Perform()

            fixed_solid = solid_fixer.Solid()
            if not fixed_solid.IsNull():
                logger.debug("  ShapeFix_Solid erfolgreich")
                return fixed_solid

            return None

        except Exception as e:
            logger.debug(f"Shell zu Solid fehlgeschlagen: {e}")
            return None

    def _unify_faces(self, shape: 'TopoDS_Shape') -> Optional['TopoDS_Shape']:
        """
        Merged coplanare/co-zylindrische Faces.
        """
        try:
            upgrader = ShapeUpgrade_UnifySameDomain(shape, True, True, True)
            upgrader.SetLinearTolerance(self.unify_linear_tol)
            upgrader.SetAngularTolerance(self.unify_angular_tol)
            upgrader.Build()

            unified = upgrader.Shape()

            if unified.IsNull():
                logger.warning("UnifySameDomain ergab Null-Shape")
                return None

            # Zähle Faces vorher/nachher
            n_before = self._count_faces(shape)
            n_after = self._count_faces(unified)

            if n_after < n_before:
                logger.debug(f"  UnifySameDomain: {n_before} → {n_after} Faces")

            return unified

        except Exception as e:
            logger.warning(f"UnifySameDomain fehlgeschlagen: {e}")
            return None

    def _validate_shape(self, shape: 'TopoDS_Shape') -> tuple:
        """
        Validiert Shape mit BRepCheck_Analyzer.

        Returns:
            (is_valid: bool, message: str)
        """
        try:
            analyzer = BRepCheck_Analyzer(shape)
            is_valid = analyzer.IsValid()

            if is_valid:
                return True, "OK"

            # Fehlerdetails sammeln (vereinfacht)
            return False, "BRepCheck_Analyzer: Invalid"

        except Exception as e:
            return False, f"Validierung fehlgeschlagen: {e}"

    def _return_shell(self, shape: 'TopoDS_Shape', stats: dict) -> ConversionResult:
        """
        Gibt Shell zurück wenn Solid nicht möglich.
        """
        try:
            shape_type = shape.ShapeType()

            if shape_type == TopAbs_SHELL:
                return ConversionResult(
                    status=ConversionStatus.SHELL_ONLY,
                    solid=Shell(TopoDS.Shell_s(shape)),
                    message="Nicht wasserdicht - Shell zurückgegeben",
                    stats=stats
                )

            if shape_type == TopAbs_COMPOUND:
                explorer = TopExp_Explorer(shape, TopAbs_SHELL)
                if explorer.More():
                    return ConversionResult(
                        status=ConversionStatus.SHELL_ONLY,
                        solid=Shell(TopoDS.Shell_s(explorer.Current())),
                        message="Nicht wasserdicht - Shell aus Compound",
                        stats=stats
                    )

            # Fallback: Shape als-is
            return ConversionResult(
                status=ConversionStatus.SHELL_ONLY,
                solid=Shape(shape),
                message="Nicht wasserdicht - Shape zurückgegeben",
                stats=stats
            )

        except Exception as e:
            return ConversionResult(
                status=ConversionStatus.FAILED,
                message=f"Shell-Rückgabe fehlgeschlagen: {e}",
                stats=stats
            )

    def _count_faces(self, shape: 'TopoDS_Shape') -> int:
        """Zählt Faces in einem Shape."""
        count = 0
        explorer = TopExp_Explorer(shape, TopAbs_FACE)
        while explorer.More():
            count += 1
            explorer.Next()
        return count
