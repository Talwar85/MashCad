"""
MashCad - Robuste Kanten-Operationen
Fillet und Chamfer mit Fallback-Strategien

Features:
- Batch-Operation: Alle Kanten gleichzeitig (schnellste Option)
- Iterative Operation: Kanten einzeln bei Fehler
- Automatische Kanten-Auflösung auf modifiziertem Solid
- Detaillierte Fehlerberichte mit klarer Status-Unterscheidung

Result Status:
- SUCCESS: Alle Kanten erfolgreich verarbeitet
- WARNING: Teilweise erfolgreich (Fallback verwendet oder Kanten übersprungen)
- ERROR: Keine Kanten konnten verarbeitet werden
"""

from typing import List, Tuple, Optional
from dataclasses import dataclass, field
from loguru import logger

from modeling.result_types import (
    ResultStatus, FilletChamferResult, OperationResult
)

# ==================== OCP Imports ====================

HAS_OCP = False
try:
    from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet, BRepFilletAPI_MakeChamfer
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE
    from OCP.ShapeFix import ShapeFix_Shape
    HAS_OCP = True
except ImportError:
    logger.warning("OCP nicht verfügbar - Fillet/Chamfer eingeschränkt")

HAS_BUILD123D = False
try:
    from build123d import Solid, Shape, fillet, chamfer, Vector
    HAS_BUILD123D = True
except ImportError:
    logger.warning("build123d nicht verfügbar")


# ==================== Legacy Alias (für Kompatibilität) ====================

@dataclass
class FilletResult:
    """
    Legacy-Ergebnis einer Fillet/Chamfer-Operation.
    Verwende FilletChamferResult für neue Implementierungen.

    Attributes:
        success: True wenn mindestens eine Kante erfolgreich verarbeitet wurde
        solid: Das resultierende build123d Solid (oder None bei totalem Fehler)
        failed_edges: Liste der Edge-IDs die nicht verarbeitet werden konnten
        failed_edge_indices: Indizes im ursprünglichen edges-Array
        message: Beschreibende Nachricht über das Ergebnis
    """
    success: bool
    solid: Optional[object]
    failed_edges: List[int]
    failed_edge_indices: List[int]
    message: str

    @classmethod
    def from_result(cls, result: FilletChamferResult) -> "FilletResult":
        """Konvertiert FilletChamferResult zu Legacy FilletResult."""
        return cls(
            success=result.is_success,
            solid=result.value,
            failed_edges=result.failed_edge_indices,
            failed_edge_indices=result.failed_edge_indices,
            message=result.message
        )


# ==================== Neue API mit Result-Pattern ====================

def apply_robust_fillet_v2(body, edges: List, radius: float) -> FilletChamferResult:
    """
    Wendet Fillet mit automatischer Fallback-Strategie an.
    Verwendet das neue Result-Pattern für klare Status-Unterscheidung.

    Result Status:
    - SUCCESS: Alle Kanten erfolgreich (Batch oder iterativ)
    - WARNING: Teilweise erfolgreich (einige Kanten übersprungen)
    - ERROR: Keine Kanten verarbeitet

    Args:
        body: Body-Objekt mit _build123d_solid
        edges: Liste von build123d Edge-Objekten
        radius: Fillet-Radius in mm

    Returns:
        FilletChamferResult mit klarem Status
    """
    total_edges = len(edges) if edges else 0

    # --- Validierung ---
    if not HAS_OCP:
        return FilletChamferResult(
            status=ResultStatus.ERROR,
            message="OCP nicht verfügbar",
            total_edges=total_edges
        )

    if not edges:
        return FilletChamferResult(
            status=ResultStatus.EMPTY,
            message="Keine Kanten übergeben",
            details={"reason": "Leere Kantenliste"},
            total_edges=0
        )

    if not hasattr(body, '_build123d_solid') or not body._build123d_solid:
        return FilletChamferResult(
            status=ResultStatus.ERROR,
            message="Body hat kein Solid",
            total_edges=total_edges
        )

    solid = body._build123d_solid
    failed_indices = []
    warnings = []

    # ========== STRATEGIE 1: Batch-Operation ==========
    logger.info(f"Fillet: Versuche Batch mit {total_edges} Kanten, r={radius}")

    try:
        result = _try_fillet_batch(solid, edges, radius)
        if result and _validate_solid(result):
            logger.success(f"Fillet Batch erfolgreich: {total_edges} Kanten")
            return FilletChamferResult(
                status=ResultStatus.SUCCESS,
                value=result,
                message=f"Alle {total_edges} Kanten erfolgreich gefillt",
                total_edges=total_edges,
                successful_edges=total_edges
            )
    except Exception as e:
        warnings.append(f"Batch fehlgeschlagen: {str(e)[:50]}")
        logger.debug(f"Batch-Fillet fehlgeschlagen: {e}")

    # ========== STRATEGIE 2: Iterativ mit Fallback ==========
    logger.info("Batch-Fillet fehlgeschlagen, versuche iterativen Ansatz...")
    warnings.append("Fallback auf iterative Verarbeitung")

    current_solid = solid
    successful_count = 0

    for i, edge in enumerate(edges):
        try:
            resolved_edge = _resolve_edge_on_solid(current_solid, edge)

            if resolved_edge is None:
                warnings.append(f"Kante {i}: Nicht auf Solid gefunden")
                failed_indices.append(i)
                continue

            result = _try_fillet_single(current_solid, resolved_edge, radius)

            if result and _validate_solid(result):
                current_solid = result
                successful_count += 1
                logger.debug(f"Kante {i} erfolgreich")
            else:
                failed_indices.append(i)
                warnings.append(f"Kante {i}: Fillet fehlgeschlagen")

        except Exception as e:
            failed_indices.append(i)
            warnings.append(f"Kante {i}: {str(e)[:30]}")

    # ========== Ergebnis zusammenstellen ==========
    if successful_count == total_edges:
        # Alle erfolgreich (nach Fallback)
        return FilletChamferResult(
            status=ResultStatus.WARNING,
            value=current_solid,
            message=f"Alle {total_edges} Kanten erfolgreich (via iterativ)",
            details={"fallback_used": "iterative"},
            warnings=warnings,
            total_edges=total_edges,
            successful_edges=successful_count
        )
    elif successful_count > 0:
        # Teilweise erfolgreich
        return FilletChamferResult(
            status=ResultStatus.WARNING,
            value=current_solid,
            message=f"{successful_count}/{total_edges} Kanten erfolgreich",
            details={"fallback_used": "iterative"},
            warnings=warnings,
            failed_items=[f"edge_{i}" for i in failed_indices],
            total_edges=total_edges,
            successful_edges=successful_count,
            failed_edge_indices=failed_indices
        )
    else:
        # Alle fehlgeschlagen
        return FilletChamferResult(
            status=ResultStatus.ERROR,
            message=f"Alle {total_edges} Kanten fehlgeschlagen",
            warnings=warnings,
            total_edges=total_edges,
            successful_edges=0,
            failed_edge_indices=list(range(total_edges))
        )


def apply_robust_chamfer_v2(body, edges: List, distance: float) -> FilletChamferResult:
    """
    Wendet Chamfer mit automatischer Fallback-Strategie an.
    Verwendet das neue Result-Pattern für klare Status-Unterscheidung.

    Args:
        body: Body-Objekt mit _build123d_solid
        edges: Liste von build123d Edge-Objekten
        distance: Chamfer-Distanz in mm

    Returns:
        FilletChamferResult mit klarem Status
    """
    total_edges = len(edges) if edges else 0

    if not HAS_OCP:
        return FilletChamferResult(
            status=ResultStatus.ERROR,
            message="OCP nicht verfügbar",
            total_edges=total_edges
        )

    if not edges:
        return FilletChamferResult(
            status=ResultStatus.EMPTY,
            message="Keine Kanten übergeben",
            total_edges=0
        )

    if not hasattr(body, '_build123d_solid') or not body._build123d_solid:
        return FilletChamferResult(
            status=ResultStatus.ERROR,
            message="Body hat kein Solid",
            total_edges=total_edges
        )

    solid = body._build123d_solid
    failed_indices = []
    warnings = []

    # ========== STRATEGIE 1: Batch ==========
    logger.info(f"Chamfer: Versuche Batch mit {total_edges} Kanten, d={distance}")

    try:
        result = _try_chamfer_batch(solid, edges, distance)
        if result and _validate_solid(result):
            logger.success(f"Chamfer Batch erfolgreich: {total_edges} Kanten")
            return FilletChamferResult(
                status=ResultStatus.SUCCESS,
                value=result,
                message=f"Alle {total_edges} Kanten erfolgreich gechamfert",
                total_edges=total_edges,
                successful_edges=total_edges
            )
    except Exception as e:
        warnings.append(f"Batch fehlgeschlagen: {str(e)[:50]}")

    # ========== STRATEGIE 2: Iterativ ==========
    logger.info("Batch-Chamfer fehlgeschlagen, versuche iterativen Ansatz...")
    warnings.append("Fallback auf iterative Verarbeitung")

    current_solid = solid
    successful_count = 0

    for i, edge in enumerate(edges):
        try:
            resolved_edge = _resolve_edge_on_solid(current_solid, edge)

            if resolved_edge is None:
                failed_indices.append(i)
                continue

            result = _try_chamfer_single(current_solid, resolved_edge, distance)

            if result and _validate_solid(result):
                current_solid = result
                successful_count += 1
            else:
                failed_indices.append(i)

        except Exception as e:
            failed_indices.append(i)
            warnings.append(f"Kante {i}: {str(e)[:30]}")

    # Ergebnis
    if successful_count == total_edges:
        return FilletChamferResult(
            status=ResultStatus.WARNING,
            value=current_solid,
            message=f"Alle {total_edges} Kanten erfolgreich (via iterativ)",
            details={"fallback_used": "iterative"},
            warnings=warnings,
            total_edges=total_edges,
            successful_edges=successful_count
        )
    elif successful_count > 0:
        return FilletChamferResult(
            status=ResultStatus.WARNING,
            value=current_solid,
            message=f"{successful_count}/{total_edges} Kanten erfolgreich",
            details={"fallback_used": "iterative"},
            warnings=warnings,
            total_edges=total_edges,
            successful_edges=successful_count,
            failed_edge_indices=failed_indices
        )
    else:
        return FilletChamferResult(
            status=ResultStatus.ERROR,
            message=f"Alle {total_edges} Kanten fehlgeschlagen",
            warnings=warnings,
            total_edges=total_edges,
            failed_edge_indices=list(range(total_edges))
        )


# ==================== Legacy API (für Kompatibilität) ====================

def apply_robust_fillet(body, edges: List, radius: float) -> FilletResult:
    """
    Wendet Fillet mit automatischer Fallback-Strategie an.

    Strategie:
    1. Versuche alle Kanten gleichzeitig (schnellste Option wenn es funktioniert)
    2. Bei Fehler: Versuche Kanten einzeln nacheinander
    3. Bei Einzel-Fehler: Überspringe Kante, logge Warnung, fahre fort

    Args:
        body: Body-Objekt mit _build123d_solid
        edges: Liste von build123d Edge-Objekten
        radius: Fillet-Radius in mm

    Returns:
        FilletResult mit Erfolgs-Status, Solid und Liste fehlgeschlagener Kanten
    """
    if not HAS_OCP:
        return FilletResult(False, None, [], [], "OCP nicht verfügbar")

    if not edges:
        return FilletResult(False, None, [], [], "Keine Kanten übergeben")

    if not hasattr(body, '_build123d_solid') or not body._build123d_solid:
        return FilletResult(False, None, [], [], "Body hat kein Solid")

    solid = body._build123d_solid
    failed_edges = []
    failed_indices = []

    # ========== STRATEGIE 1: Alle Kanten gleichzeitig ==========
    logger.info(f"Fillet: Versuche Batch-Operation mit {len(edges)} Kanten, r={radius}")

    try:
        result = _try_fillet_batch(solid, edges, radius)
        if result and _validate_solid(result):
            logger.success(f"Fillet Batch erfolgreich: {len(edges)} Kanten, r={radius}")
            return FilletResult(True, result, [], [], "Erfolg")
    except Exception as e:
        logger.debug(f"Batch-Fillet fehlgeschlagen: {e}")

    # ========== STRATEGIE 2: Kanten einzeln ==========
    logger.info("Batch-Fillet fehlgeschlagen, versuche iterativen Ansatz...")

    current_solid = solid
    successful_count = 0

    for i, edge in enumerate(edges):
        try:
            # Kante auf aktuellem (möglicherweise modifiziertem) Solid auflösen
            resolved_edge = _resolve_edge_on_solid(current_solid, edge)

            if resolved_edge is None:
                logger.warning(f"Kante {i} konnte nicht auf modifiziertem Solid gefunden werden")
                failed_edges.append(i)
                failed_indices.append(i)
                continue

            # Einzel-Fillet versuchen
            result = _try_fillet_single(current_solid, resolved_edge, radius)

            if result and _validate_solid(result):
                current_solid = result
                successful_count += 1
                logger.debug(f"Kante {i} erfolgreich gefillt")
            else:
                failed_edges.append(i)
                failed_indices.append(i)
                logger.warning(f"Fillet für Kante {i} fehlgeschlagen")

        except Exception as e:
            failed_edges.append(i)
            failed_indices.append(i)
            logger.warning(f"Kante {i} Fillet-Fehler: {e}")

    # Ergebnis zusammenstellen
    if successful_count > 0:
        message = f"Teilweise erfolgreich: {successful_count}/{len(edges)} Kanten"
        if failed_edges:
            message += f", {len(failed_edges)} fehlgeschlagen"
        return FilletResult(True, current_solid, failed_edges, failed_indices, message)
    else:
        return FilletResult(False, None, list(range(len(edges))), list(range(len(edges))),
                           "Alle Kanten fehlgeschlagen")


def apply_robust_chamfer(body, edges: List, distance: float) -> FilletResult:
    """
    Wendet Chamfer mit automatischer Fallback-Strategie an.
    Gleiche Strategie wie Fillet.

    Args:
        body: Body-Objekt mit _build123d_solid
        edges: Liste von build123d Edge-Objekten
        distance: Chamfer-Distanz in mm

    Returns:
        FilletResult mit Erfolgs-Status und Details
    """
    if not HAS_OCP:
        return FilletResult(False, None, [], [], "OCP nicht verfügbar")

    if not edges:
        return FilletResult(False, None, [], [], "Keine Kanten übergeben")

    if not hasattr(body, '_build123d_solid') or not body._build123d_solid:
        return FilletResult(False, None, [], [], "Body hat kein Solid")

    solid = body._build123d_solid
    failed_edges = []
    failed_indices = []

    # ========== STRATEGIE 1: Alle Kanten gleichzeitig ==========
    logger.info(f"Chamfer: Versuche Batch-Operation mit {len(edges)} Kanten, d={distance}")

    try:
        result = _try_chamfer_batch(solid, edges, distance)
        if result and _validate_solid(result):
            logger.success(f"Chamfer Batch erfolgreich: {len(edges)} Kanten, d={distance}")
            return FilletResult(True, result, [], [], "Erfolg")
    except Exception as e:
        logger.debug(f"Batch-Chamfer fehlgeschlagen: {e}")

    # ========== STRATEGIE 2: Kanten einzeln ==========
    logger.info("Batch-Chamfer fehlgeschlagen, versuche iterativen Ansatz...")

    current_solid = solid
    successful_count = 0

    for i, edge in enumerate(edges):
        try:
            resolved_edge = _resolve_edge_on_solid(current_solid, edge)

            if resolved_edge is None:
                failed_edges.append(i)
                failed_indices.append(i)
                continue

            result = _try_chamfer_single(current_solid, resolved_edge, distance)

            if result and _validate_solid(result):
                current_solid = result
                successful_count += 1
            else:
                failed_edges.append(i)
                failed_indices.append(i)

        except Exception as e:
            failed_edges.append(i)
            failed_indices.append(i)
            logger.warning(f"Kante {i} Chamfer-Fehler: {e}")

    if successful_count > 0:
        message = f"Teilweise erfolgreich: {successful_count}/{len(edges)} Kanten"
        return FilletResult(True, current_solid, failed_edges, failed_indices, message)
    else:
        return FilletResult(False, None, list(range(len(edges))), list(range(len(edges))),
                           "Alle Kanten fehlgeschlagen")


# ==================== Interne Fillet-Funktionen ====================

def _try_fillet_batch(solid, edges: List, radius: float):
    """
    Versucht Fillet auf alle Kanten gleichzeitig mit OCP.

    Args:
        solid: build123d Solid
        edges: Liste von build123d Edges
        radius: Fillet-Radius

    Returns:
        build123d Solid oder None bei Fehler
    """
    shape = solid.wrapped if hasattr(solid, 'wrapped') else solid
    fillet_op = BRepFilletAPI_MakeFillet(shape)

    for edge in edges:
        edge_shape = edge.wrapped if hasattr(edge, 'wrapped') else edge
        fillet_op.Add(radius, edge_shape)

    fillet_op.Build()

    if not fillet_op.IsDone():
        return None

    result_shape = fillet_op.Shape()

    # Reparatur-Versuch
    result_shape = _fix_shape(result_shape)

    return _wrap_to_build123d(result_shape)


def _try_fillet_single(solid, edge, radius: float):
    """
    Versucht Fillet auf eine einzelne Kante.

    Args:
        solid: build123d Solid
        edge: build123d Edge
        radius: Fillet-Radius

    Returns:
        build123d Solid oder None bei Fehler
    """
    shape = solid.wrapped if hasattr(solid, 'wrapped') else solid
    fillet_op = BRepFilletAPI_MakeFillet(shape)

    edge_shape = edge.wrapped if hasattr(edge, 'wrapped') else edge
    fillet_op.Add(radius, edge_shape)

    fillet_op.Build()

    if not fillet_op.IsDone():
        return None

    result_shape = fillet_op.Shape()
    result_shape = _fix_shape(result_shape)

    return _wrap_to_build123d(result_shape)


# ==================== Interne Chamfer-Funktionen ====================

def _try_chamfer_batch(solid, edges: List, distance: float):
    """
    Versucht Chamfer auf alle Kanten gleichzeitig.
    FIX: Nutzt die einfache Signatur Add(dist, edge) für symmetrische Fasen.
    """
    shape = solid.wrapped if hasattr(solid, 'wrapped') else solid
    chamfer_op = BRepFilletAPI_MakeChamfer(shape)

    added_count = 0
    for edge in edges:
        edge_shape = edge.wrapped if hasattr(edge, 'wrapped') else edge

        try:
            # FIX: Keine Face übergeben! Das verursacht den Signatur-Fehler bei symmetrischen Fasen.
            # OCP/Cascade errechnet die Fasen-Richtung automatisch.
            chamfer_op.Add(distance, edge_shape)
            added_count += 1
        except Exception as e:
            logger.debug(f"Chamfer.Add fehlgeschlagen für Kante: {e}")
            continue

    if added_count == 0:
        return None

    try:
        chamfer_op.Build()

        if not chamfer_op.IsDone():
            logger.debug(f"Chamfer Build fehlgeschlagen")
            return None

        result_shape = chamfer_op.Shape()
        result_shape = _fix_shape(result_shape)

        return _wrap_to_build123d(result_shape)
    except Exception as e:
        logger.debug(f"Chamfer Build Exception: {e}")
        return None


def _try_chamfer_single(solid, edge, distance: float):
    """
    Versucht Chamfer auf eine einzelne Kante.
    FIX: Signatur korrigiert.
    """
    shape = solid.wrapped if hasattr(solid, 'wrapped') else solid
    edge_shape = edge.wrapped if hasattr(edge, 'wrapped') else edge

    chamfer_op = BRepFilletAPI_MakeChamfer(shape)

    try:
        # FIX: Nur Distanz und Edge
        chamfer_op.Add(distance, edge_shape)
        
        chamfer_op.Build()

        if not chamfer_op.IsDone():
            return None

        result_shape = chamfer_op.Shape()
        result_shape = _fix_shape(result_shape)

        return _wrap_to_build123d(result_shape)
    except Exception as e:
        logger.debug(f"Single Chamfer Exception: {e}")
        return None


def _find_face_by_edge_geometry(shape, edge_shape):
    """
    Findet eine Face die eine geometrisch ähnliche Kante enthält.
    Fallback wenn topologische Methoden versagen.

    Args:
        shape: TopoDS_Shape
        edge_shape: TopoDS_Edge

    Returns:
        TopoDS_Face oder None
    """
    try:
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE
        from OCP.BRepAdaptor import BRepAdaptor_Curve

        # Mittelpunkt der Ziel-Kante berechnen
        target_curve = BRepAdaptor_Curve(edge_shape)
        u_mid = (target_curve.FirstParameter() + target_curve.LastParameter()) / 2.0
        target_mid = target_curve.Value(u_mid)

        # Auch Start und End für besseren Match
        target_start = target_curve.Value(target_curve.FirstParameter())
        target_end = target_curve.Value(target_curve.LastParameter())

        tolerance = 0.01  # 0.01mm

        face_explorer = TopExp_Explorer(shape, TopAbs_FACE)
        while face_explorer.More():
            face = face_explorer.Current()
            edge_explorer = TopExp_Explorer(face, TopAbs_EDGE)
            while edge_explorer.More():
                try:
                    cand_edge = edge_explorer.Current()
                    cand_curve = BRepAdaptor_Curve(cand_edge)
                    u_mid_cand = (cand_curve.FirstParameter() + cand_curve.LastParameter()) / 2.0
                    cand_mid = cand_curve.Value(u_mid_cand)

                    # Prüfe Mittelpunkt
                    if target_mid.Distance(cand_mid) < tolerance:
                        # Doppel-Check mit Start/End
                        cand_start = cand_curve.Value(cand_curve.FirstParameter())
                        cand_end = cand_curve.Value(cand_curve.LastParameter())

                        start_match = (target_start.Distance(cand_start) < tolerance or
                                       target_start.Distance(cand_end) < tolerance)
                        end_match = (target_end.Distance(cand_start) < tolerance or
                                     target_end.Distance(cand_end) < tolerance)

                        if start_match and end_match:
                            return face
                except Exception as e:
                    logger.debug(f"[edge_operations.py] Fehler: {e}")
                    pass
                edge_explorer.Next()
            face_explorer.Next()

        return None

    except Exception as e:
        logger.debug(f"Face-by-geometry Suche fehlgeschlagen: {e}")
        return None


def _find_adjacent_face(shape, edge_shape):
    """
    Findet eine an die Kante angrenzende Face.

    Verwendet mehrere Strategien:
    1. TopExp Map (schnell, aber erfordert exakte Topologie)
    2. IsSame-Vergleich (für Kanten aus gleicher Topologie)
    3. Geometrischer Vergleich (für Kanten mit ähnlicher Position)

    Args:
        shape: TopoDS_Shape
        edge_shape: TopoDS_Edge

    Returns:
        TopoDS_Face oder None
    """
    try:
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE
        from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape
        from OCP.TopExp import TopExp
        from OCP.BRepAdaptor import BRepAdaptor_Curve
        from OCP.gp import gp_Pnt

        # Strategie 1: TopExp Map (schnellste Option)
        try:
            edge_face_map = TopTools_IndexedDataMapOfShapeListOfShape()
            TopExp.MapShapesAndAncestors_s(shape, TopAbs_EDGE, TopAbs_FACE, edge_face_map)

            if edge_face_map.Contains(edge_shape):
                face_list = edge_face_map.FindFromKey(edge_shape)
                if face_list.Size() > 0:
                    return face_list.First()
        except Exception as e:
            logger.debug(f"TopExp Map fehlgeschlagen: {e}")

        # Strategie 2: IsSame-Vergleich (für Kanten aus gleicher Topologie)
        face_explorer = TopExp_Explorer(shape, TopAbs_FACE)
        while face_explorer.More():
            face = face_explorer.Current()
            edge_explorer = TopExp_Explorer(face, TopAbs_EDGE)
            while edge_explorer.More():
                if edge_explorer.Current().IsSame(edge_shape):
                    return face
                edge_explorer.Next()
            face_explorer.Next()

        # Strategie 3: Geometrischer Vergleich (für Kanten mit ähnlicher Position)
        # Berechne Mittelpunkt der Ziel-Kante
        try:
            target_curve = BRepAdaptor_Curve(edge_shape)
            u_mid = (target_curve.FirstParameter() + target_curve.LastParameter()) / 2.0
            target_mid = target_curve.Value(u_mid)
            tolerance = 1e-3  # 0.001mm Toleranz

            face_explorer = TopExp_Explorer(shape, TopAbs_FACE)
            while face_explorer.More():
                face = face_explorer.Current()
                edge_explorer = TopExp_Explorer(face, TopAbs_EDGE)
                while edge_explorer.More():
                    try:
                        candidate_curve = BRepAdaptor_Curve(edge_explorer.Current())
                        u_mid_cand = (candidate_curve.FirstParameter() + candidate_curve.LastParameter()) / 2.0
                        cand_mid = candidate_curve.Value(u_mid_cand)

                        dist = target_mid.Distance(cand_mid)
                        if dist < tolerance:
                            logger.debug(f"Face via geometrischen Vergleich gefunden (dist={dist:.6f})")
                            return face
                    except Exception as e:
                        logger.debug(f"[edge_operations.py] Fehler: {e}")
                        pass
                    edge_explorer.Next()
                face_explorer.Next()
        except Exception as e:
            logger.debug(f"Geometrischer Vergleich fehlgeschlagen: {e}")

        return None

    except Exception as e:
        logger.debug(f"Face-Suche komplett fehlgeschlagen: {e}")
        return None


# ==================== Hilfs-Funktionen ====================

def _resolve_edge_on_solid(solid, original_edge) -> Optional[object]:
    """
    Findet die entsprechende Kante auf einem (möglicherweise modifizierten) Solid.

    Verwendet Center-Point Matching (Topological Naming Fallback).

    Args:
        solid: build123d Solid (möglicherweise durch vorherige Operationen modifiziert)
        original_edge: Ursprüngliche build123d Edge

    Returns:
        Entsprechende Edge auf dem Solid oder None
    """
    if not HAS_BUILD123D:
        return None

    try:
        # Original-Mittelpunkt
        original_center = original_edge.center()
        target = Vector(original_center.X, original_center.Y, original_center.Z)

        best_edge = None
        min_dist = float('inf')
        tolerance = 1.0  # mm Toleranz

        for edge in solid.edges():
            try:
                edge_center = edge.center()
                dist = (edge_center - target).length
                if dist < min_dist:
                    min_dist = dist
                    best_edge = edge
            except Exception as e:
                logger.debug(f"[edge_operations.py] Fehler: {e}")
                pass

        if best_edge and min_dist < tolerance:
            return best_edge

        # Fallback: Größere Toleranz
        if best_edge and min_dist < tolerance * 5:
            logger.debug(f"Kante mit größerer Toleranz gefunden: {min_dist:.2f}mm")
            return best_edge

        return None

    except Exception as e:
        logger.debug(f"Kanten-Auflösung fehlgeschlagen: {e}")
        return None


def _validate_solid(solid) -> bool:
    """
    Validiert dass das Solid geometrisch gültig ist.

    Args:
        solid: build123d Solid oder Shape

    Returns:
        True wenn gültig
    """
    if solid is None:
        return False

    try:
        shape = solid.wrapped if hasattr(solid, 'wrapped') else solid
        analyzer = BRepCheck_Analyzer(shape)
        return analyzer.IsValid()
    except Exception as e:
        logger.debug(f"[edge_operations.py] Fehler: {e}")
        # Fallback: Prüfe ob es Faces hat
        try:
            return len(solid.faces()) > 0
        except Exception as e:
            logger.debug(f"[edge_operations.py] Fehler: {e}")
            return False


def _fix_shape(shape):
    """
    Versucht ein Shape zu reparieren.

    Args:
        shape: TopoDS_Shape

    Returns:
        Repariertes Shape
    """
    try:
        fixer = ShapeFix_Shape(shape)
        fixer.Perform()
        return fixer.Shape()
    except Exception as e:
        logger.debug(f"[edge_operations.py] Fehler: {e}")
        return shape


def _wrap_to_build123d(ocp_shape):
    """
    Wrappt ein OCP Shape zurück zu build123d Solid.

    Args:
        ocp_shape: TopoDS_Shape

    Returns:
        build123d Solid oder None
    """
    if not HAS_BUILD123D:
        return None

    try:
        try:
            return Solid(ocp_shape)
        except Exception as e:
            logger.debug(f"[edge_operations.py] Fehler: {e}")
            return Shape(ocp_shape)
    except Exception as e:
        logger.error(f"Wrap zu build123d fehlgeschlagen: {e}")
        return None


# ==================== Utility-Funktionen ====================

def get_edge_info(edge) -> dict:
    """
    Gibt Debug-Informationen über eine Kante zurück.

    Args:
        edge: build123d Edge

    Returns:
        Dict mit Kanten-Informationen
    """
    info = {
        "type": "unknown",
        "length": 0.0,
        "center": (0, 0, 0),
        "start": (0, 0, 0),
        "end": (0, 0, 0),
    }

    try:
        from build123d import GeomType

        info["length"] = edge.length

        center = edge.center()
        info["center"] = (center.X, center.Y, center.Z)

        start = edge.position_at(0)
        info["start"] = (start.X, start.Y, start.Z)

        end = edge.position_at(1)
        info["end"] = (end.X, end.Y, end.Z)

        geom_type = edge.geom_type()
        if geom_type == GeomType.LINE:
            info["type"] = "linear"
        elif geom_type == GeomType.CIRCLE:
            info["type"] = "circular"
        else:
            info["type"] = "curve"

    except Exception as e:
        logger.debug(f"Edge-Info Fehler: {e}")

    return info


def estimate_max_fillet_radius(edges: List) -> float:
    """
    Schätzt den maximalen sicheren Fillet-Radius für eine Kantenliste.

    Faustregel: max ~40% der kürzesten Kantenlänge

    Args:
        edges: Liste von build123d Edges

    Returns:
        Geschätzter maximaler Radius in mm
    """
    if not edges:
        return 10.0  # Default

    min_length = float('inf')

    for edge in edges:
        try:
            length = edge.length
            if length < min_length:
                min_length = length
        except Exception as e:
            logger.debug(f"[edge_operations.py] Fehler: {e}")
            pass

    if min_length == float('inf'):
        return 10.0

    return max(0.5, min_length * 0.4)
