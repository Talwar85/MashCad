import pytest
import random
from shapely.geometry import Polygon

from modeling import Body, ChamferFeature, Document, ExtrudeFeature, FilletFeature, PrimitiveFeature
from modeling.geometric_selector import GeometricFaceSelector
from modeling.topology_indexing import edge_index_of, face_index_of
from modeling.tnp_system import ShapeType

_AXIS_DIRECTIONS = (
    (1.0, 0.0, 0.0),
    (-1.0, 0.0, 0.0),
    (0.0, 1.0, 0.0),
    (0.0, -1.0, 0.0),
    (0.0, 0.0, 1.0),
    (0.0, 0.0, -1.0),
)


class _DummyBrowser:
    def refresh(self):
        return None


class _DummyMainWindow:
    def __init__(self):
        self.browser = _DummyBrowser()
        self.viewport_3d = type("_Viewport", (), {"remove_body": lambda self, _bid: None})()

    def _update_body_from_build123d(self, _body, _solid):
        return None


def _is_success_status(status: str) -> bool:
    return str(status or "").upper() in {"OK", "SUCCESS"}


def _pick_face_by_direction(solid, direction):
    dx, dy, dz = direction
    return max(
        list(solid.faces()),
        key=lambda f: (float(f.center().X) * dx)
        + (float(f.center().Y) * dy)
        + (float(f.center().Z) * dz),
    )


def _register_face_shape_id(doc: Document, face, feature_seed: str, local_index: int):
    fc = face.center()
    return doc._shape_naming_service.register_shape(
        ocp_shape=face.wrapped,
        shape_type=ShapeType.FACE,
        feature_id=feature_seed,
        local_index=int(local_index),
        geometry_data=(float(fc.X), float(fc.Y), float(fc.Z), float(face.area)),
    )


def _add_pushpull_join(doc: Document, body: Body, step: int, direction, distance: float) -> ExtrudeFeature:
    solid = body._build123d_solid
    assert solid is not None

    face = _pick_face_by_direction(solid, direction)
    face_idx = face_index_of(solid, face)
    assert face_idx is not None
    face_idx = int(face_idx)

    shape_id = _register_face_shape_id(doc, face, f"trust_seed_{step}", face_idx)
    # Realistic payload: GUI stores projected polygons as WKT-serializable shapely polygons.
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


def _loop_edge_indices_for_face_direction(solid, direction, limit: int = 4):
    face = _pick_face_by_direction(solid, direction)
    indices = []
    for edge in face.edges():
        edge_idx = edge_index_of(solid, edge)
        if edge_idx is None:
            continue
        idx = int(edge_idx)
        if idx not in indices:
            indices.append(idx)
        if len(indices) >= limit:
            break
    return indices


def _random_chamfer_edges_from_face_loop(solid, rng: random.Random):
    direction = rng.choice(_AXIS_DIRECTIONS)
    loop = _loop_edge_indices_for_face_direction(solid, direction, limit=8)
    assert loop, "expected at least one edge for random chamfer selection"

    mode = rng.choice(("single", "subset", "loop4"))
    if mode == "single" or len(loop) == 1:
        return [rng.choice(loop)]
    if mode == "loop4" and len(loop) >= 4:
        return loop[:4]

    k = rng.randint(1, min(4, len(loop)))
    return rng.sample(loop, k=k)


def _safe_random_fillet_radius(solid, edge_indices, rng: random.Random) -> float:
    edges = list(solid.edges())
    lengths = []
    for idx in edge_indices:
        if 0 <= int(idx) < len(edges):
            edge = edges[int(idx)]
            length = float(getattr(edge, "length", 0.0) or 0.0)
            if length > 1e-6:
                lengths.append(length)

    # Fail-safe bounds: keep radius small compared to shortest selected edge.
    min_len = min(lengths) if lengths else 1.0
    upper = min(0.8, max(0.12, 0.12 * min_len))
    lower = min(0.08, upper)
    return round(rng.uniform(lower, upper), 4)


def _solid_signature(solid):
    assert solid is not None
    bb = solid.bounding_box()
    return {
        "volume": float(solid.volume),
        "faces": len(list(solid.faces())),
        "edges": len(list(solid.edges())),
        "bbox": (
            float(bb.min.X),
            float(bb.min.Y),
            float(bb.min.Z),
            float(bb.max.X),
            float(bb.max.Y),
            float(bb.max.Z),
        ),
    }


def _bbox_lengths(sig: dict) -> tuple[float, float, float]:
    bb = sig["bbox"]
    return (
        float(bb[3] - bb[0]),
        float(bb[4] - bb[1]),
        float(bb[5] - bb[2]),
    )


def _bbox_diag(sig: dict) -> float:
    lx, ly, lz = _bbox_lengths(sig)
    return (lx * lx + ly * ly + lz * lz) ** 0.5


def _bbox_center(sig: dict) -> tuple[float, float, float]:
    bb = sig["bbox"]
    return (
        0.5 * float(bb[0] + bb[3]),
        0.5 * float(bb[1] + bb[4]),
        0.5 * float(bb[2] + bb[5]),
    )


def _assert_local_modifier_keeps_body_scale(pre_sig: dict, post_sig: dict, *, magnitude: float, context: str):
    """
    Chamfer/Fillet must behave as local edge modifiers.
    They must not cause large bbox growth/shrink or large global center shifts.
    """
    mag = max(0.0, float(magnitude))
    max_axis_grow = max(0.15, 0.35 * mag)
    max_axis_shrink = max(1.25, 5.0 * mag)
    max_diag_grow = max(0.20, 0.60 * mag)
    max_diag_shrink = max(1.80, 7.0 * mag)
    max_center_shift = max(1.20, 4.0 * mag)

    pre_l = _bbox_lengths(pre_sig)
    post_l = _bbox_lengths(post_sig)

    for axis, (before, after) in enumerate(zip(pre_l, post_l)):
        grow = after - before
        shrink = before - after
        assert grow <= max_axis_grow, (
            f"{context}: bbox axis {axis} grew too much ({grow:.3f}mm > {max_axis_grow:.3f}mm) "
            f"for local modifier magnitude={mag:.3f}"
        )
        assert shrink <= max_axis_shrink, (
            f"{context}: bbox axis {axis} shrank too much ({shrink:.3f}mm > {max_axis_shrink:.3f}mm) "
            f"for local modifier magnitude={mag:.3f}"
        )

    pre_diag = _bbox_diag(pre_sig)
    post_diag = _bbox_diag(post_sig)
    diag_grow = post_diag - pre_diag
    diag_shrink = pre_diag - post_diag
    assert diag_grow <= max_diag_grow, (
        f"{context}: bbox diagonal grew too much ({diag_grow:.3f}mm > {max_diag_grow:.3f}mm)"
    )
    assert diag_shrink <= max_diag_shrink, (
        f"{context}: bbox diagonal shrank too much ({diag_shrink:.3f}mm > {max_diag_shrink:.3f}mm)"
    )

    pre_c = _bbox_center(pre_sig)
    post_c = _bbox_center(post_sig)
    center_shift = (
        (post_c[0] - pre_c[0]) ** 2
        + (post_c[1] - pre_c[1]) ** 2
        + (post_c[2] - pre_c[2]) ** 2
    ) ** 0.5
    assert center_shift <= max_center_shift, (
        f"{context}: bbox center shifted too much ({center_shift:.3f}mm > {max_center_shift:.3f}mm)"
    )


def _assert_signature_close(a: dict, b: dict, *, context: str):
    assert a["faces"] == b["faces"], f"{context}: face-count mismatch live={a} replay={b}"
    assert a["edges"] == b["edges"], f"{context}: edge-count mismatch live={a} replay={b}"
    assert a["volume"] == pytest.approx(b["volume"], rel=1e-6, abs=1e-6), (
        f"{context}: volume mismatch live={a} replay={b}"
    )
    for i, (av, bv) in enumerate(zip(a["bbox"], b["bbox"])):
        assert av == pytest.approx(bv, rel=1e-6, abs=1e-6), (
            f"{context}: bbox[{i}] mismatch live={a} replay={b}"
        )


def _clone_and_rebuild(body: Body, *, name: str):
    clone_doc = Document(name)
    clone = Body.from_dict(body.to_dict())
    clone_doc.add_body(clone, set_active=True)
    clone._rebuild()
    return clone_doc, clone


def _assert_rebuild_replay_matches_live(body: Body, *, context: str):
    live_sig = _solid_signature(body._build123d_solid)
    _clone_doc, replayed = _clone_and_rebuild(body, name=f"{context}_probe")
    replay_sig = _solid_signature(replayed._build123d_solid)
    _assert_signature_close(live_sig, replay_sig, context=context)


def _add_pushpull_join_live_skip_rebuild(doc: Document, body: Body, step: int, direction, distance: float) -> ExtrudeFeature:
    """
    Simulates GUI live Push/Pull path:
    1. BRepFeat directly updates body solid
    2. Feature is appended with rebuild=False (history replay happens later)
    """
    solid = body._build123d_solid
    assert solid is not None

    face = _pick_face_by_direction(solid, direction)
    face_idx = face_index_of(solid, face)
    assert face_idx is not None
    face_idx = int(face_idx)

    service = doc._shape_naming_service
    shape_id = service.find_shape_id_by_face(face, require_exact=True)
    if shape_id is None:
        fc = face.center()
        feature_seed = body.features[-1].id if body.features else body.id
        shape_id = service.register_shape(
            ocp_shape=face.wrapped,
            shape_type=ShapeType.FACE,
            feature_id=feature_seed,
            local_index=face_idx,
            geometry_data=(float(fc.X), float(fc.Y), float(fc.Z), float(face.area)),
        )

    feat = ExtrudeFeature(
        sketch=None,
        distance=float(distance),
        operation="Join",
        face_index=face_idx,
        face_shape_id=shape_id,
        face_selector=GeometricFaceSelector.from_face(face).to_dict(),
        precalculated_polys=[Polygon([(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)])],
        name=f"Push/Pull Live {step}",
    )

    result = body._compute_extrude_part_brepfeat(feat, solid)
    assert result is not None

    body._build123d_solid = result
    if hasattr(result, "wrapped"):
        body.shape = result.wrapped
    body.invalidate_mesh()
    body.add_feature(feat, rebuild=False)
    return feat


def _add_pushpull_join_live_via_command(
    doc: Document,
    body: Body,
    ui: _DummyMainWindow,
    step: int,
    direction,
    distance: float,
):
    from gui.commands.feature_commands import AddFeatureCommand

    solid = body._build123d_solid
    assert solid is not None

    face = _pick_face_by_direction(solid, direction)
    face_idx = face_index_of(solid, face)
    assert face_idx is not None
    face_idx = int(face_idx)

    service = doc._shape_naming_service
    shape_id = service.find_shape_id_by_face(face, require_exact=True)
    if shape_id is None:
        fc = face.center()
        feature_seed = body.features[-1].id if body.features else body.id
        shape_id = service.register_shape(
            ocp_shape=face.wrapped,
            shape_type=ShapeType.FACE,
            feature_id=feature_seed,
            local_index=face_idx,
            geometry_data=(float(fc.X), float(fc.Y), float(fc.Z), float(face.area)),
        )

    feat = ExtrudeFeature(
        sketch=None,
        distance=float(distance),
        operation="Join",
        face_index=face_idx,
        face_shape_id=shape_id,
        face_selector=GeometricFaceSelector.from_face(face).to_dict(),
        precalculated_polys=[Polygon([(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)])],
        name=f"Push/Pull Live Cmd {step}",
    )

    result = body._compute_extrude_part_brepfeat(feat, solid)
    assert result is not None

    # Simuliert MainWindow Push/Pull BRepFeat-Pfad: Solid zuerst live updaten,
    # dann Command mit skip_rebuild=True auf den Undo-Stack legen.
    body._build123d_solid = result
    if hasattr(result, "wrapped"):
        body.shape = result.wrapped
    body.invalidate_mesh()

    cmd = AddFeatureCommand(body, feat, ui, description=f"Push/Pull ({step})", skip_rebuild=True)
    cmd.redo()
    assert feat in body.features
    assert _is_success_status(getattr(feat, "status", "OK"))
    return feat, cmd


def _assert_no_broken_feature_refs(report: dict, include_types: set[str]):
    features = [f for f in report.get("features", []) if f.get("type") in include_types]
    assert features, f"Expected feature types missing: {include_types}"
    for feat in features:
        assert feat.get("status") != "broken", f"Broken feature report: {feat}"
        assert int(feat.get("broken", 0)) == 0, f"Broken refs for feature: {feat}"


def test_trust_gate_brepfeat_uses_kernel_history_tracking():
    pytest.importorskip("OCP.BRepFeat")

    doc = Document("trust_gate_brepfeat_history")
    body = Body("BodyHistory", document=doc)
    doc.add_body(body, set_active=True)

    base = PrimitiveFeature(primitive_type="box", length=42.0, width=28.0, height=18.0, name="Base Box")
    body.add_feature(base, rebuild=True)
    assert _is_success_status(base.status), base.status_message

    feat = _add_pushpull_join_live_skip_rebuild(
        doc,
        body,
        step=0,
        direction=(1.0, 0.0, 0.0),
        distance=2.2,
    )
    assert _is_success_status(feat.status), feat.status_message

    op = doc._shape_naming_service.get_last_operation()
    assert op is not None
    assert op.operation_type == "BREPFEAT_PRISM"
    assert op.feature_id == feat.id
    assert op.occt_history is not None
    assert str(op.metadata.get("mapping_mode", "")).lower() == "history"


def test_trust_gate_health_report_marks_geometry_drift_code_as_broken():
    doc = Document("trust_gate_drift_code")
    body = Body("BodyDrift", document=doc)
    doc.add_body(body, set_active=True)

    base = PrimitiveFeature(primitive_type="box", length=20.0, width=16.0, height=10.0, name="Base Box")
    body.add_feature(base, rebuild=True)
    assert _is_success_status(base.status), base.status_message

    # Simuliert einen strikt verworfenen lokalen Modifier.
    fake = ChamferFeature(distance=0.4, edge_indices=[0])
    fake.name = "Chamfer Drift"
    fake.status = "ERROR"
    fake.status_message = "Strict Self-Heal rollback due to geometry drift"
    fake.status_details = {
        "code": "self_heal_rollback_geometry_drift",
        "refs": {"edge_indices": [0]},
    }
    body.features.append(fake)

    report = doc._shape_naming_service.get_health_report(body)
    chamfer_reports = [f for f in report.get("features", []) if f.get("name") == "Chamfer Drift"]
    assert chamfer_reports, report
    chamfer_report = chamfer_reports[0]
    assert chamfer_report.get("status") == "broken", chamfer_report
    assert int(chamfer_report.get("broken", 0)) > 0, chamfer_report


def test_trust_gate_panel_maps_geometry_drift_code_to_broken():
    panel_mod = pytest.importorskip("gui.widgets.tnp_stats_panel")
    feat = {
        "status": "ok",
        "status_details": {"code": "self_heal_rollback_geometry_drift"},
    }
    assert panel_mod.TNPStatsPanel._feature_display_status(feat) == "broken"


@pytest.mark.parametrize("seed", [11, 37, 59, 83, 107, 131, 173])
def test_trust_gate_ui_workflow_five_pushpull_chamfer_panel_consistency(seed):
    """
    Reproduziert den realen GUI-Flow:
    5x Push/Pull -> Chamfer -> Undo/Redo.

    Ziel:
    - Kein stilles "alles grün", wenn Geometrie driftet.
    - Bei Erfolg: lokale Modifier bleiben lokal.
    - Bei Fehler: harter Rollback + Panel zeigt broken.
    """
    pytest.importorskip("OCP.BRepFeat")
    panel_mod = pytest.importorskip("gui.widgets.tnp_stats_panel")

    from gui.commands.feature_commands import AddFeatureCommand

    rng = random.Random(seed)
    doc = Document(f"trust_gate_ui_flow_{seed}")
    body = Body(f"BodyUI{seed}", document=doc)
    doc.add_body(body, set_active=True)
    ui = _DummyMainWindow()

    base = PrimitiveFeature(
        primitive_type="box",
        length=30.0 + rng.uniform(0.0, 20.0),
        width=20.0 + rng.uniform(0.0, 20.0),
        height=12.0 + rng.uniform(0.0, 18.0),
        name="Base Box",
    )
    body.add_feature(base, rebuild=True)
    assert _is_success_status(base.status), f"seed={seed}: {base.status_message}"

    for step in range(5):
        direction = rng.choice(_AXIS_DIRECTIONS)
        distance = round(rng.uniform(0.8, 3.4), 3)
        feat, _cmd = _add_pushpull_join_live_via_command(
            doc,
            body,
            ui,
            step,
            direction,
            distance=distance,
        )
        assert _is_success_status(feat.status), (
            f"seed={seed}, step={step}, dir={direction}, dist={distance}: {feat.status_message}"
        )

    pre_sig = _solid_signature(body._build123d_solid)
    chamfer_edges = _random_chamfer_edges_from_face_loop(body._build123d_solid, rng)
    chamfer_distance = 2.0

    chamfer = ChamferFeature(distance=chamfer_distance, edge_indices=chamfer_edges)
    cmd = AddFeatureCommand(body, chamfer, ui, description=f"Chamfer UI seed={seed}")
    cmd.redo()
    post_sig = _solid_signature(body._build123d_solid)

    report_after = doc._shape_naming_service.get_health_report(body)
    feature_reports = [
        f for f in report_after.get("features", [])
        if f.get("type") in {"Extrude", "Chamfer"}
    ]
    assert feature_reports, f"seed={seed}: expected Extrude/Chamfer entries in TNP report"

    if _is_success_status(chamfer.status):
        _assert_local_modifier_keeps_body_scale(
            pre_sig,
            post_sig,
            magnitude=chamfer_distance,
            context=f"ui_seed_{seed}_chamfer_scale_guard",
        )
        # Kein Push/Pull darf als broken angezeigt werden.
        for feat_report in feature_reports:
            if feat_report.get("type") != "Extrude":
                continue
            disp = panel_mod.TNPStatsPanel._feature_display_status(feat_report)
            assert disp != "broken", (
                f"seed={seed}: panel marks Push/Pull broken despite successful workflow: {feat_report}"
            )

        cmd.undo()
        undo_sig = _solid_signature(body._build123d_solid)
        _assert_signature_close(undo_sig, pre_sig, context=f"ui_seed_{seed}_undo")

        cmd.redo()
        redo_sig = _solid_signature(body._build123d_solid)
        _assert_signature_close(redo_sig, post_sig, context=f"ui_seed_{seed}_redo")
    else:
        # Fehlerpfad: Geometrie darf nicht mutieren + Panel muss broken anzeigen.
        _assert_signature_close(post_sig, pre_sig, context=f"ui_seed_{seed}_error_rollback")

        chamfer_reports = [f for f in feature_reports if f.get("type") == "Chamfer"]
        assert chamfer_reports, f"seed={seed}: missing chamfer report after error"
        disp = panel_mod.TNPStatsPanel._feature_display_status(chamfer_reports[-1])
        assert disp == "broken", (
            f"seed={seed}: panel must show broken when chamfer fails: {chamfer_reports[-1]}"
        )

        cmd.undo()
        undo_sig = _solid_signature(body._build123d_solid)
        _assert_signature_close(undo_sig, pre_sig, context=f"ui_seed_{seed}_undo_after_error")

        cmd.redo()
        redo_sig = _solid_signature(body._build123d_solid)
        _assert_signature_close(redo_sig, pre_sig, context=f"ui_seed_{seed}_redo_after_error")


def test_trust_gate_rect_pushpull_chamfer_undo_redo_save_load_and_continue(tmp_path):
    pytest.importorskip("OCP.BRepFeat")

    doc = Document("trust_gate_rect")
    body = Body("BodyTrust", document=doc)
    doc.add_body(body, set_active=True)

    base = PrimitiveFeature(primitive_type="box", length=40.0, width=28.0, height=18.0, name="Base Box")
    body.add_feature(base, rebuild=True)
    assert _is_success_status(base.status), base.status_message
    assert body._build123d_solid is not None

    directions = [
        (0.0, 1.0, 0.0),
        (1.0, 0.0, 0.0),
        (0.0, 0.0, 1.0),
        (-1.0, 0.0, 0.0),
        (0.0, -1.0, 0.0),
    ]
    for step, direction in enumerate(directions):
        pushpull = _add_pushpull_join(doc, body, step, direction, distance=2.0 + (0.25 * step))
        assert _is_success_status(pushpull.status), pushpull.status_message

    solid = body._build123d_solid
    assert solid is not None and float(solid.volume) > 0.0

    edge_indices = _top_edge_indices(solid, limit=4)
    assert edge_indices
    chamfer = ChamferFeature(distance=0.8, edge_indices=edge_indices)
    body.add_feature(chamfer, rebuild=True)
    assert _is_success_status(chamfer.status), chamfer.status_message

    report = doc._shape_naming_service.get_health_report(body)
    _assert_no_broken_feature_refs(report, {"Extrude", "Chamfer"})

    # Undo (simulate command effect): remove chamfer and rebuild.
    removed = body.features.pop()
    assert removed is chamfer
    body._rebuild()
    assert body._build123d_solid is not None
    assert all(
        _is_success_status(feat.status) for feat in body.features if isinstance(feat, (PrimitiveFeature, ExtrudeFeature))
    )

    # Redo (simulate command effect): re-add same chamfer and rebuild.
    body.features.append(chamfer)
    body._rebuild()
    assert _is_success_status(chamfer.status), chamfer.status_message

    report_after_redo = doc._shape_naming_service.get_health_report(body)
    _assert_no_broken_feature_refs(report_after_redo, {"Extrude", "Chamfer"})

    save_path = tmp_path / "trust_gate_rect_pushpull_chamfer.mshcad"
    assert doc.save_project(str(save_path)) is True
    loaded = Document.load_project(str(save_path))
    assert loaded is not None

    loaded_body = loaded.find_body_by_id(body.id)
    assert loaded_body is not None
    loaded_report = loaded._shape_naming_service.get_health_report(loaded_body)
    _assert_no_broken_feature_refs(loaded_report, {"Extrude", "Chamfer"})

    # Continue modeling after load: one more Push/Pull must work without missing ref errors.
    post_load_pushpull = _add_pushpull_join(loaded, loaded_body, 99, (0.0, 1.0, 0.0), distance=1.4)
    assert _is_success_status(post_load_pushpull.status), post_load_pushpull.status_message
    assert "referenz" not in (post_load_pushpull.status_message or "").lower()

    post_load_report = loaded._shape_naming_service.get_health_report(loaded_body)
    _assert_no_broken_feature_refs(post_load_report, {"Extrude", "Chamfer"})


def test_trust_gate_live_pushpull_skip_rebuild_replay_is_consistent():
    pytest.importorskip("OCP.BRepFeat")

    doc = Document("trust_gate_live_pushpull")
    body = Body("BodyLive", document=doc)
    doc.add_body(body, set_active=True)

    base = PrimitiveFeature(primitive_type="box", length=40.0, width=28.0, height=18.0, name="Base Box")
    body.add_feature(base, rebuild=True)
    assert _is_success_status(base.status), base.status_message

    directions = [
        (0.0, 1.0, 0.0),
        (1.0, 0.0, 0.0),
        (0.0, 0.0, 1.0),
        (-1.0, 0.0, 0.0),
        (0.0, -1.0, 0.0),
    ]
    for step, direction in enumerate(directions):
        feat = _add_pushpull_join_live_skip_rebuild(doc, body, step, direction, distance=2.0 + (0.25 * step))
        assert _is_success_status(feat.status), feat.status_message
        _assert_rebuild_replay_matches_live(body, context=f"live_pushpull_step_{step}")


def test_trust_gate_live_pushpull_then_chamfer_and_fillet():
    pytest.importorskip("OCP.BRepFeat")

    doc = Document("trust_gate_live_post_edges")
    body = Body("BodyLiveEdges", document=doc)
    doc.add_body(body, set_active=True)

    base = PrimitiveFeature(primitive_type="box", length=38.0, width=24.0, height=16.0, name="Base Box")
    body.add_feature(base, rebuild=True)
    assert _is_success_status(base.status), base.status_message

    for step, direction in enumerate([(0.0, 1.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (-1.0, 0.0, 0.0)]):
        feat = _add_pushpull_join_live_skip_rebuild(doc, body, step, direction, distance=1.6 + (0.2 * step))
        assert _is_success_status(feat.status), feat.status_message

    # Branch 1: Chamfer after live push/pull history.
    chamfer_doc, chamfer_body = _clone_and_rebuild(body, name="live_chamfer_branch")
    chamfer_edges = _top_edge_indices(chamfer_body._build123d_solid, limit=4)
    assert chamfer_edges
    chamfer = ChamferFeature(distance=0.7, edge_indices=chamfer_edges)
    chamfer_body.add_feature(chamfer, rebuild=True)
    assert _is_success_status(chamfer.status), chamfer.status_message
    chamfer_report = chamfer_doc._shape_naming_service.get_health_report(chamfer_body)
    _assert_no_broken_feature_refs(chamfer_report, {"Extrude", "Chamfer"})

    # Branch 2: Fillet after live push/pull history.
    fillet_doc, fillet_body = _clone_and_rebuild(body, name="live_fillet_branch")
    fillet_edges = _top_edge_indices(fillet_body._build123d_solid, limit=4)
    assert fillet_edges
    fillet = FilletFeature(radius=0.6, edge_indices=fillet_edges)
    fillet_body.add_feature(fillet, rebuild=True)
    assert _is_success_status(fillet.status), fillet.status_message
    fillet_report = fillet_doc._shape_naming_service.get_health_report(fillet_body)
    _assert_no_broken_feature_refs(fillet_report, {"Extrude", "Fillet"})


def test_trust_gate_live_pushpull_chamfer_undo_redo_is_geometry_stable():
    pytest.importorskip("OCP.BRepFeat")

    doc = Document("trust_gate_live_undo_redo")
    body = Body("BodyLiveUndoRedo", document=doc)
    doc.add_body(body, set_active=True)

    base = PrimitiveFeature(primitive_type="box", length=40.0, width=28.0, height=18.0, name="Base Box")
    body.add_feature(base, rebuild=True)
    assert _is_success_status(base.status), base.status_message

    # Matches the problematic user flow: several live Push/Pulls before edge ops.
    directions = [
        (0.0, 1.0, 0.0),
        (1.0, 0.0, 0.0),
        (0.0, 0.0, 1.0),
        (-1.0, 0.0, 0.0),
        (0.0, -1.0, 0.0),
    ]
    for step, direction in enumerate(directions):
        feat = _add_pushpull_join_live_skip_rebuild(doc, body, step, direction, distance=1.8 + (0.2 * step))
        assert _is_success_status(feat.status), feat.status_message

    pre_chamfer_sig = _solid_signature(body._build123d_solid)

    chamfer_edges = _top_edge_indices(body._build123d_solid, limit=4)
    assert len(chamfer_edges) == 4
    chamfer = ChamferFeature(distance=0.7, edge_indices=chamfer_edges)
    body.add_feature(chamfer, rebuild=True)
    assert _is_success_status(chamfer.status), chamfer.status_message

    post_chamfer_sig = _solid_signature(body._build123d_solid)
    assert post_chamfer_sig["faces"] >= pre_chamfer_sig["faces"]
    assert post_chamfer_sig["volume"] < pre_chamfer_sig["volume"]

    report_after_chamfer = doc._shape_naming_service.get_health_report(body)
    _assert_no_broken_feature_refs(report_after_chamfer, {"Extrude", "Chamfer"})

    # Undo chamfer (same behavior as command path: remove feature and rebuild).
    removed = body.features.pop()
    assert removed is chamfer
    body._rebuild()
    undo_sig = _solid_signature(body._build123d_solid)
    _assert_signature_close(undo_sig, pre_chamfer_sig, context="live_chamfer_undo")

    report_after_undo = doc._shape_naming_service.get_health_report(body)
    _assert_no_broken_feature_refs(report_after_undo, {"Extrude"})

    # Redo chamfer: re-append same feature and rebuild.
    body.features.append(chamfer)
    body._rebuild()
    redo_sig = _solid_signature(body._build123d_solid)
    _assert_signature_close(redo_sig, post_chamfer_sig, context="live_chamfer_redo")

    report_after_redo = doc._shape_naming_service.get_health_report(body)
    _assert_no_broken_feature_refs(report_after_redo, {"Extrude", "Chamfer"})


def test_trust_gate_tnp_registry_is_idempotent_across_rebuild_cycles():
    pytest.importorskip("OCP.BRepFeat")

    doc = Document("trust_gate_registry_idempotent")
    body = Body("BodyRegistryStable", document=doc)
    doc.add_body(body, set_active=True)

    base = PrimitiveFeature(primitive_type="box", length=40.0, width=30.0, height=20.0, name="Base Box")
    body.add_feature(base, rebuild=True)
    assert _is_success_status(base.status), base.status_message

    directions = [
        (0.0, 1.0, 0.0),
        (1.0, 0.0, 0.0),
        (0.0, 0.0, 1.0),
        (-1.0, 0.0, 0.0),
        (0.0, -1.0, 0.0),
    ]
    for step, direction in enumerate(directions):
        feat = _add_pushpull_join_live_skip_rebuild(doc, body, step, direction, distance=1.7 + (0.2 * step))
        assert _is_success_status(feat.status), feat.status_message

    chamfer_edges = _top_edge_indices(body._build123d_solid, limit=4)
    assert len(chamfer_edges) == 4
    chamfer = ChamferFeature(distance=0.8, edge_indices=chamfer_edges)
    body.add_feature(chamfer, rebuild=True)
    assert _is_success_status(chamfer.status), chamfer.status_message

    # Warmup rebuild once, then stats must stay stable across repeated rebuilds.
    body._rebuild()
    baseline = doc._shape_naming_service.get_stats()

    for _ in range(4):
        body._rebuild()

    after = doc._shape_naming_service.get_stats()
    assert after["edges"] == baseline["edges"], (
        f"TNP edge registry grew across idempotent rebuilds: {baseline['edges']} -> {after['edges']}"
    )
    assert after["operations"] == baseline["operations"], (
        f"TNP operation graph grew across idempotent rebuilds: "
        f"{baseline['operations']} -> {after['operations']}"
    )


def test_trust_gate_gui_command_flow_5x_pushpull_then_chamfer_undo_redo():
    pytest.importorskip("OCP.BRepFeat")

    from gui.commands.feature_commands import AddFeatureCommand

    doc = Document("trust_gate_gui_cmd_flow")
    body = Body("BodyGuiCmd", document=doc)
    doc.add_body(body, set_active=True)
    ui = _DummyMainWindow()

    base = PrimitiveFeature(primitive_type="box", length=40.0, width=28.0, height=18.0, name="Base Box")
    body.add_feature(base, rebuild=True)
    assert _is_success_status(base.status), base.status_message

    directions = [
        (0.0, 1.0, 0.0),
        (1.0, 0.0, 0.0),
        (0.0, 0.0, 1.0),
        (-1.0, 0.0, 0.0),
        (0.0, -1.0, 0.0),
    ]
    for step, direction in enumerate(directions):
        feat, _cmd = _add_pushpull_join_live_via_command(
            doc,
            body,
            ui,
            step,
            direction,
            distance=2.0 + (0.2 * step),
        )
        assert _is_success_status(feat.status), feat.status_message

    pre_chamfer_sig = _solid_signature(body._build123d_solid)
    pre_report = doc._shape_naming_service.get_health_report(body)
    _assert_no_broken_feature_refs(pre_report, {"Extrude"})

    chamfer_edges = _top_edge_indices(body._build123d_solid, limit=4)
    assert len(chamfer_edges) == 4
    chamfer = ChamferFeature(distance=0.7, edge_indices=chamfer_edges)

    chamfer_cmd = AddFeatureCommand(body, chamfer, ui, description="Chamfer R=0.7")
    chamfer_cmd.redo()
    assert _is_success_status(chamfer.status), chamfer.status_message

    post_chamfer_sig = _solid_signature(body._build123d_solid)
    assert post_chamfer_sig["faces"] >= pre_chamfer_sig["faces"]
    assert post_chamfer_sig["volume"] < pre_chamfer_sig["volume"]
    report_after_chamfer = doc._shape_naming_service.get_health_report(body)
    _assert_no_broken_feature_refs(report_after_chamfer, {"Extrude", "Chamfer"})

    chamfer_cmd.undo()
    undo_sig = _solid_signature(body._build123d_solid)
    _assert_signature_close(undo_sig, pre_chamfer_sig, context="gui_cmd_chamfer_undo")
    report_after_undo = doc._shape_naming_service.get_health_report(body)
    _assert_no_broken_feature_refs(report_after_undo, {"Extrude"})

    chamfer_cmd.redo()
    redo_sig = _solid_signature(body._build123d_solid)
    _assert_signature_close(redo_sig, post_chamfer_sig, context="gui_cmd_chamfer_redo")
    report_after_redo = doc._shape_naming_service.get_health_report(body)
    _assert_no_broken_feature_refs(report_after_redo, {"Extrude", "Chamfer"})

    stats_before_cycles = doc._shape_naming_service.get_stats()
    for _ in range(3):
        chamfer_cmd.undo()
        chamfer_cmd.redo()
    stats_after_cycles = doc._shape_naming_service.get_stats()
    assert stats_after_cycles["edges"] == stats_before_cycles["edges"], (
        f"TNP edge registry grew over GUI-like chamfer undo/redo cycles: "
        f"{stats_before_cycles['edges']} -> {stats_after_cycles['edges']}"
    )
    assert stats_after_cycles["operations"] == stats_before_cycles["operations"], (
        f"TNP operation graph grew over GUI-like chamfer undo/redo cycles: "
        f"{stats_before_cycles['operations']} -> {stats_after_cycles['operations']}"
    )


@pytest.mark.parametrize(
    "loop_face_direction",
    [
        (0.0, 0.0, 1.0),  # Top (Z)
        (1.0, 0.0, 0.0),  # Side (X)
    ],
)
def test_trust_gate_gui_loop_selection_top_or_side_face(loop_face_direction):
    pytest.importorskip("OCP.BRepFeat")

    from gui.commands.feature_commands import AddFeatureCommand

    doc = Document("trust_gate_gui_loop_select")
    body = Body("BodyLoopSelect", document=doc)
    doc.add_body(body, set_active=True)
    ui = _DummyMainWindow()

    base = PrimitiveFeature(primitive_type="box", length=40.0, width=28.0, height=18.0, name="Base Box")
    body.add_feature(base, rebuild=True)
    assert _is_success_status(base.status), base.status_message

    directions = [
        (0.0, 1.0, 0.0),
        (1.0, 0.0, 0.0),
        (0.0, 0.0, 1.0),
        (-1.0, 0.0, 0.0),
        (0.0, -1.0, 0.0),
    ]
    for step, direction in enumerate(directions):
        feat, _cmd = _add_pushpull_join_live_via_command(
            doc,
            body,
            ui,
            step,
            direction,
            distance=1.9 + (0.15 * step),
        )
        assert _is_success_status(feat.status), feat.status_message

    pre_chamfer_sig = _solid_signature(body._build123d_solid)

    # Entspricht dem realen User-Pattern: Face selektieren -> 4-Edge Loop.
    edge_loop = _loop_edge_indices_for_face_direction(body._build123d_solid, loop_face_direction, limit=4)
    assert len(edge_loop) == 4
    assert len(set(edge_loop)) == 4

    chamfer = ChamferFeature(distance=0.7, edge_indices=edge_loop)
    cmd = AddFeatureCommand(body, chamfer, ui, description="Chamfer Loop")
    cmd.redo()
    assert _is_success_status(chamfer.status), chamfer.status_message
    report_after_chamfer = doc._shape_naming_service.get_health_report(body)
    _assert_no_broken_feature_refs(report_after_chamfer, {"Extrude", "Chamfer"})

    post_chamfer_sig = _solid_signature(body._build123d_solid)
    assert post_chamfer_sig["faces"] >= pre_chamfer_sig["faces"]
    assert post_chamfer_sig["volume"] < pre_chamfer_sig["volume"]

    cmd.undo()
    undo_sig = _solid_signature(body._build123d_solid)
    _assert_signature_close(undo_sig, pre_chamfer_sig, context="gui_loop_chamfer_undo")
    report_after_undo = doc._shape_naming_service.get_health_report(body)
    _assert_no_broken_feature_refs(report_after_undo, {"Extrude"})

    cmd.redo()
    redo_sig = _solid_signature(body._build123d_solid)
    _assert_signature_close(redo_sig, post_chamfer_sig, context="gui_loop_chamfer_redo")
    report_after_redo = doc._shape_naming_service.get_health_report(body)
    _assert_no_broken_feature_refs(report_after_redo, {"Extrude", "Chamfer"})


@pytest.mark.parametrize(
    "single_edge_face_direction",
    [
        (0.0, 0.0, 1.0),  # Top (Z)
        (1.0, 0.0, 0.0),  # Side (X)
    ],
)
def test_trust_gate_gui_single_edge_selection_top_or_side_face(single_edge_face_direction):
    pytest.importorskip("OCP.BRepFeat")

    from gui.commands.feature_commands import AddFeatureCommand

    doc = Document("trust_gate_gui_single_edge")
    body = Body("BodySingleEdge", document=doc)
    doc.add_body(body, set_active=True)
    ui = _DummyMainWindow()

    base = PrimitiveFeature(primitive_type="box", length=40.0, width=28.0, height=18.0, name="Base Box")
    body.add_feature(base, rebuild=True)
    assert _is_success_status(base.status), base.status_message

    directions = [
        (0.0, 1.0, 0.0),
        (1.0, 0.0, 0.0),
        (0.0, 0.0, 1.0),
        (-1.0, 0.0, 0.0),
        (0.0, -1.0, 0.0),
    ]
    for step, direction in enumerate(directions):
        feat, _cmd = _add_pushpull_join_live_via_command(
            doc,
            body,
            ui,
            step,
            direction,
            distance=1.8 + (0.15 * step),
        )
        assert _is_success_status(feat.status), feat.status_message

    pre_chamfer_sig = _solid_signature(body._build123d_solid)

    edge_loop = _loop_edge_indices_for_face_direction(body._build123d_solid, single_edge_face_direction, limit=4)
    assert edge_loop, "expected at least one edge on selected face"
    single_edge = [edge_loop[0]]

    chamfer = ChamferFeature(distance=0.6, edge_indices=single_edge)
    cmd = AddFeatureCommand(body, chamfer, ui, description="Chamfer Single Edge")
    cmd.redo()
    assert _is_success_status(chamfer.status), chamfer.status_message
    report_after_chamfer = doc._shape_naming_service.get_health_report(body)
    _assert_no_broken_feature_refs(report_after_chamfer, {"Extrude", "Chamfer"})

    post_chamfer_sig = _solid_signature(body._build123d_solid)
    assert post_chamfer_sig["faces"] >= pre_chamfer_sig["faces"]
    assert post_chamfer_sig["volume"] < pre_chamfer_sig["volume"]

    cmd.undo()
    undo_sig = _solid_signature(body._build123d_solid)
    _assert_signature_close(undo_sig, pre_chamfer_sig, context="gui_single_edge_chamfer_undo")
    report_after_undo = doc._shape_naming_service.get_health_report(body)
    _assert_no_broken_feature_refs(report_after_undo, {"Extrude"})

    cmd.redo()
    redo_sig = _solid_signature(body._build123d_solid)
    _assert_signature_close(redo_sig, post_chamfer_sig, context="gui_single_edge_chamfer_redo")
    report_after_redo = doc._shape_naming_service.get_health_report(body)
    _assert_no_broken_feature_refs(report_after_redo, {"Extrude", "Chamfer"})


@pytest.mark.parametrize("seed", [7, 19, 43, 71, 97])
def test_trust_gate_randomized_pushpull_and_chamfer_workflow(seed):
    pytest.importorskip("OCP.BRepFeat")

    from gui.commands.feature_commands import AddFeatureCommand

    rng = random.Random(seed)

    doc = Document(f"trust_gate_random_{seed}")
    body = Body(f"BodyRandom{seed}", document=doc)
    doc.add_body(body, set_active=True)
    ui = _DummyMainWindow()

    base = PrimitiveFeature(
        primitive_type="box",
        length=30.0 + rng.uniform(0.0, 20.0),
        width=20.0 + rng.uniform(0.0, 20.0),
        height=12.0 + rng.uniform(0.0, 18.0),
        name="Base Box",
    )
    body.add_feature(base, rebuild=True)
    assert _is_success_status(base.status), f"seed={seed}: {base.status_message}"

    pushpull_count = rng.randint(3, 9)
    for step in range(pushpull_count):
        direction = rng.choice(_AXIS_DIRECTIONS)
        distance = round(rng.uniform(0.8, 3.4), 3)
        feat, _cmd = _add_pushpull_join_live_via_command(
            doc,
            body,
            ui,
            step,
            direction,
            distance=distance,
        )
        assert _is_success_status(feat.status), (
            f"seed={seed}, step={step}, dir={direction}, dist={distance}: {feat.status_message}"
        )

    pre_chamfer_sig = _solid_signature(body._build123d_solid)
    chamfer_edges = _random_chamfer_edges_from_face_loop(body._build123d_solid, rng)
    chamfer_distance = round(rng.uniform(0.25, 0.9), 3)

    chamfer = ChamferFeature(distance=chamfer_distance, edge_indices=chamfer_edges)
    cmd = AddFeatureCommand(body, chamfer, ui, description=f"Chamfer Random seed={seed}")
    cmd.redo()
    assert _is_success_status(chamfer.status), (
        f"seed={seed}, edges={chamfer_edges}, dist={chamfer_distance}: {chamfer.status_message}"
    )

    report_after_chamfer = doc._shape_naming_service.get_health_report(body)
    _assert_no_broken_feature_refs(report_after_chamfer, {"Extrude", "Chamfer"})

    post_chamfer_sig = _solid_signature(body._build123d_solid)
    assert post_chamfer_sig["faces"] >= pre_chamfer_sig["faces"], f"seed={seed}"
    assert post_chamfer_sig["volume"] < pre_chamfer_sig["volume"], f"seed={seed}"
    _assert_local_modifier_keeps_body_scale(
        pre_chamfer_sig,
        post_chamfer_sig,
        magnitude=chamfer_distance,
        context=f"random_seed_{seed}_chamfer_scale_guard",
    )

    cmd.undo()
    undo_sig = _solid_signature(body._build123d_solid)
    _assert_signature_close(undo_sig, pre_chamfer_sig, context=f"random_seed_{seed}_undo")

    report_after_undo = doc._shape_naming_service.get_health_report(body)
    _assert_no_broken_feature_refs(report_after_undo, {"Extrude"})

    cmd.redo()
    redo_sig = _solid_signature(body._build123d_solid)
    _assert_signature_close(redo_sig, post_chamfer_sig, context=f"random_seed_{seed}_redo")

    report_after_redo = doc._shape_naming_service.get_health_report(body)
    _assert_no_broken_feature_refs(report_after_redo, {"Extrude", "Chamfer"})

    # Randomisierte zusätzliche Undo/Redo-Zyklen müssen TNP-Registry stabil halten.
    stats_before_cycles = doc._shape_naming_service.get_stats()
    for _ in range(rng.randint(1, 3)):
        cmd.undo()
        cmd.redo()
    stats_after_cycles = doc._shape_naming_service.get_stats()
    assert stats_after_cycles["edges"] == stats_before_cycles["edges"], (
        f"seed={seed}: edge registry grew across random undo/redo cycles: "
        f"{stats_before_cycles['edges']} -> {stats_after_cycles['edges']}"
    )
    assert stats_after_cycles["operations"] == stats_before_cycles["operations"], (
        f"seed={seed}: operation graph grew across random undo/redo cycles: "
        f"{stats_before_cycles['operations']} -> {stats_after_cycles['operations']}"
    )


def test_trust_gate_regression_seed_chamfer_redo_3657887():
    """
    Regression for stress-run failure:
    Chamfer succeeded on first redo, failed on second redo after undo because
    stale edge_shape_ids conflicted with still-valid edge_indices.
    """
    test_trust_gate_randomized_pushpull_and_chamfer_workflow(3657887)


@pytest.mark.parametrize("seed", [13, 31, 59, 79, 103])
def test_trust_gate_randomized_pushpull_and_fillet_workflow(seed):
    pytest.importorskip("OCP.BRepFeat")

    from gui.commands.feature_commands import AddFeatureCommand

    rng = random.Random(seed)

    doc = Document(f"trust_gate_random_fillet_{seed}")
    body = Body(f"BodyRandomFillet{seed}", document=doc)
    doc.add_body(body, set_active=True)
    ui = _DummyMainWindow()

    base = PrimitiveFeature(
        primitive_type="box",
        length=30.0 + rng.uniform(0.0, 20.0),
        width=20.0 + rng.uniform(0.0, 20.0),
        height=12.0 + rng.uniform(0.0, 18.0),
        name="Base Box",
    )
    body.add_feature(base, rebuild=True)
    assert _is_success_status(base.status), f"seed={seed}: {base.status_message}"

    pushpull_count = rng.randint(3, 9)
    for step in range(pushpull_count):
        direction = rng.choice(_AXIS_DIRECTIONS)
        distance = round(rng.uniform(0.8, 3.4), 3)
        feat, _cmd = _add_pushpull_join_live_via_command(
            doc,
            body,
            ui,
            step,
            direction,
            distance=distance,
        )
        assert _is_success_status(feat.status), (
            f"seed={seed}, step={step}, dir={direction}, dist={distance}: {feat.status_message}"
        )

    pre_fillet_sig = _solid_signature(body._build123d_solid)
    fillet_edges = _random_chamfer_edges_from_face_loop(body._build123d_solid, rng)
    fillet_radius = _safe_random_fillet_radius(body._build123d_solid, fillet_edges, rng)

    fillet = FilletFeature(radius=fillet_radius, edge_indices=fillet_edges)
    cmd = AddFeatureCommand(body, fillet, ui, description=f"Fillet Random seed={seed}")
    cmd.redo()
    assert _is_success_status(fillet.status), (
        f"seed={seed}, edges={fillet_edges}, r={fillet_radius}: {fillet.status_message}"
    )

    report_after_fillet = doc._shape_naming_service.get_health_report(body)
    _assert_no_broken_feature_refs(report_after_fillet, {"Extrude", "Fillet"})

    post_fillet_sig = _solid_signature(body._build123d_solid)
    assert post_fillet_sig["faces"] >= pre_fillet_sig["faces"], f"seed={seed}"
    assert post_fillet_sig["volume"] < pre_fillet_sig["volume"], f"seed={seed}"
    _assert_local_modifier_keeps_body_scale(
        pre_fillet_sig,
        post_fillet_sig,
        magnitude=fillet_radius,
        context=f"random_fillet_seed_{seed}_scale_guard",
    )

    cmd.undo()
    undo_sig = _solid_signature(body._build123d_solid)
    _assert_signature_close(undo_sig, pre_fillet_sig, context=f"random_fillet_seed_{seed}_undo")

    report_after_undo = doc._shape_naming_service.get_health_report(body)
    _assert_no_broken_feature_refs(report_after_undo, {"Extrude"})

    cmd.redo()
    redo_sig = _solid_signature(body._build123d_solid)
    _assert_signature_close(redo_sig, post_fillet_sig, context=f"random_fillet_seed_{seed}_redo")

    report_after_redo = doc._shape_naming_service.get_health_report(body)
    _assert_no_broken_feature_refs(report_after_redo, {"Extrude", "Fillet"})

    stats_before_cycles = doc._shape_naming_service.get_stats()
    for _ in range(rng.randint(1, 3)):
        cmd.undo()
        cmd.redo()
    stats_after_cycles = doc._shape_naming_service.get_stats()
    assert stats_after_cycles["edges"] == stats_before_cycles["edges"], (
        f"seed={seed}: edge registry grew across random fillet undo/redo cycles: "
        f"{stats_before_cycles['edges']} -> {stats_after_cycles['edges']}"
    )
    assert stats_after_cycles["operations"] == stats_before_cycles["operations"], (
        f"seed={seed}: operation graph grew across random fillet undo/redo cycles: "
        f"{stats_before_cycles['operations']} -> {stats_after_cycles['operations']}"
    )
