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


def test_browser_tooltip_uses_next_action_when_hint_missing():
    msg = "Fillet: Kante konnte nicht aufgeloest werden"
    details = {
        "code": "operation_failed",
        "next_action": "Feature-Referenz neu auswaehlen",
        "refs": {
            "edge_indices": [123],
        },
    }

    tooltip = _format_feature_status_tooltip(msg, status="ERROR", status_details=details)

    assert "Broken refs:" in tooltip
    assert "- edge_indices=[123]" in tooltip
    assert ("Hint:" in tooltip) or ("Hinweis:" in tooltip)
    assert "Feature-Referenz neu auswaehlen" in tooltip

def test_browser_tooltip_shows_tnp_category():
    """Verify that tnp_failure.category is displayed in tooltip."""
    msg = "Chamfer: Kantenreferenz verloren"
    details = {
        "code": "tnp_ref_missing",
        "tnp_failure": {
            "category": "missing_ref",
            "reference_kind": "edge"
        }
    }
    
    tooltip = _format_feature_status_tooltip(msg, status="ERROR", status_details=details)
    
    # German fallback "Ref verloren" or similar
    assert "[Referenz verloren]" in tooltip or "[missing_ref]" in tooltip
    assert "Code: tnp_ref_missing" in tooltip

def test_browser_tooltip_shows_warning_for_drift():
    """Verify that tnp_ref_drift is shown as Warning (Recoverable)."""
    msg = "Fillet: Geometrie leicht verschoben"
    details = {
        "code": "tnp_ref_drift",
        "tnp_failure": {
            "category": "drift"
        }
    }
    
    # Even if status is ERROR, we expect Warning text due to drift mapping
    tooltip = _format_feature_status_tooltip(msg, status="ERROR", status_details=details)
    
    assert "Warning (Recoverable)" in tooltip
    assert "[Geometrie-Drift]" in tooltip or "[drift]" in tooltip
    assert "Code: tnp_ref_drift" in tooltip
