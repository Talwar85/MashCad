"""
MashCad - Geometry Healer
=========================

Phase 7: Kernel-Robustheit

Auto-Healing für problematische importierte oder berechnete Geometrie.
Versucht verschiedene Reparatur-Strategien und meldet Erfolg/Misserfolg.

Healing-Strategien:
1. ShapeFix_Shape - Allgemeine Topologie-Reparatur
2. ShapeFix_Solid - Solid-spezifische Reparatur
3. Sewing - Zusammennähen offener Kanten
4. Tolerance Upgrade - Toleranz erhöhen bei kleinen Lücken

Verwendung:
    from modeling.geometry_healer import GeometryHealer

    # Automatisches Healing
    healed_solid, result = GeometryHealer.heal_solid(solid)

    # Mit spezifischer Strategie
    healed, result = GeometryHealer.heal_with_sewing(solid)

Author: Claude (Phase 7 Kernel-Robustheit)
Date: 2026-01-23
"""

from dataclasses import dataclass, field
from typing import Optional, Tuple, Any, List
from enum import Enum, auto
from loguru import logger

from config.tolerances import Tolerances
from .geometry_validator import GeometryValidator, ValidationResult, ValidationLevel


class HealingStrategy(Enum):
    """Verfügbare Healing-Strategien."""
    SHAPE_FIX = auto()      # ShapeFix_Shape
    SOLID_FIX = auto()      # ShapeFix_Solid
    SEWING = auto()         # BRepBuilderAPI_Sewing
    TOLERANCE = auto()      # Toleranz erhöhen
    COMBINED = auto()       # Alle Strategien kombiniert


@dataclass
class HealingResult:
    """
    Ergebnis eines Healing-Versuchs.

    Attributes:
        success: True wenn Healing erfolgreich
        solid: Geheiltes Solid (oder Original bei Fehler)
        strategy_used: Welche Strategie erfolgreich war
        message: Beschreibung des Ergebnisses
        changes_made: Liste der durchgeführten Änderungen
    """
    success: bool
    solid: Any
    strategy_used: Optional[HealingStrategy]
    message: str
    changes_made: List[str] = field(default_factory=list)

    @classmethod
    def healed(cls, solid, strategy: HealingStrategy, changes: List[str]) -> 'HealingResult':
        """Factory für erfolgreiches Healing."""
        return cls(
            success=True,
            solid=solid,
            strategy_used=strategy,
            message=f"Healing erfolgreich mit {strategy.name}",
            changes_made=changes
        )

    @classmethod
    def unchanged(cls, solid, reason: str) -> 'HealingResult':
        """Factory wenn kein Healing nötig war."""
        return cls(
            success=True,
            solid=solid,
            strategy_used=None,
            message=reason,
            changes_made=[]
        )

    @classmethod
    def failed(cls, solid, reason: str) -> 'HealingResult':
        """Factory für fehlgeschlagenes Healing."""
        return cls(
            success=False,
            solid=solid,
            strategy_used=None,
            message=f"Healing fehlgeschlagen: {reason}",
            changes_made=[]
        )


class GeometryHealer:
    """
    Repariert problematische OCP/Build123d Geometrie.

    Versucht verschiedene Strategien um ungültige Shapes zu reparieren.
    """

    @staticmethod
    def heal_solid(solid, strategy: HealingStrategy = HealingStrategy.COMBINED) -> Tuple[Any, HealingResult]:
        """
        Versucht ein Solid zu heilen.

        Args:
            solid: Build123d Solid
            strategy: Healing-Strategie (default: COMBINED = alle probieren)

        Returns:
            Tuple[healed_solid, HealingResult]
        """
        if solid is None:
            return None, HealingResult.failed(None, "Solid ist None")

        # Erst prüfen ob Healing überhaupt nötig ist
        validation = GeometryValidator.validate_solid(solid, ValidationLevel.NORMAL)

        if validation.is_valid and not validation.issues:
            return solid, HealingResult.unchanged(solid, "Solid ist bereits valide")

        logger.info(f"🔧 Starte Healing für Solid (Validierung: {validation.message})")

        if strategy == HealingStrategy.COMBINED:
            # Alle Strategien der Reihe nach probieren
            strategies = [
                HealingStrategy.SHAPE_FIX,
                HealingStrategy.SOLID_FIX,
                HealingStrategy.SEWING,
                HealingStrategy.TOLERANCE
            ]

            for strat in strategies:
                healed, result = GeometryHealer._apply_strategy(solid, strat)

                if result.success and result.changes_made:
                    # Validieren
                    new_validation = GeometryValidator.validate_solid(healed, ValidationLevel.NORMAL)

                    if new_validation.is_valid:
                        logger.success(f"✅ Healing erfolgreich mit {strat.name}")
                        return healed, result

                    # Strategie hat zwar Änderungen gemacht, aber Ergebnis ist noch ungültig
                    logger.warning(f"⚠️ {strat.name} hat Änderungen gemacht, aber Solid noch ungültig")
                    solid = healed  # Trotzdem weitermachen mit verbessertem Solid

            # Keine Strategie war vollständig erfolgreich
            final_validation = GeometryValidator.validate_solid(solid, ValidationLevel.NORMAL)

            if final_validation.is_valid:
                return solid, HealingResult.healed(
                    solid,
                    HealingStrategy.COMBINED,
                    ["Kombinierte Strategien angewendet"]
                )
            else:
                return solid, HealingResult.failed(
                    solid,
                    f"Alle Strategien probiert, Solid bleibt problematisch: {final_validation.message}"
                )

        else:
            # Einzelne Strategie anwenden
            return GeometryHealer._apply_strategy(solid, strategy)

    @staticmethod
    def _apply_strategy(solid, strategy: HealingStrategy) -> Tuple[Any, HealingResult]:
        """Wendet eine einzelne Healing-Strategie an."""

        if strategy == HealingStrategy.SHAPE_FIX:
            return GeometryHealer._heal_with_shape_fix(solid)

        elif strategy == HealingStrategy.SOLID_FIX:
            return GeometryHealer._heal_with_solid_fix(solid)

        elif strategy == HealingStrategy.SEWING:
            return GeometryHealer._heal_with_sewing(solid)

        elif strategy == HealingStrategy.TOLERANCE:
            return GeometryHealer._heal_with_tolerance_upgrade(solid)

        else:
            return solid, HealingResult.failed(solid, f"Unbekannte Strategie: {strategy}")

    @staticmethod
    def _heal_with_shape_fix(solid) -> Tuple[Any, HealingResult]:
        """
        ShapeFix_Shape - Allgemeine Topologie-Reparatur.

        Repariert:
        - Fehlende Vertices
        - Offene Wires
        - Selbstüberschneidungen
        """
        try:
            from OCP.ShapeFix import ShapeFix_Shape

            fixer = ShapeFix_Shape(solid.wrapped)
            fixer.SetPrecision(Tolerances.KERNEL_FUZZY)
            fixer.SetMaxTolerance(Tolerances.KERNEL_FUZZY * 10)
            fixer.SetMinTolerance(Tolerances.KERNEL_FUZZY / 10)

            # Alle Fixes aktivieren
            fixer.FixSolidTool().SetFixShellMode(True)
            fixer.FixShellTool().SetFixFaceMode(True)

            performed = fixer.Perform()

            if performed:
                fixed_shape = fixer.Shape()

                # Zu Build123d Solid konvertieren
                from build123d import Solid
                healed_solid = Solid(fixed_shape)

                changes = []
                # Status abfragen
                try:
                    from OCP.ShapeExtend import ShapeExtend_OK, ShapeExtend_DONE
                    if fixer.Status(ShapeExtend_DONE):
                        changes.append("ShapeFix hat Änderungen vorgenommen")
                except:
                    changes.append("ShapeFix angewendet")

                if changes:
                    return healed_solid, HealingResult.healed(healed_solid, HealingStrategy.SHAPE_FIX, changes)
                else:
                    return solid, HealingResult.unchanged(solid, "ShapeFix: Keine Änderungen nötig")

            return solid, HealingResult.unchanged(solid, "ShapeFix: Keine Änderungen")

        except Exception as e:
            logger.warning(f"ShapeFix fehlgeschlagen: {e}")
            return solid, HealingResult.failed(solid, str(e))

    @staticmethod
    def _heal_with_solid_fix(solid) -> Tuple[Any, HealingResult]:
        """
        ShapeFix_Solid - Solid-spezifische Reparatur.

        Repariert:
        - Shell-Orientierung
        - Fehlende Shells
        - Shell-Verbindungen
        """
        try:
            from OCP.ShapeFix import ShapeFix_Solid
            from OCP.TopoDS import TopoDS

            # Erst zu Solid casten
            topo_solid = TopoDS.Solid_s(solid.wrapped)

            fixer = ShapeFix_Solid(topo_solid)
            fixer.SetPrecision(Tolerances.KERNEL_FUZZY)

            performed = fixer.Perform()

            if performed:
                fixed_solid = fixer.Solid()

                from build123d import Solid
                healed_solid = Solid(fixed_solid)

                return healed_solid, HealingResult.healed(
                    healed_solid,
                    HealingStrategy.SOLID_FIX,
                    ["SolidFix: Shell-Reparatur durchgeführt"]
                )

            return solid, HealingResult.unchanged(solid, "SolidFix: Keine Änderungen nötig")

        except Exception as e:
            logger.warning(f"SolidFix fehlgeschlagen: {e}")
            return solid, HealingResult.failed(solid, str(e))

    @staticmethod
    def _heal_with_sewing(solid) -> Tuple[Any, HealingResult]:
        """
        BRepBuilderAPI_Sewing - Zusammennähen offener Kanten.

        Repariert:
        - Offene Shells
        - Nicht verbundene Flächen
        - Kleine Lücken zwischen Flächen
        """
        try:
            from OCP.BRepBuilderAPI import BRepBuilderAPI_Sewing
            from OCP.TopExp import TopExp_Explorer
            from OCP.TopAbs import TopAbs_FACE

            sewer = BRepBuilderAPI_Sewing(Tolerances.KERNEL_FUZZY)

            # Alle Faces zum Sewing hinzufügen
            explorer = TopExp_Explorer(solid.wrapped, TopAbs_FACE)
            face_count = 0

            while explorer.More():
                sewer.Add(explorer.Current())
                face_count += 1
                explorer.Next()

            if face_count == 0:
                return solid, HealingResult.unchanged(solid, "Sewing: Keine Faces zum Nähen")

            sewer.Perform()

            sewn_shape = sewer.SewedShape()

            if sewn_shape.IsNull():
                return solid, HealingResult.failed(solid, "Sewing: Ergebnis ist Null")

            # Zu Solid konvertieren
            from build123d import Solid
            from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeSolid
            from OCP.TopoDS import TopoDS

            try:
                # Versuche Shell zu Solid zu machen
                shell = TopoDS.Shell_s(sewn_shape)
                maker = BRepBuilderAPI_MakeSolid(shell)

                if maker.IsDone():
                    healed_solid = Solid(maker.Solid())

                    n_free_edges = sewer.NbFreeEdges()
                    n_contiguous = sewer.NbContigousEdges()

                    changes = [f"Sewing: {face_count} Faces verarbeitet"]
                    if n_free_edges > 0:
                        changes.append(f"{n_free_edges} freie Kanten verbleiben")

                    return healed_solid, HealingResult.healed(healed_solid, HealingStrategy.SEWING, changes)

            except:
                pass

            # Fallback: Direkt als Solid verwenden
            try:
                healed_solid = Solid(sewn_shape)
                return healed_solid, HealingResult.healed(
                    healed_solid,
                    HealingStrategy.SEWING,
                    [f"Sewing: {face_count} Faces zusammengenäht"]
                )
            except:
                pass

            return solid, HealingResult.failed(solid, "Sewing: Konvertierung zu Solid fehlgeschlagen")

        except Exception as e:
            logger.warning(f"Sewing fehlgeschlagen: {e}")
            return solid, HealingResult.failed(solid, str(e))

    @staticmethod
    def _heal_with_tolerance_upgrade(solid) -> Tuple[Any, HealingResult]:
        """
        Toleranz erhöhen - Für kleine Lücken und Ungenauigkeiten.

        Erhöht die Toleranz aller Vertices/Edges/Faces um kleine Lücken zu schließen.
        """
        try:
            from OCP.ShapeFix import ShapeFix_ShapeTolerance

            fixer = ShapeFix_ShapeTolerance()

            # Toleranz auf alle Shape-Elemente anwenden
            new_tolerance = Tolerances.KERNEL_FUZZY * 2

            fixer.SetTolerance(solid.wrapped, new_tolerance)

            # Das Original-Shape wird in-place modifiziert
            # Wir müssen ein neues Build123d Solid erstellen
            from build123d import Solid

            healed_solid = Solid(solid.wrapped)

            return healed_solid, HealingResult.healed(
                healed_solid,
                HealingStrategy.TOLERANCE,
                [f"Toleranz erhöht auf {new_tolerance}"]
            )

        except Exception as e:
            logger.warning(f"Tolerance Upgrade fehlgeschlagen: {e}")
            return solid, HealingResult.failed(solid, str(e))

    @staticmethod
    def heal_imported_mesh(mesh_solid, source_format: str = "unknown") -> Tuple[Any, HealingResult]:
        """
        Spezielles Healing für aus Mesh konvertierte Solids.

        Diese haben oft:
        - Viele kleine Faces
        - Nicht-manifold Kanten
        - T-Vertices

        Args:
            mesh_solid: Build123d Solid (aus Mesh konvertiert)
            source_format: "stl", "obj", etc. für format-spezifisches Healing

        Returns:
            Tuple[healed_solid, HealingResult]
        """
        logger.info(f"🔧 Healing importiertes Mesh (Format: {source_format})")

        # Kombiniertes Healing mit erhöhter Toleranz
        changes = []

        # 1. Zuerst Sewing versuchen (häufig bei Meshes nötig)
        healed, result = GeometryHealer._heal_with_sewing(mesh_solid)
        if result.changes_made:
            changes.extend(result.changes_made)
            mesh_solid = healed

        # 2. Dann ShapeFix
        healed, result = GeometryHealer._heal_with_shape_fix(mesh_solid)
        if result.changes_made:
            changes.extend(result.changes_made)
            mesh_solid = healed

        # 3. Solid-Fix
        healed, result = GeometryHealer._heal_with_solid_fix(mesh_solid)
        if result.changes_made:
            changes.extend(result.changes_made)
            mesh_solid = healed

        # Validieren
        validation = GeometryValidator.validate_solid(mesh_solid, ValidationLevel.NORMAL)

        if validation.is_valid:
            return mesh_solid, HealingResult.healed(
                mesh_solid,
                HealingStrategy.COMBINED,
                changes if changes else ["Mesh-Import validiert"]
            )
        else:
            return mesh_solid, HealingResult.failed(
                mesh_solid,
                f"Mesh-Healing unvollständig: {validation.message}"
            )


# Convenience-Funktionen
def heal_solid(solid) -> Tuple[Any, HealingResult]:
    """Shortcut für GeometryHealer.heal_solid()"""
    return GeometryHealer.heal_solid(solid)


def auto_heal(solid) -> Any:
    """
    Automatisches Healing - gibt geheiltes Solid zurück oder Original bei Fehler.

    Convenience-Funktion für einfache Anwendungsfälle.
    """
    healed, result = GeometryHealer.heal_solid(solid)

    if result.success:
        if result.changes_made:
            logger.info(f"Auto-Heal: {', '.join(result.changes_made)}")
        return healed
    else:
        logger.warning(f"Auto-Heal fehlgeschlagen: {result.message}")
        return solid
