import math

from gui.sketch_handlers import SketchHandlersMixin
from sketcher import Arc2D, Circle2D, Line2D, Point2D
from sketcher.operations.trim import TrimSegment


class _TrimPreviewDummy(SketchHandlersMixin):
    pass


def _segment(target, start_xy, end_xy, full_delete=False):
    p0 = Point2D(*start_xy)
    p1 = Point2D(*end_xy)
    return TrimSegment(
        start_point=p0,
        end_point=p1,
        segment_index=0,
        all_cut_points=[],
        target_entity=target,
        is_full_delete=full_delete,
    )


def test_trim_preview_line_returns_line_segment():
    dummy = _TrimPreviewDummy()
    target = Line2D(Point2D(0.0, 0.0), Point2D(10.0, 0.0))
    seg = _segment(target, (2.0, 0.0), (8.0, 0.0))

    preview = dummy._build_trim_preview_geometry(target, seg)

    assert len(preview) == 1
    assert isinstance(preview[0], Line2D)
    assert math.isclose(preview[0].start.x, 2.0, rel_tol=0.0, abs_tol=1e-9)
    assert math.isclose(preview[0].end.x, 8.0, rel_tol=0.0, abs_tol=1e-9)


def test_trim_preview_circle_returns_arc_segment():
    dummy = _TrimPreviewDummy()
    target = Circle2D(center=Point2D(0.0, 0.0), radius=10.0)
    seg = _segment(target, (10.0, 0.0), (0.0, 10.0))

    preview = dummy._build_trim_preview_geometry(target, seg)

    assert len(preview) == 1
    assert isinstance(preview[0], Arc2D)
    assert math.isclose(preview[0].radius, 10.0, rel_tol=0.0, abs_tol=1e-9)
    assert math.isclose(preview[0].center.x, 0.0, rel_tol=0.0, abs_tol=1e-9)
    assert math.isclose(preview[0].start_angle, 0.0, rel_tol=0.0, abs_tol=1e-6)
    assert math.isclose(preview[0].end_angle, 90.0, rel_tol=0.0, abs_tol=1e-6)


def test_trim_preview_full_delete_returns_empty():
    dummy = _TrimPreviewDummy()
    target = Circle2D(center=Point2D(0.0, 0.0), radius=5.0)
    seg = _segment(target, (5.0, 0.0), (0.0, 5.0), full_delete=True)

    preview = dummy._build_trim_preview_geometry(target, seg)

    assert preview == []


def test_trim_preview_circle_wrap_segment_keeps_direction():
    dummy = _TrimPreviewDummy()
    target = Circle2D(center=Point2D(0.0, 0.0), radius=10.0)
    a0 = math.radians(350.0)
    a1 = math.radians(10.0)
    seg = _segment(
        target,
        (10.0 * math.cos(a0), 10.0 * math.sin(a0)),
        (10.0 * math.cos(a1), 10.0 * math.sin(a1)),
    )

    preview = dummy._build_trim_preview_geometry(target, seg)

    assert len(preview) == 1
    arc = preview[0]
    assert isinstance(arc, Arc2D)
    assert math.isclose(arc.sweep_angle, 20.0, rel_tol=0.0, abs_tol=1.5)


def test_trim_preview_circle_can_show_major_segment():
    dummy = _TrimPreviewDummy()
    target = Circle2D(center=Point2D(0.0, 0.0), radius=10.0)
    a0 = math.radians(10.0)
    a1 = math.radians(350.0)
    seg = _segment(
        target,
        (10.0 * math.cos(a0), 10.0 * math.sin(a0)),
        (10.0 * math.cos(a1), 10.0 * math.sin(a1)),
    )

    preview = dummy._build_trim_preview_geometry(target, seg)

    assert len(preview) == 1
    arc = preview[0]
    assert isinstance(arc, Arc2D)
    assert math.isclose(arc.sweep_angle, 340.0, rel_tol=0.0, abs_tol=1.5)
