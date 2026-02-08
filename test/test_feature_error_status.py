from modeling import Body, DraftFeature, HoleFeature, PrimitiveFeature


def _make_box_body(name: str = "error_status_body") -> Body:
    body = Body(name)
    body.add_feature(PrimitiveFeature(primitive_type="box", length=20.0, width=20.0, height=20.0))
    return body


def test_feature_status_message_roundtrip():
    body = Body("roundtrip_status_message")
    feat = PrimitiveFeature(primitive_type="box", length=10.0, width=10.0, height=10.0)
    feat.status = "ERROR"
    feat.status_message = "Primitive konnte nicht erzeugt werden"
    body.features = [feat]

    restored = Body.from_dict(body.to_dict())
    restored_feat = restored.features[0]

    assert restored_feat.status == "ERROR"
    assert restored_feat.status_message == "Primitive konnte nicht erzeugt werden"


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


def test_draft_invalid_pull_direction_sets_feature_error_message():
    body = _make_box_body("draft_error_body")
    draft = DraftFeature(
        draft_angle=5.0,
        pull_direction=(0.0, 0.0, 0.0),
    )

    body.add_feature(draft)

    assert draft.status == "ERROR"
    assert "Pull-Richtung" in (draft.status_message or "")
