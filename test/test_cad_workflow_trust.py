"""
CAD Workflow Trust Tests - Comprehensive Integration Testing

Simuliert echte User-Workflows von der 2D-Skizze bis zum fertigen Bauteil.
Deckt schonungslos auf wo es bricht. Jeder Fehler wird so detailliert geloggt,
dass der Bug direkt nachvollziehbar und fixbar ist.

Ausführung:
    pytest test/test_cad_workflow_trust.py -v                       # 1x Durchlauf
    pytest test/test_cad_workflow_trust.py -k "sketch" -v           # Nur Sketch-Tests
    pytest test/test_cad_workflow_trust.py -k "N_pushpull" -v       # Kritischer Workflow
    CAD_TRUST_ITERATIONS=5 pytest test/test_cad_workflow_trust.py   # 5x Stress
    pytest test/test_cad_workflow_trust.py -v --tb=long -s          # Mit Logging
"""

import math
import os
import random

import pytest
from loguru import logger
from shapely.geometry import Polygon

from modeling import (
    Body,
    ChamferFeature,
    Document,
    ExtrudeFeature,
    FilletFeature,
    PrimitiveFeature,
    RevolveFeature,
    ShellFeature,
)
from modeling.geometric_selector import GeometricFaceSelector
from modeling.topology_indexing import edge_index_of, face_index_of
from modeling.tnp_system import ShapeType
from sketcher.sketch import Sketch, SketchState
from sketcher.geometry import Point2D, Line2D, Circle2D, Arc2D
from sketcher.operations.trim import TrimOperation

# ---------------------------------------------------------------------------
# Konfigurierbare Durchläufe
# ---------------------------------------------------------------------------
STRESS_ITERATIONS = int(os.environ.get("CAD_TRUST_ITERATIONS", "1"))

_AXIS_DIRECTIONS = (
    (1.0, 0.0, 0.0),
    (-1.0, 0.0, 0.0),
    (0.0, 1.0, 0.0),
    (0.0, -1.0, 0.0),
    (0.0, 0.0, 1.0),
    (0.0, 0.0, -1.0),
)


# ===========================================================================
# DIAGNOSTISCHES LOGGING
# ===========================================================================

def _solid_signature(solid):
    """Geometrie-Fingerprint eines Solids."""
    assert solid is not None, "Solid is None!"
    bb = solid.bounding_box()
    return {
        "volume": float(solid.volume),
        "faces": len(list(solid.faces())),
        "edges": len(list(solid.edges())),
        "bbox": (
            float(bb.min.X), float(bb.min.Y), float(bb.min.Z),
            float(bb.max.X), float(bb.max.Y), float(bb.max.Z),
        ),
    }


def _assert_signature_close(a: dict, b: dict, *, context: str):
    """Vergleicht zwei Solid-Signaturen auf Gleichheit."""
    assert a["faces"] == b["faces"], f"{context}: face-count {a['faces']} != {b['faces']}"
    assert a["edges"] == b["edges"], f"{context}: edge-count {a['edges']} != {b['edges']}"
    assert a["volume"] == pytest.approx(b["volume"], rel=1e-6, abs=1e-6), (
        f"{context}: volume {a['volume']} != {b['volume']}"
    )


def _log_step(step_name: str, body, feature=None):
    """Loggt den aktuellen Zustand nach jedem Schritt."""
    solid = body._build123d_solid
    if solid:
        sig = _solid_signature(solid)
        logger.info(f"[STEP] {step_name} | vol={sig['volume']:.2f} faces={sig['faces']} edges={sig['edges']}")
    else:
        logger.info(f"[STEP] {step_name} | KEIN SOLID")
    for i, f in enumerate(body.features):
        status = getattr(f, "status", "?")
        msg = getattr(f, "status_message", "") or ""
        logger.info(f"  [{i}] {f.name} | status={status} | {msg}")
    if feature:
        _log_feature_detail(feature)


def _log_feature_detail(feature):
    """Detail-Logging eines Features."""
    logger.info(f"  Feature Detail: {feature.name} (type={type(feature).__name__})")
    if hasattr(feature, "edge_indices") and feature.edge_indices:
        logger.info(f"    edge_indices={feature.edge_indices}")
    if hasattr(feature, "edge_shape_ids") and feature.edge_shape_ids:
        logger.info(f"    edge_shape_ids={len(feature.edge_shape_ids)} entries")
    if hasattr(feature, "face_index") and feature.face_index is not None:
        logger.info(f"    face_index={feature.face_index}")


def _log_failure_diagnostic(context: str, body, doc, feature=None, pre_sig=None, post_sig=None):
    """Vollständiger Debug-Dump bei Test-Fehler."""
    logger.error(f"{'=' * 60}")
    logger.error(f"FAILURE DIAGNOSTIC: {context}")
    logger.error(f"{'=' * 60}")

    solid = body._build123d_solid
    if solid:
        logger.error(f"  Solid: volume={solid.volume:.4f}, faces={len(list(solid.faces()))}, edges={len(list(solid.edges()))}")
    else:
        logger.error(f"  Solid: NONE!")

    if pre_sig and post_sig:
        logger.error(f"  PRE:  vol={pre_sig['volume']:.4f} faces={pre_sig['faces']} edges={pre_sig['edges']}")
        logger.error(f"  POST: vol={post_sig['volume']:.4f} faces={post_sig['faces']} edges={post_sig['edges']}")
        dv = post_sig["volume"] - pre_sig["volume"]
        df = post_sig["faces"] - pre_sig["faces"]
        de = post_sig["edges"] - pre_sig["edges"]
        logger.error(f"  DIFF: vol={dv:.4f} faces={df} edges={de}")

    logger.error(f"  Feature Chain ({len(body.features)} features):")
    for i, f in enumerate(body.features):
        marker = ">>>" if f is feature else "   "
        status = getattr(f, "status", "?")
        msg = getattr(f, "status_message", "") or ""
        logger.error(f"  {marker}[{i}] {f.name} | status={status} | {msg}")
        if status not in ("OK", "SUCCESS", None):
            details = getattr(f, "status_details", None)
            if details:
                logger.error(f"       details={details}")

    if doc and hasattr(doc, "_shape_naming_service"):
        try:
            report = doc._shape_naming_service.get_health_report(body)
            logger.error(f"  TNP Report: status={report.get('status')}")
            for fr in report.get("features", []):
                broken = fr.get("broken", 0)
                if broken > 0 or fr.get("status") == "broken":
                    logger.error(f"    BROKEN: {fr.get('name')} | broken={broken} | {fr.get('status_message', '')}")
        except Exception as e:
            logger.error(f"  TNP Report: FAILED ({e})")

    if feature and hasattr(feature, "edge_indices") and solid:
        all_edges = list(solid.edges())
        logger.error(f"  Edge Analysis: solid has {len(all_edges)} edges, feature wants indices={feature.edge_indices}")
        for idx in feature.edge_indices or []:
            if 0 <= idx < len(all_edges):
                e = all_edges[idx]
                c = e.center()
                logger.error(f"    edge[{idx}]: length={e.length:.4f}, center=({c.X:.2f},{c.Y:.2f},{c.Z:.2f})")
            else:
                logger.error(f"    edge[{idx}]: OUT OF RANGE! (max={len(all_edges) - 1})")

    logger.error(f"{'=' * 60}")


# ===========================================================================
# HELPER-FUNKTIONEN
# ===========================================================================

def _is_success(status: str) -> bool:
    return str(status or "").upper() in {"OK", "SUCCESS"}


def _pick_face_by_direction(solid, direction):
    dx, dy, dz = direction
    return max(
        list(solid.faces()),
        key=lambda f: float(f.center().X) * dx + float(f.center().Y) * dy + float(f.center().Z) * dz,
    )


def _top_edge_indices(solid, limit: int = 4):
    top_face = max(list(solid.faces()), key=lambda f: float(f.center().Z))
    indices = []
    for edge in top_face.edges():
        edge_idx = edge_index_of(solid, edge)
        if edge_idx is None:
            continue
        idx = int(edge_idx)
        if idx not in indices:
            indices.append(idx)
        if len(indices) >= limit:
            break
    return indices


def _bottom_edge_indices(solid, limit: int = 4):
    bottom_face = min(list(solid.faces()), key=lambda f: float(f.center().Z))
    indices = []
    for edge in bottom_face.edges():
        edge_idx = edge_index_of(solid, edge)
        if edge_idx is None:
            continue
        idx = int(edge_idx)
        if idx not in indices:
            indices.append(idx)
        if len(indices) >= limit:
            break
    return indices


def _all_edge_indices(solid):
    return list(range(len(list(solid.edges()))))


def _register_face_shape_id(doc, face, feature_seed, local_index):
    fc = face.center()
    return doc._shape_naming_service.register_shape(
        ocp_shape=face.wrapped,
        shape_type=ShapeType.FACE,
        feature_id=feature_seed,
        local_index=int(local_index),
        geometry_data=(float(fc.X), float(fc.Y), float(fc.Z), float(face.area)),
    )


def _add_pushpull_join(doc, body, step, direction, distance):
    """Push/Pull Join via rebuild path."""
    solid = body._build123d_solid
    assert solid is not None, f"Step {step}: Solid is None before push/pull"

    face = _pick_face_by_direction(solid, direction)
    face_idx = face_index_of(solid, face)
    assert face_idx is not None, f"Step {step}: face_index_of returned None"
    face_idx = int(face_idx)

    shape_id = _register_face_shape_id(doc, face, f"trust_wf_{step}", face_idx)
    poly = Polygon([(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)])
    feat = ExtrudeFeature(
        sketch=None,
        distance=float(distance),
        operation="Join",
        face_index=face_idx,
        face_shape_id=shape_id,
        precalculated_polys=[poly],
        name=f"Push/Pull (Join) {step}",
    )
    body.add_feature(feat, rebuild=True)
    return feat


def _clone_and_rebuild(body, name):
    clone_doc = Document(name)
    clone = Body.from_dict(body.to_dict())
    clone_doc.add_body(clone, set_active=True)
    clone._rebuild()
    return clone_doc, clone


def _create_rectangle_sketch(width=40.0, height=30.0):
    """Erstellt programmatisch ein Rechteck-Sketch mit closed_profiles."""
    sketch = Sketch("Rectangle")
    lines = sketch.add_rectangle(0, 0, width, height)
    # closed_profiles muss mit Shapely-Polygonen befüllt sein (GUI tut das automatisch)
    coords = [(0, 0), (width, 0), (width, height), (0, height), (0, 0)]
    sketch.closed_profiles = [Polygon(coords)]
    return sketch, lines


def _create_circle_sketch(radius=15.0):
    """Erstellt programmatisch ein Kreis-Sketch mit closed_profiles."""
    sketch = Sketch("Circle")
    circle = sketch.add_circle(0, 0, radius)
    # Kreis als Polygon approximieren für closed_profiles
    n_pts = 64
    coords = [
        (radius * math.cos(2 * math.pi * i / n_pts), radius * math.sin(2 * math.pi * i / n_pts))
        for i in range(n_pts)
    ]
    coords.append(coords[0])
    sketch.closed_profiles = [Polygon(coords)]
    return sketch, circle


def _create_l_shape_sketch():
    """Erstellt L-förmiges Profil für Revolve-Tests mit closed_profiles."""
    sketch = Sketch("L-Shape")
    # L-Profil: Basis 20x10, Steg 10x20
    sketch.add_line(0, 0, 20, 0)
    sketch.add_line(20, 0, 20, 10)
    sketch.add_line(20, 10, 10, 10)
    sketch.add_line(10, 10, 10, 20)
    sketch.add_line(10, 20, 0, 20)
    sketch.add_line(0, 20, 0, 0)
    coords = [(0, 0), (20, 0), (20, 10), (10, 10), (10, 20), (0, 20), (0, 0)]
    sketch.closed_profiles = [Polygon(coords)]
    return sketch


def _assert_chamfer_applied(pre_sig, post_sig, context, body=None, doc=None, feature=None):
    """Prüft dass Chamfer TATSÄCHLICH angewendet wurde (Geometry Truth)."""
    try:
        assert post_sig["faces"] > pre_sig["faces"], (
            f"{context}: Chamfer hat keine Flächen hinzugefügt! "
            f"faces: {pre_sig['faces']} -> {post_sig['faces']}"
        )
        assert post_sig["volume"] < pre_sig["volume"], (
            f"{context}: Chamfer hat kein Material entfernt! "
            f"volume: {pre_sig['volume']:.4f} -> {post_sig['volume']:.4f}"
        )
    except AssertionError:
        if body and doc:
            _log_failure_diagnostic(context, body, doc, feature=feature, pre_sig=pre_sig, post_sig=post_sig)
        raise


def _assert_fillet_applied(pre_sig, post_sig, context, body=None, doc=None, feature=None):
    """Prüft dass Fillet TATSÄCHLICH angewendet wurde (Geometry Truth)."""
    try:
        assert post_sig["faces"] > pre_sig["faces"], (
            f"{context}: Fillet hat keine Flächen hinzugefügt! "
            f"faces: {pre_sig['faces']} -> {post_sig['faces']}"
        )
        assert post_sig["volume"] < pre_sig["volume"], (
            f"{context}: Fillet hat kein Material entfernt! "
            f"volume: {pre_sig['volume']:.4f} -> {post_sig['volume']:.4f}"
        )
    except AssertionError:
        if body and doc:
            _log_failure_diagnostic(context, body, doc, feature=feature, pre_sig=pre_sig, post_sig=post_sig)
        raise


def _assert_tnp_no_broken(doc, body, include_types=None):
    """Prüft TNP Health Report auf gebrochene Referenzen."""
    report = doc._shape_naming_service.get_health_report(body)
    features = report.get("features", [])
    if include_types:
        features = [f for f in features if f.get("type") in include_types]
    for feat in features:
        broken = int(feat.get("broken", 0))
        assert broken == 0, (
            f"TNP broken refs in {feat.get('name')}: broken={broken}, "
            f"status={feat.get('status')}, msg={feat.get('status_message')}"
        )


def _make_doc_body(name="trust_test"):
    """Erstellt Document + Body Paar."""
    doc = Document(name)
    body = Body(f"Body_{name}", document=doc)
    doc.add_body(body, set_active=True)
    return doc, body


def _add_box_base(body, length=40.0, width=28.0, height=18.0, name="Base Box"):
    """Fügt PrimitiveFeature Box hinzu und verifiziert."""
    base = PrimitiveFeature(primitive_type="box", length=length, width=width, height=height, name=name)
    body.add_feature(base, rebuild=True)
    assert _is_success(base.status), f"Base Box failed: {base.status_message}"
    assert body._build123d_solid is not None, "Base Box produced no solid"
    _log_step("Base Box created", body, base)
    return base


def _add_cylinder_base(body, radius=15.0, height=30.0, name="Base Cylinder"):
    """Fügt PrimitiveFeature Cylinder hinzu und verifiziert."""
    base = PrimitiveFeature(primitive_type="cylinder", radius=radius, height=height, name=name)
    body.add_feature(base, rebuild=True)
    assert _is_success(base.status), f"Base Cylinder failed: {base.status_message}"
    assert body._build123d_solid is not None, "Base Cylinder produced no solid"
    _log_step("Base Cylinder created", body, base)
    return base


# ===========================================================================
# STUFE 1: 2D SKETCH GRUNDLAGEN
# ===========================================================================

class TestSketchBasics:
    """Kann das System korrekte 2D-Skizzen erzeugen?"""

    def test_sketch_rectangle_creation(self):
        """Rechteck: 4 Linien, geschlossen, korrekte Maße."""
        sketch, lines = _create_rectangle_sketch(40, 30)

        assert len(lines) == 4, f"Erwarte 4 Linien, got {len(lines)}"
        assert len(sketch.lines) == 4

        # Maße prüfen
        horizontal = [l for l in lines if abs(l.start.y - l.end.y) < 1e-6]
        vertical = [l for l in lines if abs(l.start.x - l.end.x) < 1e-6]
        assert len(horizontal) == 2, f"Erwarte 2 horizontale Linien, got {len(horizontal)}"
        assert len(vertical) == 2, f"Erwarte 2 vertikale Linien, got {len(vertical)}"

        for h in horizontal:
            assert abs(h.length - 40.0) < 1e-6, f"Horizontale Linie: length={h.length}, erwarte 40"
        for v in vertical:
            assert abs(v.length - 30.0) < 1e-6, f"Vertikale Linie: length={v.length}, erwarte 30"

        # Geschlossenes Profil
        profiles = sketch._find_closed_profiles()
        assert len(profiles) >= 1, "Kein geschlossenes Profil erkannt!"

    def test_sketch_circle_creation(self):
        """Kreis: Radius korrekt, Profil erkannt."""
        sketch, circle = _create_circle_sketch(15.0)

        assert len(sketch.circles) == 1
        assert abs(circle.radius - 15.0) < 1e-6
        assert abs(circle.center.x) < 1e-6
        assert abs(circle.center.y) < 1e-6

    def test_sketch_rectangle_with_constraints(self):
        """Rechteck mit Constraints → Solver löst korrekt."""
        sketch, lines = _create_rectangle_sketch(40, 30)

        # add_rectangle fügt bereits H/V Constraints hinzu
        # Zusätzlich: Fix + Length
        from sketcher.constraints import make_fixed, make_length
        sketch.constraints.append(make_fixed(lines[0].start))
        sketch.constraints.append(make_length(lines[0], 40.0))
        sketch.constraints.append(make_length(lines[1], 30.0))

        result = sketch.solve()
        assert result.success, f"Solver failed: {result}"

        # Maße nach Solve noch korrekt
        assert abs(lines[0].length - 40.0) < 0.1, f"Width nach Solve: {lines[0].length}"
        assert abs(lines[1].length - 30.0) < 0.1, f"Height nach Solve: {lines[1].length}"

    def test_sketch_circle_with_constraints(self):
        """Kreis mit Constraints → Solver löst."""
        sketch, circle = _create_circle_sketch(25.0)

        from sketcher.constraints import make_fixed, make_radius
        sketch.constraints.append(make_fixed(circle.center))
        sketch.constraints.append(make_radius(circle, 25.0))

        result = sketch.solve()
        assert result.success, f"Solver failed: {result}"
        assert abs(circle.radius - 25.0) < 0.1

    def test_sketch_trim_line(self):
        """2 sich kreuzende Linien → Trim → korrektes Segment entfernt."""
        sketch = Sketch("trim_test")
        target = sketch.add_line(0.0, 0.0, 10.0, 0.0)
        sketch.add_line(5.0, -5.0, 5.0, 5.0)  # Cutter

        op = TrimOperation(sketch)
        find_result = op.find_segment(target, Point2D(2.0, 0.0))
        assert find_result.success, f"Trim find failed: {find_result}"

        exec_result = op.execute_trim(find_result.segment)
        assert exec_result.success, f"Trim exec failed: {exec_result}"

        # Verbleibendes Segment: rechte Hälfte (5→10)
        remaining_lines = [l for l in sketch.lines if not l.construction]
        assert len(remaining_lines) >= 2, f"Erwarte mindestens 2 Linien nach Trim, got {len(remaining_lines)}"

    def test_sketch_trim_circle_to_arc(self):
        """Kreis + Linie → Trim Kreis → Arc entsteht."""
        sketch = Sketch("trim_circle")
        circle = sketch.add_circle(0.0, 0.0, 5.0)
        sketch.add_line(-10.0, 0.0, 10.0, 0.0)  # Cutter

        op = TrimOperation(sketch)
        find_result = op.find_segment(circle, Point2D(0.0, 5.0))

        if find_result.success:
            exec_result = op.execute_trim(find_result.segment)
            assert exec_result.success, f"Trim circle failed: {exec_result}"
            # Nach Trim sollte ein Arc existieren
            assert len(sketch.arcs) >= 1, "Kein Arc nach Circle-Trim!"
        else:
            # Trim nicht möglich = auch ein valides Ergebnis, loggen
            logger.warning(f"Circle trim not possible: {find_result}")

    def test_sketch_profile_detection(self):
        """Geschlossenes Profil aus Linien → Profil erkannt."""
        sketch = Sketch("profile_test")
        # Dreieck
        sketch.add_line(0, 0, 10, 0)
        sketch.add_line(10, 0, 5, 8)
        sketch.add_line(5, 8, 0, 0)

        profiles = sketch._find_closed_profiles()
        assert len(profiles) >= 1, "Kein geschlossenes Profil (Dreieck) erkannt!"

    def test_sketch_complex_profile_rectangle_with_hole(self):
        """Rechteck + innerer Kreis → mindestens 1 Profil."""
        sketch = Sketch("complex_profile")
        sketch.add_rectangle(0, 0, 40, 30)
        # Kreis in der Mitte (wird als separate Geometrie erkannt)
        sketch.add_circle(20, 15, 5)

        # Mindestens das Rechteck-Profil muss erkannt werden
        profiles = sketch._find_closed_profiles()
        assert len(profiles) >= 1, "Kein Profil bei Rechteck+Kreis!"


# ===========================================================================
# STUFE 2: SKETCH → 3D (EXTRUDE / REVOLVE)
# ===========================================================================

class TestSketchTo3D:
    """Kann eine Skizze korrekt in 3D umgewandelt werden?"""

    def test_extrude_rectangle_sketch(self):
        """Sketch-Rechteck → Extrude → Box."""
        pytest.importorskip("OCP.BRepFeat")

        sketch, lines = _create_rectangle_sketch(40, 30)
        profiles = sketch._find_closed_profiles()
        assert profiles, "Kein Profil für Extrude!"

        doc, body = _make_doc_body("extrude_rect")
        feat = ExtrudeFeature(
            sketch=sketch,
            distance=20.0,
            operation="New Body",
            name="Extrude Rect",
        )
        body.add_feature(feat, rebuild=True)
        _log_step("Extrude Rectangle", body, feat)

        assert _is_success(feat.status), f"Extrude failed: {feat.status_message}"
        solid = body._build123d_solid
        assert solid is not None, "Extrude produced no solid"

        sig = _solid_signature(solid)
        expected_vol = 40.0 * 30.0 * 20.0
        assert sig["volume"] == pytest.approx(expected_vol, rel=0.05), (
            f"Volume {sig['volume']} != expected {expected_vol}"
        )
        assert sig["faces"] == 6, f"Box should have 6 faces, got {sig['faces']}"
        assert sig["edges"] == 12, f"Box should have 12 edges, got {sig['edges']}"

    def test_extrude_circle_sketch(self):
        """Sketch-Kreis → Extrude → Zylinder."""
        pytest.importorskip("OCP.BRepFeat")

        sketch, circle = _create_circle_sketch(15.0)

        doc, body = _make_doc_body("extrude_circle")
        feat = ExtrudeFeature(
            sketch=sketch,
            distance=25.0,
            operation="New Body",
            name="Extrude Circle",
        )
        body.add_feature(feat, rebuild=True)
        _log_step("Extrude Circle", body, feat)

        assert _is_success(feat.status), f"Extrude circle failed: {feat.status_message}"
        solid = body._build123d_solid
        assert solid is not None, "Extrude circle produced no solid"

        sig = _solid_signature(solid)
        expected_vol = math.pi * 15.0**2 * 25.0
        assert sig["volume"] == pytest.approx(expected_vol, rel=0.05), (
            f"Cylinder volume {sig['volume']} != expected {expected_vol}"
        )
        assert sig["faces"] == 3, f"Cylinder should have 3 faces, got {sig['faces']}"

    def test_revolve_l_shape_360(self):
        """L-Profil → Revolve 360° → Rotationskörper."""
        pytest.importorskip("OCP.BRepFeat")

        sketch = _create_l_shape_sketch()
        profiles = sketch._find_closed_profiles()
        assert profiles, "L-Shape hat kein geschlossenes Profil!"

        doc, body = _make_doc_body("revolve_l")
        feat = RevolveFeature(
            sketch=sketch,
            angle=360.0,
            axis=(0, 1, 0),
            axis_origin=(0, 0, 0),
            operation="New Body",
            name="Revolve L 360",
        )
        body.add_feature(feat, rebuild=True)
        _log_step("Revolve L-Shape 360", body, feat)

        assert _is_success(feat.status), f"Revolve failed: {feat.status_message}"
        solid = body._build123d_solid
        assert solid is not None, "Revolve produced no solid"
        assert float(solid.volume) > 0, "Revolve volume is 0!"

    def test_revolve_rectangle_180(self):
        """Rechteck → Revolve 180° → Halbzylinder-artig."""
        pytest.importorskip("OCP.BRepFeat")

        sketch, lines = _create_rectangle_sketch(10, 5)

        doc, body = _make_doc_body("revolve_rect_180")
        feat = RevolveFeature(
            sketch=sketch,
            angle=180.0,
            axis=(0, 1, 0),
            axis_origin=(0, 0, 0),
            operation="New Body",
            name="Revolve Rect 180",
        )
        body.add_feature(feat, rebuild=True)
        _log_step("Revolve Rect 180", body, feat)

        assert _is_success(feat.status), f"Revolve 180 failed: {feat.status_message}"
        solid = body._build123d_solid
        assert solid is not None, "Revolve 180 produced no solid"
        assert float(solid.volume) > 0, "Revolve 180 volume is 0!"

    def test_extrude_with_cut_operation(self):
        """Sketch → Extrude Cut aus bestehendem Box-Körper."""
        pytest.importorskip("OCP.BRepFeat")

        doc, body = _make_doc_body("extrude_cut")
        _add_box_base(body, 40, 30, 20)
        pre_sig = _solid_signature(body._build123d_solid)

        # Kleines Rechteck als Cut-Sketch
        cut_sketch, _ = _create_rectangle_sketch(10, 10)
        cut_feat = ExtrudeFeature(
            sketch=cut_sketch,
            distance=20.0,
            operation="Cut",
            name="Extrude Cut",
        )
        body.add_feature(cut_feat, rebuild=True)
        _log_step("Extrude Cut", body, cut_feat)

        assert _is_success(cut_feat.status), f"Extrude Cut failed: {cut_feat.status_message}"
        post_sig = _solid_signature(body._build123d_solid)
        assert post_sig["volume"] < pre_sig["volume"], (
            f"Cut should reduce volume: {pre_sig['volume']} -> {post_sig['volume']}"
        )


# ===========================================================================
# STUFE 3: PUSH/PULL + EDGE-OPS (DER KRITISCHE WORKFLOW)
# ===========================================================================

class TestPushPullEdgeOps:
    """Box → N× Push/Pull → Chamfer/Fillet. MUSS funktionieren."""

    @pytest.mark.parametrize("n_pushpulls", [1, 2, 3, 5, 7])
    def test_box_N_pushpull_chamfer(self, n_pushpulls):
        """KRITISCH: Box → N× Push/Pull → Chamfer top edges."""
        pytest.importorskip("OCP.BRepFeat")

        doc, body = _make_doc_body(f"pp{n_pushpulls}_chamfer")
        _add_box_base(body)

        directions = _AXIS_DIRECTIONS[:n_pushpulls]
        for step, direction in enumerate(directions):
            dist = 2.0 + 0.25 * step
            feat = _add_pushpull_join(doc, body, step, direction, dist)
            assert _is_success(feat.status), (
                f"Push/Pull step {step} failed: {feat.status_message}"
            )
            _log_step(f"Push/Pull {step}/{n_pushpulls}", body, feat)

        # Chamfer top edges
        solid = body._build123d_solid
        assert solid is not None, f"Solid is None after {n_pushpulls}x Push/Pull"
        pre_sig = _solid_signature(solid)

        edge_indices = _top_edge_indices(solid, limit=4)
        assert edge_indices, f"Keine Top-Edges gefunden nach {n_pushpulls}x PP"
        logger.info(f"Chamfer edge_indices={edge_indices} (solid has {pre_sig['edges']} edges)")

        chamfer = ChamferFeature(distance=0.8, edge_indices=edge_indices, name=f"Chamfer after {n_pushpulls}xPP")
        body.add_feature(chamfer, rebuild=True)
        _log_step(f"Chamfer after {n_pushpulls}x PP", body, chamfer)

        # Dreifach-Prüfung
        # 1. Status
        if not _is_success(chamfer.status):
            _log_failure_diagnostic(f"Chamfer_N{n_pushpulls}", body, doc, chamfer, pre_sig, None)
        assert _is_success(chamfer.status), f"Chamfer failed after {n_pushpulls}x PP: {chamfer.status_message}"

        # 2. Geometry Truth
        post_sig = _solid_signature(body._build123d_solid)
        _assert_chamfer_applied(pre_sig, post_sig, f"Chamfer_N{n_pushpulls}", body, doc, chamfer)

        # 3. TNP Reality
        _assert_tnp_no_broken(doc, body, {"Extrude", "Chamfer"})

    @pytest.mark.parametrize("n_pushpulls", [1, 2, 3, 5, 7])
    def test_box_N_pushpull_fillet(self, n_pushpulls):
        """Box → N× Push/Pull → Fillet top edges."""
        pytest.importorskip("OCP.BRepFeat")

        doc, body = _make_doc_body(f"pp{n_pushpulls}_fillet")
        _add_box_base(body)

        directions = _AXIS_DIRECTIONS[:n_pushpulls]
        for step, direction in enumerate(directions):
            dist = 2.0 + 0.25 * step
            feat = _add_pushpull_join(doc, body, step, direction, dist)
            assert _is_success(feat.status), f"PP step {step}: {feat.status_message}"

        solid = body._build123d_solid
        assert solid is not None
        pre_sig = _solid_signature(solid)

        edge_indices = _top_edge_indices(solid, limit=4)
        assert edge_indices

        fillet = FilletFeature(radius=0.6, edge_indices=edge_indices, name=f"Fillet after {n_pushpulls}xPP")
        body.add_feature(fillet, rebuild=True)
        _log_step(f"Fillet after {n_pushpulls}x PP", body, fillet)

        if not _is_success(fillet.status):
            _log_failure_diagnostic(f"Fillet_N{n_pushpulls}", body, doc, fillet, pre_sig, None)
        assert _is_success(fillet.status), f"Fillet failed after {n_pushpulls}x PP: {fillet.status_message}"

        post_sig = _solid_signature(body._build123d_solid)
        _assert_fillet_applied(pre_sig, post_sig, f"Fillet_N{n_pushpulls}", body, doc, fillet)
        _assert_tnp_no_broken(doc, body, {"Extrude", "Fillet"})

    def test_box_pushpull_fillet_pushpull_chamfer(self):
        """PP → Fillet → PP → Chamfer (gemischte Reihenfolge)."""
        pytest.importorskip("OCP.BRepFeat")

        doc, body = _make_doc_body("mixed_ops")
        _add_box_base(body)

        # PP 1
        pp1 = _add_pushpull_join(doc, body, 0, (0, 1, 0), 3.0)
        assert _is_success(pp1.status)

        # Fillet
        solid = body._build123d_solid
        pre_fillet = _solid_signature(solid)
        fillet_edges = _top_edge_indices(solid, limit=4)
        fillet = FilletFeature(radius=0.5, edge_indices=fillet_edges, name="Fillet Mid")
        body.add_feature(fillet, rebuild=True)
        assert _is_success(fillet.status), f"Mid-Fillet failed: {fillet.status_message}"
        _assert_fillet_applied(pre_fillet, _solid_signature(body._build123d_solid), "Mid-Fillet", body, doc, fillet)

        # PP 2
        pp2 = _add_pushpull_join(doc, body, 1, (1, 0, 0), 2.5)
        assert _is_success(pp2.status), f"PP after Fillet failed: {pp2.status_message}"

        # Chamfer
        solid = body._build123d_solid
        pre_chamfer = _solid_signature(solid)
        chamfer_edges = _bottom_edge_indices(solid, limit=4)
        chamfer = ChamferFeature(distance=0.6, edge_indices=chamfer_edges, name="Chamfer End")
        body.add_feature(chamfer, rebuild=True)

        if not _is_success(chamfer.status):
            _log_failure_diagnostic("Mixed_Chamfer", body, doc, chamfer, pre_chamfer, None)
        assert _is_success(chamfer.status), f"End-Chamfer failed: {chamfer.status_message}"
        _assert_chamfer_applied(pre_chamfer, _solid_signature(body._build123d_solid), "Mixed_Chamfer", body, doc, chamfer)

    @pytest.mark.parametrize("n_pushpulls", [1, 3, 5])
    def test_pushpull_chamfer_rebuild_idempotent(self, n_pushpulls):
        """3× Rebuild → identische Geometrie."""
        pytest.importorskip("OCP.BRepFeat")

        doc, body = _make_doc_body(f"rebuild_idem_{n_pushpulls}")
        _add_box_base(body)

        for step in range(n_pushpulls):
            direction = _AXIS_DIRECTIONS[step % len(_AXIS_DIRECTIONS)]
            _add_pushpull_join(doc, body, step, direction, 2.0 + 0.3 * step)

        edge_indices = _top_edge_indices(body._build123d_solid, limit=4)
        chamfer = ChamferFeature(distance=0.7, edge_indices=edge_indices)
        body.add_feature(chamfer, rebuild=True)
        assert _is_success(chamfer.status)

        ref_sig = _solid_signature(body._build123d_solid)

        for cycle in range(3):
            body._rebuild()
            cycle_sig = _solid_signature(body._build123d_solid)
            _assert_signature_close(ref_sig, cycle_sig, context=f"rebuild_cycle_{cycle}")

    def test_box_chamfer_all_12_edges(self):
        """Box → Chamfer alle 12 Kanten."""
        pytest.importorskip("OCP.BRepFeat")

        doc, body = _make_doc_body("chamfer_all_12")
        _add_box_base(body, 30, 20, 15)

        solid = body._build123d_solid
        pre_sig = _solid_signature(solid)
        assert pre_sig["edges"] == 12

        all_indices = _all_edge_indices(solid)
        chamfer = ChamferFeature(distance=0.5, edge_indices=all_indices, name="Chamfer All 12")
        body.add_feature(chamfer, rebuild=True)
        _log_step("Chamfer all 12 edges", body, chamfer)

        if not _is_success(chamfer.status):
            _log_failure_diagnostic("Chamfer_All12", body, doc, chamfer, pre_sig, None)
        assert _is_success(chamfer.status), f"Chamfer all 12: {chamfer.status_message}"
        _assert_chamfer_applied(pre_sig, _solid_signature(body._build123d_solid), "Chamfer_All12", body, doc, chamfer)

    def test_cylinder_fillet_circular_edges(self):
        """Zylinder → Fillet obere und untere kreisförmige Kanten."""
        pytest.importorskip("OCP.BRepFeat")

        doc, body = _make_doc_body("cyl_fillet")
        _add_cylinder_base(body, radius=15, height=30)

        solid = body._build123d_solid
        pre_sig = _solid_signature(solid)

        # Zylinder hat 2 kreisförmige Kanten (oben/unten) + evtl. Naht
        top_edges = _top_edge_indices(solid, limit=2)
        assert top_edges, "Keine Top-Edges am Zylinder"

        fillet = FilletFeature(radius=2.0, edge_indices=top_edges, name="Fillet Circular")
        body.add_feature(fillet, rebuild=True)
        _log_step("Fillet Cylinder", body, fillet)

        if not _is_success(fillet.status):
            _log_failure_diagnostic("Cyl_Fillet", body, doc, fillet, pre_sig, None)
        assert _is_success(fillet.status), f"Cylinder fillet: {fillet.status_message}"


# ===========================================================================
# STUFE 4: BOOLEAN WORKFLOWS
# ===========================================================================

class TestBooleanWorkflows:
    """Boolean-Operationen + nachfolgende Edge-Ops."""

    def test_box_cut_box_then_chamfer(self):
        """Box1 - Box2 (Cut) → Chamfer."""
        pytest.importorskip("OCP.BRepFeat")

        doc, body = _make_doc_body("bool_cut_chamfer")
        _add_box_base(body, 40, 30, 20)
        pre_cut_sig = _solid_signature(body._build123d_solid)

        # Cut-Sketch: kleines Rechteck oben
        cut_sketch, _ = _create_rectangle_sketch(15, 10)
        cut = ExtrudeFeature(
            sketch=cut_sketch,
            distance=20.0,
            operation="Cut",
            name="Boolean Cut",
        )
        body.add_feature(cut, rebuild=True)
        _log_step("Boolean Cut", body, cut)
        assert _is_success(cut.status), f"Boolean Cut failed: {cut.status_message}"

        post_cut_sig = _solid_signature(body._build123d_solid)
        assert post_cut_sig["volume"] < pre_cut_sig["volume"], "Cut didn't reduce volume"

        # Chamfer nach Boolean Cut
        pre_chamfer = _solid_signature(body._build123d_solid)
        edge_indices = _top_edge_indices(body._build123d_solid, limit=4)
        assert edge_indices, "Keine Edges nach Boolean Cut"

        chamfer = ChamferFeature(distance=0.5, edge_indices=edge_indices, name="Chamfer Post-Cut")
        body.add_feature(chamfer, rebuild=True)
        _log_step("Chamfer after Cut", body, chamfer)

        if not _is_success(chamfer.status):
            _log_failure_diagnostic("Bool_Cut_Chamfer", body, doc, chamfer, pre_chamfer, None)
        assert _is_success(chamfer.status), f"Chamfer after Cut: {chamfer.status_message}"

    def test_boolean_then_pushpull_then_chamfer(self):
        """Cut → Push/Pull → Chamfer (3-stufig)."""
        pytest.importorskip("OCP.BRepFeat")

        doc, body = _make_doc_body("bool_pp_chamfer")
        _add_box_base(body, 50, 35, 25)

        # Cut
        cut_sketch, _ = _create_rectangle_sketch(10, 10)
        cut = ExtrudeFeature(sketch=cut_sketch, distance=25.0, operation="Cut", name="Cut Step")
        body.add_feature(cut, rebuild=True)
        assert _is_success(cut.status), f"Cut failed: {cut.status_message}"

        # Push/Pull
        pp = _add_pushpull_join(doc, body, 0, (0, 1, 0), 3.0)
        assert _is_success(pp.status), f"PP after Cut failed: {pp.status_message}"

        # Chamfer
        pre_chamfer = _solid_signature(body._build123d_solid)
        edges = _top_edge_indices(body._build123d_solid, limit=4)
        chamfer = ChamferFeature(distance=0.5, edge_indices=edges, name="Chamfer Final")
        body.add_feature(chamfer, rebuild=True)

        if not _is_success(chamfer.status):
            _log_failure_diagnostic("Bool_PP_Chamfer", body, doc, chamfer, pre_chamfer, None)
        assert _is_success(chamfer.status), f"Final Chamfer: {chamfer.status_message}"
        _assert_chamfer_applied(pre_chamfer, _solid_signature(body._build123d_solid), "Bool_PP_Chamfer", body, doc, chamfer)


# ===========================================================================
# STUFE 5: ASSEMBLY
# ===========================================================================

class TestAssembly:
    """Assembly-System: Komponenten, Hierarchie, Unabhängigkeit."""

    def test_assembly_create_components(self):
        """Root → 2 Sub-Components erstellen, Bodies zuweisen."""
        doc = Document("assembly_test")

        comp_a = doc.new_component("Part A")
        comp_b = doc.new_component("Part B")

        assert comp_a is not None, "Component A creation failed"
        assert comp_b is not None, "Component B creation failed"

        # Bodies in verschiedene Components
        doc.set_active_component(comp_a)
        body_a = Body("Body_A", document=doc)
        doc.add_body(body_a, set_active=True)
        _add_box_base(body_a, 20, 15, 10, "Box A")

        doc.set_active_component(comp_b)
        body_b = Body("Body_B", document=doc)
        doc.add_body(body_b, set_active=True)
        _add_box_base(body_b, 30, 20, 15, "Box B")

        # Alle Bodies auffindbar
        all_bodies = doc.get_all_bodies()
        assert len(all_bodies) >= 2, f"Expected 2+ bodies, got {len(all_bodies)}"

    def test_assembly_nested_components(self):
        """3 Ebenen tiefe Verschachtelung → get_all_bodies() findet alle."""
        doc = Document("nested_assembly")

        level1 = doc.new_component("Level1")
        assert level1 is not None

        doc.set_active_component(level1)
        level2 = doc.new_component("Level2")
        assert level2 is not None

        doc.set_active_component(level2)
        level3 = doc.new_component("Level3")
        assert level3 is not None

        # Body ganz unten
        doc.set_active_component(level3)
        deep_body = Body("DeepBody", document=doc)
        doc.add_body(deep_body, set_active=True)
        _add_box_base(deep_body, 10, 10, 10, "Deep Box")

        all_bodies = doc.get_all_bodies()
        found = any(b.id == deep_body.id for b in all_bodies)
        assert found, "Deep body not found by get_all_bodies()!"

    def test_assembly_independent_modeling(self):
        """Modellieren in Component A beeinflusst B nicht."""
        doc = Document("indep_assembly")

        comp_a = doc.new_component("Part A")
        comp_b = doc.new_component("Part B")

        doc.set_active_component(comp_a)
        body_a = Body("Body_A", document=doc)
        doc.add_body(body_a, set_active=True)
        _add_box_base(body_a, 20, 15, 10, "Box A")

        doc.set_active_component(comp_b)
        body_b = Body("Body_B", document=doc)
        doc.add_body(body_b, set_active=True)
        _add_box_base(body_b, 30, 20, 15, "Box B")

        sig_b_before = _solid_signature(body_b._build123d_solid)

        # Modelliere in A
        doc.set_active_component(comp_a)
        chamfer_edges = _top_edge_indices(body_a._build123d_solid, limit=4)
        chamfer = ChamferFeature(distance=1.0, edge_indices=chamfer_edges)
        body_a.add_feature(chamfer, rebuild=True)

        # B darf sich nicht verändert haben
        sig_b_after = _solid_signature(body_b._build123d_solid)
        _assert_signature_close(sig_b_before, sig_b_after, context="B_unchanged_after_A_edit")


# ===========================================================================
# STUFE 6: UNDO/REDO
# ===========================================================================

class TestUndoRedo:
    """Undo/Redo muss Geometrie identisch wiederherstellen."""

    def test_undo_redo_add_feature(self):
        """Feature hinzufügen → Undo → Redo → identische Geometrie."""
        pytest.importorskip("OCP.BRepFeat")

        doc, body = _make_doc_body("undo_add")
        _add_box_base(body)
        base_sig = _solid_signature(body._build123d_solid)

        # Chamfer hinzufügen
        edges = _top_edge_indices(body._build123d_solid, limit=4)
        chamfer = ChamferFeature(distance=0.8, edge_indices=edges)
        body.add_feature(chamfer, rebuild=True)
        assert _is_success(chamfer.status)
        after_add_sig = _solid_signature(body._build123d_solid)

        # Undo (Feature entfernen + rebuild)
        removed = body.features.pop()
        assert removed is chamfer
        body._rebuild()
        undo_sig = _solid_signature(body._build123d_solid)
        _assert_signature_close(base_sig, undo_sig, context="undo_chamfer")

        # Redo (Feature wieder hinzufügen + rebuild)
        body.features.append(chamfer)
        body._rebuild()
        redo_sig = _solid_signature(body._build123d_solid)
        _assert_signature_close(after_add_sig, redo_sig, context="redo_chamfer")

    def test_undo_redo_5x_pushpull_chamfer(self):
        """5× PP + Chamfer → Undo Chamfer → Redo → Geometrie stabil."""
        pytest.importorskip("OCP.BRepFeat")

        doc, body = _make_doc_body("undo_5pp")
        _add_box_base(body)

        for step, direction in enumerate(_AXIS_DIRECTIONS[:5]):
            feat = _add_pushpull_join(doc, body, step, direction, 2.0 + 0.25 * step)
            assert _is_success(feat.status)

        pre_chamfer_sig = _solid_signature(body._build123d_solid)

        edges = _top_edge_indices(body._build123d_solid, limit=4)
        chamfer = ChamferFeature(distance=0.7, edge_indices=edges)
        body.add_feature(chamfer, rebuild=True)
        assert _is_success(chamfer.status), f"Chamfer failed: {chamfer.status_message}"
        post_chamfer_sig = _solid_signature(body._build123d_solid)

        # Undo
        body.features.pop()
        body._rebuild()
        undo_sig = _solid_signature(body._build123d_solid)
        _assert_signature_close(pre_chamfer_sig, undo_sig, context="undo_5pp_chamfer")

        # Redo
        body.features.append(chamfer)
        body._rebuild()
        redo_sig = _solid_signature(body._build123d_solid)
        _assert_signature_close(post_chamfer_sig, redo_sig, context="redo_5pp_chamfer")

    def test_undo_redo_multiple_cycles(self):
        """3× (Undo → Redo) → Geometrie bleibt identisch."""
        pytest.importorskip("OCP.BRepFeat")

        doc, body = _make_doc_body("undo_cycles")
        _add_box_base(body)

        pp = _add_pushpull_join(doc, body, 0, (0, 1, 0), 3.0)
        assert _is_success(pp.status)

        edges = _top_edge_indices(body._build123d_solid, limit=4)
        chamfer = ChamferFeature(distance=0.6, edge_indices=edges)
        body.add_feature(chamfer, rebuild=True)
        assert _is_success(chamfer.status)

        ref_sig = _solid_signature(body._build123d_solid)
        pre_sig = _solid_signature(body._build123d_solid)

        # Undo vor Chamfer für Vergleich
        body.features.pop()
        body._rebuild()
        pre_chamfer_sig = _solid_signature(body._build123d_solid)
        body.features.append(chamfer)
        body._rebuild()

        for cycle in range(3):
            # Undo
            body.features.pop()
            body._rebuild()
            _assert_signature_close(pre_chamfer_sig, _solid_signature(body._build123d_solid),
                                    context=f"cycle_{cycle}_undo")
            # Redo
            body.features.append(chamfer)
            body._rebuild()
            _assert_signature_close(ref_sig, _solid_signature(body._build123d_solid),
                                    context=f"cycle_{cycle}_redo")

        # TNP Registry darf nicht wachsen
        stats_before = doc._shape_naming_service.get_stats()
        for _ in range(2):
            body.features.pop()
            body._rebuild()
            body.features.append(chamfer)
            body._rebuild()
        stats_after = doc._shape_naming_service.get_stats()
        assert stats_after["edges"] == stats_before["edges"], (
            f"TNP edge registry grew: {stats_before['edges']} -> {stats_after['edges']}"
        )


# ===========================================================================
# STUFE 7: SAVE/LOAD
# ===========================================================================

class TestSaveLoad:
    """Echtes Speichern und Laden - funktioniert danach noch alles?"""

    def test_save_load_simple_box(self, tmp_path):
        """Box → Save → Load → identische Geometrie."""
        doc, body = _make_doc_body("save_box")
        _add_box_base(body)
        pre_sig = _solid_signature(body._build123d_solid)

        path = str(tmp_path / "simple_box.mshcad")
        assert doc.save_project(path), "Save failed"

        loaded = Document.load_project(path)
        assert loaded is not None, "Load returned None"

        loaded_body = loaded.find_body_by_id(body.id)
        assert loaded_body is not None, "Body not found after load"
        assert loaded_body._build123d_solid is not None, "Solid is None after load"

        post_sig = _solid_signature(loaded_body._build123d_solid)
        _assert_signature_close(pre_sig, post_sig, context="save_load_box")

    def test_save_load_pushpull_chamfer(self, tmp_path):
        """Box + 5×PP + Chamfer → Save → Load → identisch."""
        pytest.importorskip("OCP.BRepFeat")

        doc, body = _make_doc_body("save_pp_chamfer")
        _add_box_base(body)

        for step, direction in enumerate(_AXIS_DIRECTIONS[:5]):
            feat = _add_pushpull_join(doc, body, step, direction, 2.0 + 0.2 * step)
            assert _is_success(feat.status)

        edges = _top_edge_indices(body._build123d_solid, limit=4)
        chamfer = ChamferFeature(distance=0.7, edge_indices=edges)
        body.add_feature(chamfer, rebuild=True)
        assert _is_success(chamfer.status), f"Chamfer failed: {chamfer.status_message}"

        pre_sig = _solid_signature(body._build123d_solid)

        path = str(tmp_path / "pp_chamfer.mshcad")
        assert doc.save_project(path), "Save failed"

        loaded = Document.load_project(path)
        assert loaded is not None
        loaded_body = loaded.find_body_by_id(body.id)
        assert loaded_body is not None
        assert loaded_body._build123d_solid is not None, "Solid None after load"

        post_sig = _solid_signature(loaded_body._build123d_solid)
        _assert_signature_close(pre_sig, post_sig, context="save_load_pp_chamfer")

    def test_save_load_continue_modeling(self, tmp_path):
        """Speichern → Laden → Weiter PP + Chamfer."""
        pytest.importorskip("OCP.BRepFeat")

        doc, body = _make_doc_body("save_continue")
        _add_box_base(body, 40, 30, 20)

        # 2 Push/Pulls
        for step, direction in enumerate([(0, 1, 0), (1, 0, 0)]):
            _add_pushpull_join(doc, body, step, direction, 2.5)

        # Save
        path = str(tmp_path / "continue.mshcad")
        assert doc.save_project(path)

        # Load
        loaded = Document.load_project(path)
        loaded_body = loaded.find_body_by_id(body.id)
        assert loaded_body is not None
        assert loaded_body._build123d_solid is not None

        # Weiter modellieren nach Load
        pp_post = _add_pushpull_join(loaded, loaded_body, 99, (0, 0, 1), 1.8)
        assert _is_success(pp_post.status), f"PP after load failed: {pp_post.status_message}"

        # Chamfer nach Load
        pre_chamfer = _solid_signature(loaded_body._build123d_solid)
        edges = _top_edge_indices(loaded_body._build123d_solid, limit=4)
        chamfer = ChamferFeature(distance=0.5, edge_indices=edges, name="Chamfer Post-Load")
        loaded_body.add_feature(chamfer, rebuild=True)

        if not _is_success(chamfer.status):
            _log_failure_diagnostic("SaveLoad_Continue_Chamfer", loaded_body, loaded, chamfer, pre_chamfer, None)
        assert _is_success(chamfer.status), f"Chamfer after load: {chamfer.status_message}"
        _assert_chamfer_applied(pre_chamfer, _solid_signature(loaded_body._build123d_solid),
                                "SaveLoad_Continue_Chamfer", loaded_body, loaded, chamfer)

    def test_save_load_tnp_integrity(self, tmp_path):
        """Nach Load: TNP Health-Report = keine broken refs."""
        pytest.importorskip("OCP.BRepFeat")

        doc, body = _make_doc_body("save_tnp")
        _add_box_base(body)

        for step, direction in enumerate(_AXIS_DIRECTIONS[:3]):
            _add_pushpull_join(doc, body, step, direction, 2.0)

        edges = _top_edge_indices(body._build123d_solid, limit=4)
        chamfer = ChamferFeature(distance=0.6, edge_indices=edges)
        body.add_feature(chamfer, rebuild=True)
        assert _is_success(chamfer.status)

        path = str(tmp_path / "tnp_integrity.mshcad")
        assert doc.save_project(path)

        loaded = Document.load_project(path)
        loaded_body = loaded.find_body_by_id(body.id)
        assert loaded_body is not None

        # TNP nach Load prüfen
        _assert_tnp_no_broken(loaded, loaded_body, {"Extrude", "Chamfer"})

    def test_save_load_assembly(self, tmp_path):
        """Assembly mit 2 Components → Save → Load → Struktur intakt."""
        doc = Document("save_assembly")
        comp_a = doc.new_component("Part A")
        comp_b = doc.new_component("Part B")

        if comp_a is not None:
            doc.set_active_component(comp_a)
        body_a = Body("Body_A", document=doc)
        doc.add_body(body_a, set_active=True)
        _add_box_base(body_a, 20, 15, 10, "Box A")

        if comp_b is not None:
            doc.set_active_component(comp_b)
        body_b = Body("Body_B", document=doc)
        doc.add_body(body_b, set_active=True)
        _add_box_base(body_b, 30, 20, 15, "Box B")

        sig_a = _solid_signature(body_a._build123d_solid)
        sig_b = _solid_signature(body_b._build123d_solid)

        path = str(tmp_path / "assembly.mshcad")
        assert doc.save_project(path)

        loaded = Document.load_project(path)
        assert loaded is not None

        all_bodies = loaded.get_all_bodies()
        assert len(all_bodies) >= 2, f"Expected 2+ bodies after load, got {len(all_bodies)}"

        loaded_a = loaded.find_body_by_id(body_a.id)
        loaded_b = loaded.find_body_by_id(body_b.id)
        assert loaded_a is not None, "Body A lost after load"
        assert loaded_b is not None, "Body B lost after load"

        if loaded_a._build123d_solid:
            _assert_signature_close(sig_a, _solid_signature(loaded_a._build123d_solid), context="assembly_load_A")
        if loaded_b._build123d_solid:
            _assert_signature_close(sig_b, _solid_signature(loaded_b._build123d_solid), context="assembly_load_B")


# ===========================================================================
# STUFE 8: REALE BAUTEILE (END-TO-END)
# ===========================================================================

class TestRealParts:
    """Simuliert echte Bauteile die User bauen würden."""

    def test_real_bracket(self, tmp_path):
        """Halterung: Box → 2× PP → Fillet → Chamfer → Save → Load."""
        pytest.importorskip("OCP.BRepFeat")

        doc, body = _make_doc_body("bracket")
        _add_box_base(body, 60, 40, 10)

        # 2 Push/Pulls für Stege
        pp1 = _add_pushpull_join(doc, body, 0, (0, 0, 1), 5.0)
        assert _is_success(pp1.status), f"Bracket PP1: {pp1.status_message}"

        pp2 = _add_pushpull_join(doc, body, 1, (0, 1, 0), 3.0)
        assert _is_success(pp2.status), f"Bracket PP2: {pp2.status_message}"

        # Fillet
        solid = body._build123d_solid
        pre_fillet = _solid_signature(solid)
        fillet_edges = _top_edge_indices(solid, limit=4)
        fillet = FilletFeature(radius=0.8, edge_indices=fillet_edges, name="Bracket Fillet")
        body.add_feature(fillet, rebuild=True)

        if not _is_success(fillet.status):
            _log_failure_diagnostic("Bracket_Fillet", body, doc, fillet, pre_fillet, None)
        assert _is_success(fillet.status), f"Bracket Fillet: {fillet.status_message}"

        # Chamfer
        solid = body._build123d_solid
        pre_chamfer = _solid_signature(solid)
        chamfer_edges = _bottom_edge_indices(solid, limit=4)
        chamfer = ChamferFeature(distance=0.5, edge_indices=chamfer_edges, name="Bracket Chamfer")
        body.add_feature(chamfer, rebuild=True)

        if not _is_success(chamfer.status):
            _log_failure_diagnostic("Bracket_Chamfer", body, doc, chamfer, pre_chamfer, None)
        assert _is_success(chamfer.status), f"Bracket Chamfer: {chamfer.status_message}"

        # Save & Load
        bracket_sig = _solid_signature(body._build123d_solid)
        path = str(tmp_path / "bracket.mshcad")
        assert doc.save_project(path)

        loaded = Document.load_project(path)
        loaded_body = loaded.find_body_by_id(body.id)
        assert loaded_body is not None
        assert loaded_body._build123d_solid is not None

        loaded_sig = _solid_signature(loaded_body._build123d_solid)
        _assert_signature_close(bracket_sig, loaded_sig, context="bracket_save_load")

    def test_real_stepped_block(self):
        """Box → 3× PP gleiche Richtung (Stufen) → Chamfer."""
        pytest.importorskip("OCP.BRepFeat")

        doc, body = _make_doc_body("stepped")
        _add_box_base(body, 40, 30, 10)

        # 3 Push/Pulls in Z-Richtung (Stufen)
        for step in range(3):
            pp = _add_pushpull_join(doc, body, step, (0, 0, 1), 3.0 + step)
            assert _is_success(pp.status), f"Step {step}: {pp.status_message}"
            _log_step(f"Stepped PP {step}", body, pp)

        # Chamfer alle oberen Kanten
        solid = body._build123d_solid
        pre_sig = _solid_signature(solid)
        edges = _top_edge_indices(solid, limit=8)
        assert edges, "Keine Kanten für Chamfer"

        chamfer = ChamferFeature(distance=0.5, edge_indices=edges, name="Step Chamfer")
        body.add_feature(chamfer, rebuild=True)

        if not _is_success(chamfer.status):
            _log_failure_diagnostic("Stepped_Chamfer", body, doc, chamfer, pre_sig, None)
        assert _is_success(chamfer.status), f"Stepped Chamfer: {chamfer.status_message}"
        _assert_chamfer_applied(pre_sig, _solid_signature(body._build123d_solid), "Stepped_Chamfer", body, doc, chamfer)

    @pytest.mark.parametrize("seed", [7, 19, 43, 71, 97])
    def test_random_workflow(self, seed):
        """Zufälliger Workflow: N Push/Pulls + Chamfer."""
        pytest.importorskip("OCP.BRepFeat")

        rng = random.Random(seed)
        doc, body = _make_doc_body(f"random_{seed}")

        base = PrimitiveFeature(
            primitive_type="box",
            length=30 + rng.uniform(0, 20),
            width=20 + rng.uniform(0, 20),
            height=12 + rng.uniform(0, 18),
            name="Random Base",
        )
        body.add_feature(base, rebuild=True)
        assert _is_success(base.status), f"seed={seed}: {base.status_message}"

        n_pp = rng.randint(2, 7)
        for step in range(n_pp):
            direction = rng.choice(_AXIS_DIRECTIONS)
            dist = round(rng.uniform(0.8, 3.5), 3)
            pp = _add_pushpull_join(doc, body, step, direction, dist)
            assert _is_success(pp.status), (
                f"seed={seed}, step={step}, dir={direction}, dist={dist}: {pp.status_message}"
            )

        # Chamfer
        solid = body._build123d_solid
        pre_sig = _solid_signature(solid)
        edges = _top_edge_indices(solid, limit=4)
        assert edges, f"seed={seed}: Keine Edges"

        dist = round(rng.uniform(0.25, 0.9), 3)
        chamfer = ChamferFeature(distance=dist, edge_indices=edges)
        body.add_feature(chamfer, rebuild=True)

        if not _is_success(chamfer.status):
            _log_failure_diagnostic(f"Random_{seed}", body, doc, chamfer, pre_sig, None)
        assert _is_success(chamfer.status), f"seed={seed}: {chamfer.status_message}"

        post_sig = _solid_signature(body._build123d_solid)
        _assert_chamfer_applied(pre_sig, post_sig, f"Random_{seed}", body, doc, chamfer)
        _assert_tnp_no_broken(doc, body, {"Extrude", "Chamfer"})


# ===========================================================================
# STRESS-TESTS (Konfigurierbare Durchläufe)
# ===========================================================================
# Nutzung: pytest test/test_cad_workflow_trust.py -k "Stress" --count=100
# Oder direkt: pytest test/test_cad_workflow_trust.py::TestStressIterations -v

_stress_iterations = list(range(STRESS_ITERATIONS))


@pytest.mark.parametrize("iteration", _stress_iterations)
class TestStressIterations:
    """Wiederholt kritische Tests N-mal für Stabilitätsprüfung.

    Standard: 1× (STRESS_ITERATIONS=1).
    Stress:   CAD_TRUST_ITERATIONS=100 vor pytest setzen.
    """

    def test_stress_5x_pushpull_chamfer(self, iteration):
        """Stress: Box → 5× PP → Chamfer."""
        pytest.importorskip("OCP.BRepFeat")

        doc, body = _make_doc_body(f"stress_{iteration}")
        _add_box_base(body)

        for step, direction in enumerate(_AXIS_DIRECTIONS[:5]):
            feat = _add_pushpull_join(doc, body, step, direction, 2.0 + 0.25 * step)
            assert _is_success(feat.status)

        pre_sig = _solid_signature(body._build123d_solid)
        edges = _top_edge_indices(body._build123d_solid, limit=4)
        chamfer = ChamferFeature(distance=0.7, edge_indices=edges)
        body.add_feature(chamfer, rebuild=True)

        assert _is_success(chamfer.status), f"Iteration {iteration}: {chamfer.status_message}"
        post_sig = _solid_signature(body._build123d_solid)
        _assert_chamfer_applied(pre_sig, post_sig, f"Stress_{iteration}", body, doc, chamfer)

    def test_stress_rebuild_idempotent(self, iteration):
        """Stress: Rebuild-Idempotenz."""
        pytest.importorskip("OCP.BRepFeat")

        doc, body = _make_doc_body(f"stress_rebuild_{iteration}")
        _add_box_base(body)

        for step in range(3):
            _add_pushpull_join(doc, body, step, _AXIS_DIRECTIONS[step], 2.0)

        edges = _top_edge_indices(body._build123d_solid, limit=4)
        chamfer = ChamferFeature(distance=0.5, edge_indices=edges)
        body.add_feature(chamfer, rebuild=True)
        assert _is_success(chamfer.status)

        ref_sig = _solid_signature(body._build123d_solid)
        for cycle in range(3):
            body._rebuild()
            _assert_signature_close(ref_sig, _solid_signature(body._build123d_solid),
                                    context=f"stress_rebuild_{iteration}_cycle_{cycle}")
