from sketcher import Sketch, ConstraintType


def test_add_ellipse_creates_axes_and_perimeter():
    sketch = Sketch("ellipse_basic")

    ellipse_lines, major_axis, minor_axis, center = sketch.add_ellipse(
        cx=10.0,
        cy=20.0,
        major_radius=30.0,
        minor_radius=12.0,
        angle_deg=25.0,
        segments=48,
    )

    assert len(ellipse_lines) == 48
    assert all(not line.construction for line in ellipse_lines)
    assert major_axis.construction is True
    assert minor_axis.construction is True
    assert major_axis in sketch.lines
    assert minor_axis in sketch.lines
    assert center in sketch.points

    major_lengths = [
        c for c in sketch.constraints
        if c.type == ConstraintType.LENGTH and major_axis in c.entities
    ]
    minor_lengths = [
        c for c in sketch.constraints
        if c.type == ConstraintType.LENGTH and minor_axis in c.entities
    ]
    assert major_lengths and abs((major_lengths[0].value or 0.0) - 60.0) < 1e-6
    assert minor_lengths and abs((minor_lengths[0].value or 0.0) - 24.0) < 1e-6


def test_add_ellipse_is_closed_and_solveable():
    sketch = Sketch("ellipse_closed")
    ellipse_lines, _, _, _ = sketch.add_ellipse(
        cx=0.0,
        cy=0.0,
        major_radius=20.0,
        minor_radius=10.0,
        angle_deg=0.0,
        segments=36,
    )

    assert ellipse_lines[0].start is ellipse_lines[-1].end

    result = sketch.solve()
    assert result.success is True
