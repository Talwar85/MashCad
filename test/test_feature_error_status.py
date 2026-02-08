from modeling import Body, DraftFeature, FilletFeature, HoleFeature, PrimitiveFeature


def _make_box_body(name: str = "error_status_body") -> Body:
    body = Body(name)
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
    assert (hole.status_details or {}).get("code") == "operation_failed"


def test_draft_invalid_pull_direction_sets_feature_error_message():
    body = _make_box_body("draft_error_body")
    draft = DraftFeature(
        draft_angle=5.0,
        pull_direction=(0.0, 0.0, 0.0),
    )

    body.add_feature(draft)

    assert draft.status == "ERROR"
    assert "Pull-Richtung" in (draft.status_message or "")
    assert (draft.status_details or {}).get("code") == "operation_failed"


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
