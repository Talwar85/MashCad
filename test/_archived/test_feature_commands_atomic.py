from gui.commands.feature_commands import (
    AddFeatureCommand,
    DeleteFeatureCommand,
    EditFeatureCommand,
)
from gui.commands.transform_command import TransformCommand
from modeling import Body, ExtrudeFeature, PrimitiveFeature
from modeling import TransformFeature


class _DummyBrowser:
    def refresh(self):
        return None


class _DummyMainWindow:
    def __init__(self):
        self.browser = _DummyBrowser()
        self.viewport_3d = type("_Viewport", (), {"remove_body": lambda self, _bid: None})()
        self.notifications = []

    def _update_body_from_build123d(self, _body, _solid):
        return None

    def show_notification(self, title, message, level="info", duration=3000,
                         status_class="", severity=""):
        self.notifications.append((title, message, level))


def _make_body_with_box(name="cmd_atomic_body"):
    body = Body(name)
    body.add_feature(PrimitiveFeature(primitive_type="box", length=10.0, width=10.0, height=10.0))
    return body


def test_add_feature_command_redo_rolls_back_on_new_feature_error(monkeypatch):
    body = _make_body_with_box("add_feature_rollback")
    ui = _DummyMainWindow()
    feature = ExtrudeFeature(
        sketch=None,
        distance=5.0,
        operation="Join",
        face_index=0,
        name="Push/Pull (Join)",
    )
    before_feature_ids = [feat.id for feat in body.features]

    def _failing_add_feature(feat, rebuild=True):
        body.features.append(feat)
        feat.status = "ERROR"
        feat.status_message = "synthetic failure"
        feat.status_details = {"code": "operation_failed"}

    monkeypatch.setattr(body, "add_feature", _failing_add_feature)

    cmd = AddFeatureCommand(body, feature, ui)
    cmd.redo()

    assert [feat.id for feat in body.features] == before_feature_ids
    assert feature not in body.features
    assert all(getattr(feat, "status", "") != "ERROR" for feat in body.features)
    
    # Verify notification
    assert len(ui.notifications) > 0
    assert ui.notifications[0][0] == "Rollback"
    # Reason from _has_transaction_regression contains "new feature errors"
    assert "new feature errors" in ui.notifications[0][1]


def test_add_feature_command_detects_envelope_error_even_if_status_is_ok(monkeypatch):
    body = _make_body_with_box("add_feature_error_envelope_status_ok")
    ui = _DummyMainWindow()
    feature = ExtrudeFeature(
        sketch=None,
        distance=5.0,
        operation="Join",
        face_index=0,
        name="Push/Pull (Join)",
    )
    before_feature_ids = [feat.id for feat in body.features]

    def _failing_add_feature(feat, rebuild=True):
        body.features.append(feat)
        feat.status = "OK"
        feat.status_message = "synthetic status mismatch"
        feat.status_details = {
            "code": "operation_failed",
            "status_class": "ERROR",
            "severity": "error",
        }

    monkeypatch.setattr(body, "add_feature", _failing_add_feature)

    cmd = AddFeatureCommand(body, feature, ui)
    cmd.redo()

    assert [feat.id for feat in body.features] == before_feature_ids
    assert feature not in body.features
    assert len(ui.notifications) > 0
    assert ui.notifications[0][0] == "Rollback"
    assert "new feature errors" in ui.notifications[0][1]


def test_add_feature_command_keeps_recoverable_warning_without_rollback(monkeypatch):
    body = _make_body_with_box("add_feature_recoverable_warning")
    ui = _DummyMainWindow()
    feature = ExtrudeFeature(
        sketch=None,
        distance=5.0,
        operation="Join",
        face_index=0,
        name="Push/Pull (Join)",
    )
    before_feature_ids = [feat.id for feat in body.features]

    def _warning_add_feature(feat, rebuild=True):
        body.features.append(feat)
        feat.status = "WARNING"
        feat.status_message = "synthetic recoverable warning"
        feat.status_details = {
            "code": "fallback_used",
            "status_class": "WARNING_RECOVERABLE",
            "severity": "warning",
        }

    monkeypatch.setattr(body, "add_feature", _warning_add_feature)

    cmd = AddFeatureCommand(body, feature, ui)
    cmd.redo()

    assert len(body.features) == len(before_feature_ids) + 1
    assert feature in body.features
    assert len(ui.notifications) == 0


def test_delete_feature_command_redo_rolls_back_on_rebuild_regression(monkeypatch):
    body = _make_body_with_box("delete_feature_rollback")
    second = PrimitiveFeature(primitive_type="box", length=8.0, width=8.0, height=8.0)
    body.add_feature(second)
    ui = _DummyMainWindow()
    before_feature_ids = [feat.id for feat in body.features]

    def _failing_rebuild():
        if body.features:
            body.features[0].status = "ERROR"
            body.features[0].status_message = "synthetic rebuild regression"
            body.features[0].status_details = {"code": "operation_failed"}

    monkeypatch.setattr(body, "_rebuild", _failing_rebuild)

    cmd = DeleteFeatureCommand(body, second, 1, ui)
    cmd.redo()

    assert [feat.id for feat in body.features] == before_feature_ids
    assert second in body.features
    assert all(getattr(feat, "status", "") != "ERROR" for feat in body.features)

    # Verify notification
    assert len(ui.notifications) > 0
    assert ui.notifications[0][0] == "Rollback"
    assert "new feature errors" in ui.notifications[0][1]


def test_edit_feature_command_redo_rolls_back_and_restores_old_params(monkeypatch):
    body = _make_body_with_box("edit_feature_rollback")
    ui = _DummyMainWindow()
    feature = body.features[0]
    old_length = feature.length

    def _failing_rebuild():
        feature.status = "ERROR"
        feature.status_message = "synthetic edit regression"
        feature.status_details = {"code": "operation_failed"}

    monkeypatch.setattr(body, "_rebuild", _failing_rebuild)

    cmd = EditFeatureCommand(
        body,
        feature,
        old_params={"length": old_length},
        new_params={"length": old_length + 25.0},
        main_window=ui,
    )
    cmd.redo()

    assert feature.length == old_length
    assert getattr(feature, "status", "") != "ERROR"

    # Verify notification
    assert len(ui.notifications) > 0
    assert ui.notifications[0][0] == "Rollback"
    assert "new feature errors" in ui.notifications[0][1]


def test_transform_command_redo_rolls_back_on_transform_error(monkeypatch):
    body = _make_body_with_box("transform_redo_rollback")
    ui = _DummyMainWindow()
    feature = TransformFeature(mode="move", data={"translation": [5.0, 0.0, 0.0]})
    before_feature_ids = [feat.id for feat in body.features]
    before_solid = body._build123d_solid

    def _failing_transform(_solid, _feature):
        raise RuntimeError("synthetic transform failure")

    monkeypatch.setattr(body, "_apply_transform_feature", _failing_transform)

    cmd = TransformCommand(body, feature, ui)
    cmd.redo()

    assert [feat.id for feat in body.features] == before_feature_ids
    assert feature not in body.features
    assert body._build123d_solid is before_solid


def test_transform_command_undo_rolls_back_on_inverse_failure(monkeypatch):
    body = _make_body_with_box("transform_undo_rollback")
    ui = _DummyMainWindow()
    feature = TransformFeature(mode="move", data={"translation": [3.0, 0.0, 0.0]})
    cmd = TransformCommand(body, feature, ui)
    cmd.redo()

    assert feature in body.features
    after_redo_feature_ids = [feat.id for feat in body.features]
    after_redo_solid = body._build123d_solid

    def _failing_inverse(_solid, _feature):
        raise RuntimeError("synthetic inverse failure")

    monkeypatch.setattr(body, "_apply_transform_feature", _failing_inverse)
    cmd.undo()

    assert [feat.id for feat in body.features] == after_redo_feature_ids
    assert feature in body.features
    assert body._build123d_solid is after_redo_solid
