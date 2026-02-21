import pytest

from modeling import (
    Body,
    ChamferFeature,
    Document,
    DraftFeature,
    FilletFeature,
    PrimitiveFeature,
)


def _make_box_body(name: str = "red_flag_body") -> Body:
    body = Body(name)
    body.add_feature(PrimitiveFeature(primitive_type="box", length=20.0, width=20.0, height=20.0))
    return body


def _make_box_body_with_document(name: str = "red_flag_doc_body") -> Body:
    doc = Document(f"{name}_doc")
    body = Body(name, document=doc)
    doc.add_body(body)
    body.add_feature(PrimitiveFeature(primitive_type="box", length=20.0, width=20.0, height=20.0))
    return body


def _is_success(feature) -> bool:
    return str(getattr(feature, "status", "")).upper() in {"SUCCESS", "OK"}


def test_red_flag_finalize_failsafe_rolls_back_and_marks_critical(monkeypatch):
    body = _make_box_body("red_flag_finalize_failsafe")
    previous_solid = body._build123d_solid
    previous_shape = body.shape

    # Trigger a rebuild pass that reaches finalization and then fails there.
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
    assert details.get("status_class") == "CRITICAL"
    assert details.get("severity") == "critical"
    assert rollback.get("from") is not None
    assert rollback.get("to") is not None


def test_red_flag_blocked_upstream_chain_unblocks_after_fix():
    body = _make_box_body_with_document("red_flag_blocked_chain")

    fillet = FilletFeature(radius=50.0, edge_indices=[0, 1, 2, 3])
    body.add_feature(fillet)
    assert str(fillet.status).upper() == "ERROR"

    chamfer = ChamferFeature(distance=0.4, edge_indices=[4, 5, 6, 7])
    body.add_feature(chamfer)

    blocked_details = chamfer.status_details or {}
    assert str(chamfer.status).upper() == "ERROR"
    assert blocked_details.get("code") == "blocked_by_upstream_error"
    assert blocked_details.get("status_class") == "BLOCKED"
    assert blocked_details.get("severity") == "blocked"

    fillet.radius = 0.4
    body._rebuild()

    assert _is_success(fillet)
    recovered_details = chamfer.status_details or {}
    assert recovered_details.get("code") != "blocked_by_upstream_error"
    assert recovered_details.get("status_class") != "BLOCKED"


def test_red_flag_drift_warning_contract_is_recoverable():
    body = Body("red_flag_drift_warning")
    feature = DraftFeature(
        draft_angle=3.0,
        pull_direction=(0.0, 0.0, 1.0),
    )

    def _op_with_drift_marker():
        body._record_tnp_failure(
            feature=feature,
            category="drift",
            reference_kind="edge",
            reason="synthetic_red_flag_drift",
            strict=False,
        )
        return "ok"

    result, status = body._safe_operation(
        "RedFlag_Drift_Op",
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


def test_red_flag_error_envelope_survives_save_load_roundtrip(tmp_path):
    doc = Document("red_flag_roundtrip_doc")
    body = Body("red_flag_roundtrip_body", document=doc)
    body.id = "red_flag_roundtrip_body_id"
    doc.add_body(body)

    body.add_feature(PrimitiveFeature(primitive_type="box", length=20.0, width=20.0, height=20.0), rebuild=True)
    fillet = FilletFeature(radius=50.0, edge_indices=[0, 1, 2, 3])
    body.add_feature(fillet, rebuild=True)
    assert str(fillet.status).upper() == "ERROR"

    details_before = fillet.status_details or {}
    rollback_before = details_before.get("rollback") or {}
    assert details_before.get("code") == "operation_failed"
    assert details_before.get("status_class") == "ERROR"
    assert details_before.get("severity") == "error"
    assert rollback_before.get("from") is not None
    assert rollback_before.get("to") is not None

    save_path = tmp_path / "red_flag_roundtrip.mshcad"
    assert doc.save_project(str(save_path))

    loaded = Document.load_project(str(save_path))
    assert loaded is not None
    loaded_body = loaded.find_body_by_id("red_flag_roundtrip_body_id")
    assert loaded_body is not None
    loaded_fillet = next(feat for feat in loaded_body.features if isinstance(feat, FilletFeature))

    details_after = loaded_fillet.status_details or {}
    rollback_after = details_after.get("rollback") or {}
    assert details_after.get("code") == "operation_failed"
    assert details_after.get("status_class") == "ERROR"
    assert details_after.get("severity") == "error"
    assert rollback_after.get("from") is not None
    assert rollback_after.get("to") is not None
