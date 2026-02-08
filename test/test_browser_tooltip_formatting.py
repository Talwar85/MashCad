from gui.browser import _format_feature_status_tooltip


def test_browser_tooltip_formats_broken_refs_block():
    msg = (
        "Hole: Ziel-Face konnte via TNP v4.0 nicht aufgelöst werden "
        "| refs: face_indices=[999]; face_shape_ids=['FACE:abcd1234@0']"
    )

    tooltip = _format_feature_status_tooltip(msg, status="ERROR")

    assert ("Error" in tooltip) or ("Fehler" in tooltip)
    assert "Broken refs:" in tooltip
    assert "- face_indices=[999]" in tooltip
    assert "- face_shape_ids=['FACE:abcd1234@0']" in tooltip


def test_browser_tooltip_keeps_plain_message_when_no_refs():
    msg = "Draft: Ungültige Pull-Richtung (Nullvektor)"
    tooltip = _format_feature_status_tooltip(msg, status="ERROR")

    assert ("Error" in tooltip) or ("Fehler" in tooltip)
    assert msg in tooltip
    assert "Broken refs:" not in tooltip


def test_browser_tooltip_uses_status_details_when_message_has_no_refs():
    msg = "Hole: Ziel-Face konnte nicht aufgelöst werden"
    details = {
        "code": "operation_failed",
        "hint": "Wähle eine gültige Ziel-Fläche",
        "refs": {
            "face_indices": [999],
            "face_shape_ids": ["FACE:abcd1234@0"],
        },
    }

    tooltip = _format_feature_status_tooltip(msg, status="ERROR", status_details=details)

    assert "Broken refs:" in tooltip
    assert "- face_indices=[999]" in tooltip
    assert "- face_shape_ids=['FACE:abcd1234@0']" in tooltip
    assert ("Hint:" in tooltip) or ("Hinweis:" in tooltip)
    assert ("Code: operation_failed" in tooltip) or ("Code:" in tooltip)
