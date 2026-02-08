from gui.sketch_feedback import format_solver_failure_message, format_trim_failure_message


def test_solver_feedback_over_constrained_has_actionable_hint():
    msg = format_solver_failure_message("OVER_CONSTRAINED", "Widerspruechliche Constraints", dof=0, context="Constraint solve")
    assert "Constraint solve:" in msg
    assert "Widerspruechliche Constraints" in msg
    assert "Entferne" in msg or "entspanne" in msg


def test_solver_feedback_under_constrained_mentions_dof():
    msg = format_solver_failure_message("UNDER_CONSTRAINED", "Unterbestimmt", dof=3, context="Constraint edit")
    assert "Constraint edit:" in msg
    assert "3 DOF" in msg
    assert "unterbestimmt" in msg.lower()


def test_solver_feedback_nan_inf_mentions_numerics():
    msg = format_solver_failure_message("INCONSISTENT", "Ungueltige Residuen (NaN/Inf)", dof=None, context="Constraint solve")
    assert "NaN/Inf" in msg
    assert "Numerische Instabilitaet" in msg


def test_trim_feedback_no_target_is_explanatory():
    msg = format_trim_failure_message("Kein Ziel gefunden", target_type="Line2D")
    assert "Trim (Line2D):" in msg
    assert "Keine Geometrie unter dem Cursor" in msg


def test_trim_feedback_no_segment_is_explanatory():
    msg = format_trim_failure_message("Kein Segment gefunden", target_type="Arc2D")
    assert "Trim (Arc2D):" in msg
    assert "Kein trennbares Segment" in msg


def test_trim_feedback_failed_mentions_rollback():
    msg = format_trim_failure_message("Trim fehlgeschlagen: forced trim failure", target_type="Circle2D")
    assert "Trim (Circle2D):" in msg
    assert "zurueckgesetzt" in msg
