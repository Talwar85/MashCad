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
    assert restored_feat.status_details == {"code": "primitive_failed", "refs": {"edge_indices": [1, 2]}}


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
    assert dep.get("kind") == "ocp_api"
    assert dep.get("exception") == "ImportError"


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
