"""
Regression tests for section view bounds computation.

Guards against component-scope regressions where section slider bounds
were computed only from document.bodies (active component).
"""

from types import SimpleNamespace

from gui.viewport.section_view_mixin import SectionViewMixin


def _bind_get_bounds(host):
    host.get_section_bounds = SectionViewMixin.get_section_bounds.__get__(host, object)
    return host


def test_section_bounds_use_get_all_bodies_when_active_component_empty():
    body = SimpleNamespace(
        id="B1",
        vtk_mesh=SimpleNamespace(bounds=(0.0, 10.0, -5.0, 5.0, 2.0, 22.0)),
    )
    host = _bind_get_bounds(
        SimpleNamespace(
            document=SimpleNamespace(
                bodies=[],
                get_all_bodies=lambda: [body],
            ),
            bodies={},
            _section_plane="XY",
        )
    )

    min_pos, max_pos, default_pos = host.get_section_bounds()
    assert min_pos == 2.0
    assert max_pos == 22.0
    assert default_pos == 12.0


def test_section_bounds_fallback_to_viewport_meshes_when_document_missing():
    host = _bind_get_bounds(
        SimpleNamespace(
            document=SimpleNamespace(bodies=[]),
            bodies={
                "B2": {"mesh": SimpleNamespace(bounds=(5.0, 25.0, 1.0, 11.0, -3.0, 7.0))}
            },
            _section_plane="YZ",
        )
    )

    min_pos, max_pos, default_pos = host.get_section_bounds()
    assert min_pos == 5.0
    assert max_pos == 25.0
    assert default_pos == 15.0


def test_section_bounds_returns_defaults_when_no_mesh_data_available():
    host = _bind_get_bounds(
        SimpleNamespace(
            document=SimpleNamespace(bodies=[], get_all_bodies=lambda: []),
            bodies={},
            _section_plane="XY",
        )
    )

    assert host.get_section_bounds() == (-1000.0, 1000.0, 0.0)
