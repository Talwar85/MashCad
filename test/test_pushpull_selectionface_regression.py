"""
Regression guards for body-face extrusion (push/pull) SelectionFace handling.
"""

from types import SimpleNamespace
from unittest.mock import Mock

from gui.feature_operations import FeatureMixin


class _FeatureHarness(FeatureMixin):
    def __init__(self, selection_face):
        self._is_processing_extrusion = False

        self.viewport_3d = SimpleNamespace(
            selected_face_ids={selection_face.id},
            detector=SimpleNamespace(selection_faces=[selection_face]),
        )

        self._extrude_body_face_build123d = Mock(return_value=True)
        self._finish_extrusion_ui = Mock()


def test_on_extrusion_finished_converts_body_selection_face_to_dict_payload():
    """
    Regression for:
    AttributeError: 'SelectionFace' object has no attribute 'get'
    """
    selection_face = SimpleNamespace(
        id=17,
        domain_type="body_face",
        owner_id="B1",
        sample_point=(10.0, 20.0, 30.0),
        plane_origin=(1.0, 2.0, 3.0),
        plane_normal=(0.0, 0.0, 1.0),
        ocp_face_id=4,
    )
    host = _FeatureHarness(selection_face)

    host._on_extrusion_finished([selection_face.id], 5.0, "Join")

    host._extrude_body_face_build123d.assert_called_once()
    face_payload, height, operation = host._extrude_body_face_build123d.call_args[0]

    assert isinstance(face_payload, dict)
    assert face_payload["body_id"] == "B1"
    assert face_payload["center_3d"] == (10.0, 20.0, 30.0)
    assert face_payload["center"] == (1.0, 2.0, 3.0)
    assert face_payload["normal"] == (0.0, 0.0, 1.0)
    assert face_payload["ocp_face_id"] == 4
    assert face_payload["face_index"] == 4
    assert face_payload["selection_face_id"] == 17
    assert height == 5.0
    assert operation == "Join"

    host._finish_extrusion_ui.assert_called_once_with(success=True)
