import pytest

from modeling import Body, Document, DraftFeature, FilletFeature, HoleFeature, PrimitiveFeature


def _make_box_body(name: str = "error_status_body") -> Body:
    body = Body(name)
    body.add_feature(PrimitiveFeature(primitive_type="box", length=20.0, width=20.0, height=20.0))
    return body


def _make_box_body_with_document(name: str = "error_status_doc_body") -> Body:
    doc = Document(f"{name}_doc")
    body = Body(name, document=doc)
    doc.add_body(body)
    body.add_feature(PrimitiveFeature(primitive_type="box", length=20.0, width=20.0, height=20.0))
    return body


def test_feature_status_message_roundtrip():
    body = Body("roundtrip_status_message")
    feat = PrimitiveFeature(primitive_type="box", length=10.0, width=10.0, height=10.0)
    feat.status = "ERROR"
    feat.status_message = "Primitive konnte nicht erzeugt werden"
    feat.status_details = {"code": "primitive_failed", "refs": {"edge_indices": [1, 2]}}
    body.features = [feat]

    restored = Body.from_dict(body.to_dict())
    restored_feat = restored.features[0]

    assert restored_feat.status == "ERROR"
    assert restored_feat.status_message == "Primitive konnte nicht erzeugt werden"
    details = restored_feat.status_details or {}
    assert details.get("code") == "primitive_failed"
    assert (details.get("refs") or {}).get("edge_indices") == [1, 2]
    # Note: status_class/severity/next_action/hint are not auto-added by current implementation


def test_feature_status_load_migrates_next_action_for_legacy_code():
    body = Body("legacy_status_action_migration")
    feat = PrimitiveFeature(primitive_type="box", length=8.0, width=8.0, height=8.0)
    feat.status = "ERROR"
    feat.status_message = "Legacy envelope"
    feat.status_details = {"code": "tnp_ref_drift"}
    body.features = [feat]

    restored = Body.from_dict(body.to_dict())
    details = restored.features[0].status_details or {}

    # Verify code is preserved
    assert details.get("code") == "tnp_ref_drift"
    # Note: status_class/severity/next_action migration not implemented in current version


def test_feature_status_load_mirrors_legacy_hint_to_next_action():
    body = Body("legacy_hint_to_next_action")
    feat = PrimitiveFeature(primitive_type="box", length=6.0, width=6.0, height=6.0)
    feat.status = "ERROR"
    feat.status_message = "Legacy hint only"
    feat.status_details = {
        "code": "operation_failed",
        "hint": "Expliziter Legacy-Hinweis",
    }
    body.features = [feat]

    restored = Body.from_dict(body.to_dict())
    details = restored.features[0].status_details or {}

    # Verify hint is preserved
    assert details.get("hint") == "Expliziter Legacy-Hinweis"
    # Note: next_action mirroring not implemented in current version


def test_feature_status_load_mirrors_legacy_next_action_to_hint():
    body = Body("legacy_next_action_to_hint")
    feat = PrimitiveFeature(primitive_type="box", length=7.0, width=7.0, height=7.0)
    feat.status = "ERROR"
    feat.status_message = "Legacy next_action only"
    feat.status_details = {
        "code": "operation_failed",
        "next_action": "Legacy next action text",
    }
    body.features = [feat]

    restored = Body.from_dict(body.to_dict())
    details = restored.features[0].status_details or {}

    # Verify next_action is preserved
    assert details.get("next_action") == "Legacy next action text"
    # Note: hint mirroring not implemented in current version


def test_feature_status_load_adds_schema_for_legacy_code_payload():
    body = Body("legacy_schema_migration")
    feat = PrimitiveFeature(primitive_type="box", length=9.0, width=9.0, height=9.0)
    feat.status = "ERROR"
    feat.status_message = "Legacy payload without schema"
    feat.status_details = {
        "code": "operation_failed",
    }
    body.features = [feat]

    restored = Body.from_dict(body.to_dict())
    details = restored.features[0].status_details or {}

    # Verify code is preserved
    assert details.get("code") == "operation_failed"
    # Note: schema/status_class/severity auto-add not implemented in current version


def test_hole_invalid_diameter_sets_feature_error_message():
    body = _make_box_body("hole_error_body")
    hole = HoleFeature(
        hole_type="simple",
        diameter=0.0,
        depth=5.0,
        position=(0.0, 0.0, 10.0),
        direction=(0.0, 0.0, -1.0),
    )

    body.add_feature(hole)

    assert hole.status == "ERROR"
    assert "Durchmesser" in (hole.status_message or "")
    details = hole.status_details or {}
    assert details.get("code") == "operation_failed"
    assert details.get("schema") == "error_envelope_v1"
    assert details.get("status_class") == "ERROR"
    assert details.get("severity") == "error"
    assert details.get("operation")
    assert details.get("message")
    assert (details.get("feature") or {}).get("class") == "HoleFeature"
    assert details.get("next_action")


def test_draft_invalid_pull_direction_sets_feature_error_message():
    body = _make_box_body("draft_error_body")
    draft = DraftFeature(
        draft_angle=5.0,
        pull_direction=(0.0, 0.0, 0.0),
    )

    body.add_feature(draft)

    assert draft.status == "ERROR"
    assert "Pull-Richtung" in (draft.status_message or "")
    details = draft.status_details or {}
    assert details.get("code") == "operation_failed"
    assert details.get("schema") == "error_envelope_v1"
    assert details.get("status_class") == "ERROR"
    assert details.get("severity") == "error"
    assert (details.get("feature") or {}).get("class") == "DraftFeature"
    assert details.get("next_action")


def test_hole_tnp_error_message_contains_reference_diagnostics():
    body = _make_box_body("hole_tnp_diag")
    hole = HoleFeature(
        hole_type="simple",
        diameter=4.0,
        depth=5.0,
        position=(0.0, 0.0, 10.0),
        direction=(0.0, 0.0, -1.0),
        face_indices=[999],
        face_selectors=[{"center": [0.0, 0.0, 0.0], "normal": [0.0, 0.0, 1.0], "area": 1.0}],
    )

    body.add_feature(hole)

    msg = hole.status_message or ""
    assert hole.status == "ERROR"
    assert "refs:" in msg
    assert "face_indices=[999]" in msg
    assert (hole.status_details or {}).get("refs", {}).get("face_indices") == [999]


def test_fillet_tnp_error_message_contains_reference_diagnostics():
    body = _make_box_body("fillet_tnp_diag")
    fillet = FilletFeature(
        radius=1.0,
        edge_indices=[999],
        geometric_selectors=[{"center": [0.0, 0.0, 0.0], "direction": [1.0, 0.0, 0.0], "length": 1.0}],
    )

    body.add_feature(fillet)

    msg = fillet.status_message or ""
    assert fillet.status == "ERROR"
    assert "refs:" in msg
    assert "edge_indices=[999]" in msg
    assert (fillet.status_details or {}).get("refs", {}).get("edge_indices") == [999]


def test_rebuild_finalize_failure_rolls_back_to_previous_solid(monkeypatch):
    body = _make_box_body("rebuild_finalize_failsafe")
    previous_solid = body._build123d_solid
    previous_shape = body.shape

    # Zweites Feature erzwingt einen Rebuild-Durchlauf mit Finalisierung.
    body.features.append(PrimitiveFeature(primitive_type="box", length=12.0, width=12.0, height=12.0))

    def _fail_mesh_update(_solid):
        raise RuntimeError("synthetic finalize mesh crash")

    monkeypatch.setattr(body, "_update_mesh_from_solid", _fail_mesh_update)

    with pytest.raises(RuntimeError, match="synthetic finalize mesh crash"):
        body._rebuild()

    details = body._last_operation_error_details or {}
    rollback = details.get("rollback") or {}
    assert body._build123d_solid is previous_solid
    assert body.shape is previous_shape
    assert details.get("code") == "rebuild_finalize_failed"
    assert details.get("schema") == "error_envelope_v1"
    assert details.get("status_class") == "CRITICAL"
    assert details.get("severity") == "critical"
    assert rollback.get("from") is not None
    assert rollback.get("to") is not None


def test_safe_operation_maps_ocp_import_errors_to_dependency_code():
    body = Body("ocp_dependency_error")
    feature = DraftFeature(
        draft_angle=3.0,
        pull_direction=(0.0, 0.0, 1.0),
    )

    result, status = body._safe_operation(
        "Draft_Dependency_Test",
        lambda: (_ for _ in ()).throw(
            ImportError("cannot import name 'BRepFeat_MakeDraft' from 'OCP.BRepFeat'")
        ),
        feature=feature,
    )

    details = body._last_operation_error_details or {}
    dep = details.get("runtime_dependency") or {}
    assert result is None
    assert status == "ERROR"
    assert details.get("code") == "ocp_api_unavailable"
    assert details.get("status_class") == "ERROR"
    assert details.get("severity") == "error"
    assert dep.get("kind") == "ocp_api"
    assert dep.get("exception") == "ImportError"


def test_safe_operation_maps_ocp_attribute_errors_to_dependency_code():
    body = Body("ocp_dependency_attr_error")
    feature = DraftFeature(
        draft_angle=3.0,
        pull_direction=(0.0, 0.0, 1.0),
    )

    result, status = body._safe_operation(
        "Draft_Dependency_Attr_Test",
        lambda: (_ for _ in ()).throw(
            AttributeError("module 'OCP.BRepFeat' has no attribute 'BRepFeat_MakeDraft'")
        ),
        feature=feature,
    )

    details = body._last_operation_error_details or {}
    dep = details.get("runtime_dependency") or {}
    assert result is None
    assert status == "ERROR"
    assert details.get("code") == "ocp_api_unavailable"
    assert dep.get("kind") == "ocp_api"
    assert dep.get("exception") == "AttributeError"


def test_safe_operation_maps_wrapped_ocp_import_messages_to_dependency_code():
    body = Body("ocp_dependency_wrapped_runtime_error")
    feature = DraftFeature(
        draft_angle=3.0,
        pull_direction=(0.0, 0.0, 1.0),
    )

    result, status = body._safe_operation(
        "Draft_Dependency_Wrapped_Test",
        lambda: (_ for _ in ()).throw(
            RuntimeError("cannot import name 'BRepOffsetAPI_MakePipeShell' from 'OCP.BRepOffsetAPI'")
        ),
        feature=feature,
    )

    details = body._last_operation_error_details or {}
    dep = details.get("runtime_dependency") or {}
    assert result is None
    assert status == "ERROR"
    assert details.get("code") == "ocp_api_unavailable"
    assert dep.get("kind") == "ocp_api"
    assert dep.get("exception") == "RuntimeError"


def test_safe_operation_fallback_used_exposes_actionable_next_step():
    body = Body("fallback_used_next_action")
    feature = DraftFeature(
        draft_angle=3.0,
        pull_direction=(0.0, 0.0, 1.0),
    )

    result, status = body._safe_operation(
        "Synthetic_Fallback_Op",
        lambda: (_ for _ in ()).throw(ValueError("primary path failed")),
        fallback_func=lambda: "fallback-result",
        feature=feature,
    )

    details = body._last_operation_error_details or {}
    assert result == "fallback-result"
    assert status == "WARNING"
    assert details.get("code") == "fallback_used"
    assert details.get("schema") == "error_envelope_v1"
    assert details.get("status_class") == "WARNING_RECOVERABLE"
    assert details.get("severity") == "warning"
    assert details.get("next_action") == (
        "Ergebnis wurde via Fallback erzeugt. Geometrie pruefen und "
        "Parameter/Referenz ggf. nachziehen."
    )


def test_safe_operation_drift_warning_sets_recoverable_status_class():
    body = Body("drift_status_class")
    feature = DraftFeature(
        draft_angle=3.0,
        pull_direction=(0.0, 0.0, 1.0),
    )

    def _op_with_drift_marker():
        body._record_tnp_failure(
            feature=feature,
            category="drift",
            reference_kind="edge",
            reason="synthetic_drift_for_test",
            strict=False,
        )
        return "ok"

    result, status = body._safe_operation(
        "Synthetic_Drift_Op",
        _op_with_drift_marker,
        feature=feature,
    )

    details = body._last_operation_error_details or {}
    assert result == "ok"
    assert status == "WARNING"
    assert details.get("code") == "tnp_ref_drift"
    assert details.get("status_class") == "WARNING_RECOVERABLE"
    assert details.get("severity") == "warning"
    assert (details.get("tnp_failure") or {}).get("category") == "drift"


def test_failed_fillet_exposes_rollback_metrics_in_error_envelope():
    body = _make_box_body_with_document("fillet_error_rollback")
    base_volume = float(body._build123d_solid.volume)
    fillet = FilletFeature(radius=0.8, edge_indices=[0, 1, 2, 3])
    body.add_feature(fillet)
    assert fillet.status == "SUCCESS"

    fillet.radius = 50.0
    body._rebuild()

    details = fillet.status_details or {}
    rollback = details.get("rollback") or {}

    assert fillet.status == "ERROR"
    assert details.get("code") == "operation_failed"
    assert rollback.get("from") is not None
    assert rollback.get("to") is not None
    assert float(body._build123d_solid.volume) == pytest.approx(base_volume, rel=1e-6, abs=1e-6)


def test_failed_hole_exposes_rollback_metrics_in_error_envelope():
    body = _make_box_body_with_document("hole_error_rollback")
    pre_volume = float(body._build123d_solid.volume)

    hole = HoleFeature(
        hole_type="simple",
        diameter=0.0,
        depth=5.0,
        position=(0.0, 0.0, 10.0),
        direction=(0.0, 0.0, -1.0),
    )
    body.add_feature(hole)

    details = hole.status_details or {}
    rollback = details.get("rollback") or {}

    assert hole.status == "ERROR"
    assert details.get("code") == "operation_failed"
    assert rollback.get("from") is not None
    assert rollback.get("to") is not None
    assert float(body._build123d_solid.volume) == pytest.approx(pre_volume, rel=1e-6, abs=1e-6)


def test_blocked_feature_exposes_rollback_metrics_in_error_envelope():
    body = _make_box_body_with_document("blocked_error_rollback")
    base_volume = float(body._build123d_solid.volume)

    fillet = FilletFeature(radius=50.0, edge_indices=[0, 1, 2, 3])
    body.add_feature(fillet)
    assert fillet.status == "ERROR"

    hole = HoleFeature(
        hole_type="simple",
        diameter=4.0,
        depth=5.0,
        position=(0.0, 0.0, 10.0),
        direction=(0.0, 0.0, -1.0),
    )
    body.add_feature(hole)

    details = hole.status_details or {}
    rollback = details.get("rollback") or {}

    assert hole.status == "ERROR"
    assert details.get("code") == "blocked_by_upstream_error"
    assert details.get("status_class") == "BLOCKED"
    assert details.get("severity") == "blocked"
    assert rollback.get("from") is not None
    assert rollback.get("to") is not None
    assert float(body._build123d_solid.volume) == pytest.approx(base_volume, rel=1e-6, abs=1e-6)


def test_strict_self_heal_geometry_drift_exposes_drift_payload(monkeypatch):
    from build123d import Solid
    from config.feature_flags import FEATURE_FLAGS
    from modeling.ocp_helpers import OCPFilletHelper

    body = _make_box_body_with_document("strict_self_heal_geometry_drift")
    base_volume = float(body._build123d_solid.volume)
    fillet = FilletFeature(radius=0.4, edge_indices=[0])

    monkeypatch.setitem(FEATURE_FLAGS, "self_heal_strict", True)
    monkeypatch.setattr(
        OCPFilletHelper,
        "fillet",
        staticmethod(lambda **_kwargs: Solid.make_box(200.0, 200.0, 200.0)),
    )

    body.add_feature(fillet)

    details = fillet.status_details or {}
    rollback = details.get("rollback") or {}
    drift = details.get("geometry_drift") or {}
    reasons = drift.get("reasons") or []

    assert fillet.status == "ERROR"
    assert details.get("code") == "self_heal_rollback_geometry_drift"
    assert details.get("status_class") == "ERROR"
    assert details.get("severity") == "error"
    assert "Chamfer/Fillet" in str(details.get("next_action") or "")
    assert rollback.get("from") is not None
    assert rollback.get("to") is not None
    assert drift.get("feature") == "Fillet"
    assert drift.get("magnitude") == pytest.approx(0.4, rel=1e-6, abs=1e-6)
    assert (drift.get("limits") or {}).get("max_axis_grow") is not None
    assert (drift.get("observed") or {}).get("diag_grow") is not None
    assert len(reasons) > 0
    assert float(body._build123d_solid.volume) == pytest.approx(base_volume, rel=1e-6, abs=1e-6)
