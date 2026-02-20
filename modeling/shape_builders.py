"""
MashCAD Shape Builders

Profile and shape building utilities extracted from modeling/__init__.py.
These functions handle profile conversion, filtering, and wire/face building.

AR-002: Phase 1 Split - Extracted for maintainability.
"""

import math
from typing import List, Optional, Tuple, Any, Union, Dict
from loguru import logger

from config.feature_flags import is_enabled


def convert_legacy_nsided_edge_selectors(edge_selectors: Optional[List]) -> List[dict]:
    """
    Konvertiert legacy NSided edge_selectors zu GeometricEdgeSelector-Dicts.

    Altes Format:
    - (cx, cy, cz)
    - ((cx, cy, cz), (dx, dy, dz))

    Args:
        edge_selectors: List of legacy selector tuples

    Returns:
        List of GeometricEdgeSelector-compatible dicts
    """
    if not edge_selectors:
        return []

    def _as_vec3(value):
        if not isinstance(value, (list, tuple)) or len(value) < 3:
            return None
        try:
            return [float(value[0]), float(value[1]), float(value[2])]
        except Exception:
            return None

    migrated = []
    for selector in edge_selectors:
        center = None
        direction = None

        if isinstance(selector, (list, tuple)):
            if len(selector) == 2 and isinstance(selector[0], (list, tuple)):
                center = _as_vec3(selector[0])
                direction = _as_vec3(selector[1])
            else:
                center = _as_vec3(selector)

        if center is None:
            continue

        if direction is None or abs(direction[0]) + abs(direction[1]) + abs(direction[2]) < 1e-12:
            direction = [1.0, 0.0, 0.0]

        migrated.append({
            "center": center,
            "direction": direction,
            "length": 0.0,
            "curve_type": "unknown",
            "tolerance": 25.0,
        })

    return migrated


def convert_legacy_edge_selectors(edge_selectors: Optional[List]) -> List[dict]:
    """
    Konvertiert legacy Fillet/Chamfer edge_selectors zu GeometricEdgeSelector-Dicts.

    Altes Format:
    - (cx, cy, cz)

    Args:
        edge_selectors: List of legacy selector tuples

    Returns:
        List of GeometricEdgeSelector-compatible dicts
    """
    if not edge_selectors:
        return []

    migrated = []
    for selector in edge_selectors:
        if not isinstance(selector, (list, tuple)) or len(selector) < 3:
            continue
        try:
            center = [float(selector[0]), float(selector[1]), float(selector[2])]
        except Exception:
            continue

        migrated.append({
            "center": center,
            "direction": [1.0, 0.0, 0.0],
            "length": 0.0,
            "curve_type": "unknown",
            "tolerance": 25.0,
        })

    return migrated


def convert_line_profiles_to_polygons(line_profiles: list) -> list:
    """
    Konvertiert Profile zu Shapely Polygons fuer Legacy-Code.

    Unterstuetzt folgende Formate:
    1. List[Line2D] - vom Sketch _find_closed_profiles()
    2. ShapelyPolygon - bereits vom UI vorkonvertiert
    3. Dict {'type': 'ellipse', 'geometry': Ellipse2D} - native Ellipse Profile (TNP v4.1)
    4. Dict {'type': 'circle', 'geometry': Circle2D} - native Circle Profile (TNP v4.1)

    Args:
        line_profiles: Liste von Profilen (List[Line2D], ShapelyPolygon, oder Dict)

    Returns:
        Liste von Shapely Polygon Objekten und/oder Dict-Profilen (native)
    """
    from shapely.geometry import Polygon as ShapelyPoly

    polygons = []
    for profile in line_profiles:
        if not profile:
            continue

        # Fall 0: Native Ellipse/Circle/Slot Profile (TNP v4.1) - direkt weiterleiten
        if isinstance(profile, dict):
            profile_type = profile.get('type')
            if profile_type in ('ellipse', 'circle', 'slot'):
                # Native Profile werden nicht konvertiert, sondern direkt verwendet
                polygons.append(profile)
                continue

        # Fall 1: Bereits ein Shapely Polygon (vom UI)
        if hasattr(profile, 'exterior') and hasattr(profile, 'area'):
            if profile.is_valid and profile.area > 0:
                polygons.append(profile)
            continue

        # Fall 2: List[Line2D] - vom Sketch _find_closed_profiles()
        coords = []
        try:
            for line in profile:
                if hasattr(line, 'start') and hasattr(line.start, 'x'):
                    coords.append((line.start.x, line.start.y))
                elif isinstance(line, tuple) and len(line) == 2:
                    coords.append(line)
        except Exception:
            continue

        # Shapely Polygon erstellen
        if len(coords) >= 3:
            try:
                poly = ShapelyPoly(coords)
                if poly.is_valid and poly.area > 0:
                    polygons.append(poly)
                else:
                    logger.warning(f"[PROFILE] Ungueltiges/degeneriertes Polygon mit {len(coords)} Punkten")
            except Exception as e:
                logger.warning(f"[PROFILE] Polygon-Erstellung fehlgeschlagen: {e}")

    return polygons


def filter_profiles_by_selector(profiles: list, selector: list, tolerance: float = 5.0) -> list:
    """
    CAD Kernel First: Filtert Profile anhand ihrer Centroids.

    Der Selektor enthaelt Centroids [(cx, cy), ...] der urspruenglich gewaehlten Profile.
    Bei Sketch-Aenderungen koennen Profile sich verschieben - wir matchen mit Toleranz.

    WICHTIG: Fuer jeden Selektor wird nur das BESTE Match (kleinste Distanz) verwendet!
    Das verhindert dass bei ueberlappenden Toleranzbereichen mehrere Profile gematcht werden.

    FAIL-FAST: Wenn kein Match gefunden wird, geben wir eine LEERE Liste zurueck,
    NICHT alle Profile! Das ist CAD Kernel First konform.

    Args:
        profiles: Liste von Shapely Polygons oder Dict-Profilen (Ellipse/Circle)
        selector: Liste von (cx, cy) Tupeln (gespeicherte Centroids)
        tolerance: Abstand-Toleranz fuer Centroid-Match in mm

    Returns:
        Gefilterte Liste von Profilen die zum Selektor passen (kann leer sein!)
    """
    if not profiles or not selector:
        return list(profiles) if profiles else []

    matched = []
    used_profile_indices = set()  # Verhindert doppeltes Matchen

    # Hilfsfunktion: Centroid aus Profil ermitteln
    def get_profile_centroid(profile):
        """Ermittelt den Centroid eines Profils (Shapely oder Dict)."""
        if isinstance(profile, dict):
            # Native Ellipse/Circle Profil
            geometry = profile.get('geometry')
            if geometry:
                if hasattr(geometry, 'center'):
                    # Ellipse2D oder Circle2D
                    return geometry.center.x, geometry.center.y
        # Shapely Polygon
        if hasattr(profile, 'centroid'):
            c = profile.centroid
            return c.x, c.y
        return None

    # Debug: Zeige alle verfuegbaren Profile
    if is_enabled("extrude_debug"):
        logger.debug(f"[SELECTOR] {len(profiles)} Profile verfuegbar, {len(selector)} Selektoren")
    for i, profile in enumerate(profiles):
        try:
            centroid = get_profile_centroid(profile)
            if centroid:
                cx, cy = centroid
                if hasattr(profile, 'area'):
                    logger.debug(f"  Profile {i}: centroid=({cx:.2f}, {cy:.2f}), area={profile.area:.1f}")
                else:
                    logger.debug(f"  Profile {i}: centroid=({cx:.2f}, {cy:.2f}) [native]")
        except Exception as e:
            logger.debug(f"[shape_builders] Fehler: {e}")
            pass

    if is_enabled("extrude_debug"):
        logger.debug(f"[SELECTOR] Selektoren: {selector}")

    # Fuer JEDEN Selektor das BESTE Match finden (nicht alle innerhalb Toleranz!)
    for sel_cx, sel_cy in selector:
        best_match_idx = None
        best_match_dist = float('inf')

        for i, profile in enumerate(profiles):
            if i in used_profile_indices:
                continue  # Bereits verwendet

            try:
                centroid = get_profile_centroid(profile)
                if centroid is None:
                    continue
                cx, cy = centroid
                dist = math.hypot(cx - sel_cx, cy - sel_cy)

                # Nur innerhalb Toleranz UND besser als bisheriges Match
                if dist < tolerance and dist < best_match_dist:
                    best_match_idx = i
                    best_match_dist = dist
            except Exception as e:
                logger.warning(f"Centroid-Berechnung fehlgeschlagen: {e}")
                continue

        # Bestes Match fuer diesen Selektor hinzufuegen
        if best_match_idx is not None:
            matched.append(profiles[best_match_idx])
            used_profile_indices.add(best_match_idx)
            centroid = get_profile_centroid(profiles[best_match_idx])
            if centroid and is_enabled("extrude_debug"):
                logger.debug(f"[SELECTOR] BEST MATCH: ({centroid[0]:.2f}, {centroid[1]:.2f}) ~= ({sel_cx:.2f}, {sel_cy:.2f}), dist={best_match_dist:.2f}")
        else:
            if is_enabled("extrude_debug"):
                logger.warning(f"[SELECTOR] NO MATCH for selector ({sel_cx:.2f}, {sel_cy:.2f})")

    # FAIL-FAST: Kein Fallback auf alle Profile!
    if not matched:
        if is_enabled("extrude_debug"):
            logger.warning(f"[SELECTOR] Kein Profil-Match! Selector passt zu keinem der {len(profiles)} Profile.")

    return matched


def get_plane_from_sketch(sketch) -> 'Plane':
    """
    Extrahiert eine Plane aus einem Sketch-Objekt.

    Args:
        sketch: Sketch object with plane attributes

    Returns:
        build123d Plane object
    """
    from build123d import Plane
    
    origin = getattr(sketch, 'plane_origin', (0, 0, 0))
    normal = getattr(sketch, 'plane_normal', (0, 0, 1))
    x_dir = getattr(sketch, 'plane_x_dir', None)
    if x_dir:
        return Plane(origin=origin, x_dir=x_dir, z_dir=normal)
    return Plane(origin=origin, z_dir=normal)


def lookup_geometry_for_polygon(poly, sketch) -> Optional[List]:
    """
    Looks up the original geometry list for a polygon from the sketch's mapping.

    Args:
        poly: Shapely Polygon
        sketch: Sketch object that may have _profile_geometry_map

    Returns:
        List of (geom_type, geom_obj) or None if not found
    """
    if not hasattr(sketch, '_profile_geometry_map'):
        return None

    # Create lookup key from polygon bounds + area
    bounds = poly.bounds
    key = (round(bounds[0], 2), round(bounds[1], 2),
           round(bounds[2], 2), round(bounds[3], 2),
           round(poly.area, 2))

    geometry_list = sketch._profile_geometry_map.get(key)
    if geometry_list:
        logger.debug(f"  -> Found geometry mapping for polygon: {len(geometry_list)} segments")
        return geometry_list

    # Fuzzy matching if exact key not found
    for map_key, geom_list in sketch._profile_geometry_map.items():
        if (abs(map_key[4] - key[4]) < 0.5 and  # Area within 0.5
            abs(map_key[0] - key[0]) < 1 and
            abs(map_key[1] - key[1]) < 1):
            logger.debug(f"  -> Found geometry mapping (fuzzy): {len(geom_list)} segments")
            return geom_list

    return None


def make_wire_from_mixed_geometry(outer_coords, plane, sketch) -> Optional['Wire']:
    """
    Creates a Wire from mixed geometry (lines, arcs, ellipses) preserving native curves.

    This function attempts to build a wire using the original geometry from the sketch
    rather than just polygon approximation.

    Args:
        outer_coords: List of (x, y) coordinates
        plane: build123d Plane for 3D conversion
        sketch: Sketch object with geometry mapping

    Returns:
        build123d Wire or None if construction fails
    """
    from build123d import Wire, Edge, Arc, Line
    
    try:
        # Try to get original geometry mapping
        geometry_list = lookup_geometry_for_polygon(
            type('Poly', (), {
                'bounds': lambda: (
                    min(c[0] for c in outer_coords),
                    min(c[1] for c in outer_coords),
                    max(c[0] for c in outer_coords),
                    max(c[1] for c in outer_coords)
                ),
                'area': abs(
                    sum(outer_coords[i][0] * outer_coords[(i + 1) % len(outer_coords)][1] -
                        outer_coords[(i + 1) % len(outer_coords)][0] * outer_coords[i][1]
                        for i in range(len(outer_coords))) / 2
                )
            })(),
            sketch
        )

        if geometry_list:
            logger.info(f"  -> Mixed Geometry: {len(geometry_list)} Segmente gefunden")
            edges = []
            for geom_type, geom_obj in geometry_list:
                try:
                    if geom_type == 'line':
                        # Line2D
                        start_3d = plane.from_local_coords((geom_obj.start.x, geom_obj.start.y))
                        end_3d = plane.from_local_coords((geom_obj.end.x, geom_obj.end.y))
                        edge = Edge.make_line(
                            (start_3d[0], start_3d[1], start_3d[2]),
                            (end_3d[0], end_3d[1], end_3d[2])
                        )
                        edges.append(edge)
                        logger.debug(f"    Line: ({geom_obj.start.x:.1f}, {geom_obj.start.y:.1f}) -> ({geom_obj.end.x:.1f}, {geom_obj.end.y:.1f})")

                    elif geom_type == 'arc':
                        # Arc2D
                        center_3d = plane.from_local_coords((geom_obj.center.x, geom_obj.center.y))
                        start_3d = plane.from_local_coords((geom_obj.start.x, geom_obj.start.y))
                        end_3d = plane.from_local_coords((geom_obj.end.x, geom_obj.end.y))
                        # Arc via build123d
                        from build123d import Vector
                        arc = Arc(
                            Vector(*start_3d),
                            Vector(*center_3d),
                            Vector(*end_3d)
                        )
                        edges.append(Edge(arc))
                        logger.debug(f"    Arc: center=({geom_obj.center.x:.1f}, {geom_obj.center.y:.1f})")

                    elif geom_type == 'ellipse':
                        # Ellipse2D - als NURBS approximieren oder als Edge
                        # Fuer jetzt: Sample-Punkte als Polyline
                        logger.debug(f"    Ellipse: center=({geom_obj.center.x:.1f}, {geom_obj.center.y:.1f})")
                        # TODO: Native Ellipse-Unterstuetzung

                except Exception as e:
                    logger.warning(f"    Segment-Konvertierung fehlgeschlagen: {e}")
                    continue

            if edges:
                # Versuche Wire aus Edges zu bauen
                try:
                    wire = Wire(edges)
                    if wire.is_closed:
                        logger.info(f"  -> Mixed Geometry Wire: {len(edges)} edges, geschlossen")
                        return wire
                    else:
                        logger.debug(f"  -> Wire nicht geschlossen, versuche Polygon-Fallback")
                except Exception as e:
                    logger.debug(f"  -> Wire aus Edges fehlgeschlagen: {e}")

        # Fallback: Wenn Wire nicht geschlossen ist, nutze Polygon mit nativen Kurven
        # wo moeglich, aber fuelle Luecken mit Linien
        logger.debug("  -> Fallback: Erstelle Wire aus Polygon-Koordinaten")
        poly_pts = [plane.from_local_coords((p[0], p[1])) for p in outer_coords]
        try:
            wire = Wire.make_polygon(poly_pts)
            logger.info(f"  -> Polygon Wire Fallback: {len(poly_pts)} Punkte")
            return wire
        except Exception as e:
            logger.warning(f"  -> Polygon Wire auch fehlgeschlagen: {e}")
            return None

    except Exception as e:
        logger.warning(f"Wire aus Mixed Geometry fehlgeschlagen: {e}")
        import traceback
        traceback.print_exc()
        return None


# =============================================================================
# Legacy Aliases for Backward Compatibility
# =============================================================================

_convert_legacy_nsided_edge_selectors = convert_legacy_nsided_edge_selectors
_convert_legacy_edge_selectors = convert_legacy_edge_selectors
_convert_line_profiles_to_polygons = convert_line_profiles_to_polygons
_filter_profiles_by_selector = filter_profiles_by_selector
_get_plane_from_sketch = get_plane_from_sketch
_lookup_geometry_for_polygon = lookup_geometry_for_polygon
_make_wire_from_mixed_geometry = make_wire_from_mixed_geometry
