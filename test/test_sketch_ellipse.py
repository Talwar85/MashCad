from sketcher import Sketch, ConstraintType
from sketcher.geometry import Ellipse2D


def test_add_ellipse_creates_native_ellipse():
    """Testet die neue native Ellipse2D API."""
    sketch = Sketch("ellipse_native")

    ellipse = sketch.add_ellipse(
        cx=10.0,
        cy=20.0,
        major_radius=30.0,
        minor_radius=12.0,
        angle_deg=25.0,
    )

    # Rückgabe ist eine native Ellipse2D
    assert isinstance(ellipse, Ellipse2D)
    assert ellipse.center.x == 10.0
    assert ellipse.center.y == 20.0
    assert ellipse.radius_x == 30.0
    assert ellipse.radius_y == 12.0
    assert ellipse.rotation == 25.0
    
    # Ellipse ist in der Sketch-Liste
    assert ellipse in sketch.ellipses
    
    # Native OCP Daten vorhanden
    assert ellipse.native_ocp_data is not None
    assert ellipse.native_ocp_data['center'] == (10.0, 20.0)
    assert ellipse.native_ocp_data['radius_x'] == 30.0
    assert ellipse.native_ocp_data['radius_y'] == 12.0


def test_add_ellipse_creates_axes_and_constraints():
    """Testet dass Achsen und Constraints erstellt werden."""
    sketch = Sketch("ellipse_axes")

    ellipse = sketch.add_ellipse(
        cx=0.0,
        cy=0.0,
        major_radius=20.0,
        minor_radius=10.0,
        angle_deg=0.0,
    )

    # Konstruktions-Achsen wurden erstellt
    assert hasattr(ellipse, '_major_axis')
    assert hasattr(ellipse, '_minor_axis')
    assert hasattr(ellipse, '_center_point')
    
    major_axis = ellipse._major_axis
    minor_axis = ellipse._minor_axis
    
    # Achsen sind Konstruktionslinien
    assert major_axis.construction is True
    assert minor_axis.construction is True
    assert major_axis in sketch.lines
    assert minor_axis in sketch.lines
    
    # Constraints für Achsenlängen
    major_lengths = [
        c for c in sketch.constraints
        if c.type == ConstraintType.LENGTH and major_axis in c.entities
    ]
    minor_lengths = [
        c for c in sketch.constraints
        if c.type == ConstraintType.LENGTH and minor_axis in c.entities
    ]
    assert major_lengths and abs((major_lengths[0].value or 0.0) - 40.0) < 1e-6  # 2 * 20
    assert minor_lengths and abs((minor_lengths[0].value or 0.0) - 20.0) < 1e-6  # 2 * 10


def test_add_ellipse_solveable():
    """Testet dass der Sketch mit Ellipse lösbar ist."""
    sketch = Sketch("ellipse_solvable")
    
    ellipse = sketch.add_ellipse(
        cx=0.0,
        cy=0.0,
        major_radius=20.0,
        minor_radius=10.0,
        angle_deg=0.0,
    )

    result = sketch.solve()
    assert result.success is True


def test_ellipse_point_at_angle():
    """Testet die point_at_angle Methode."""
    from sketcher.geometry import Point2D
    
    ellipse = Ellipse2D(
        center=Point2D(0, 0),
        radius_x=10.0,
        radius_y=5.0,
        rotation=0.0
    )
    
    # Bei 0° sollte der Punkt auf der Major-Achse sein
    p0 = ellipse.point_at_angle(0)
    assert abs(p0.x - 10.0) < 1e-6
    assert abs(p0.y - 0.0) < 1e-6
    
    # Bei 90° sollte der Punkt auf der Minor-Achse sein
    p90 = ellipse.point_at_angle(90)
    assert abs(p90.x - 0.0) < 1e-6
    assert abs(p90.y - 5.0) < 1e-6


def test_ellipse_curve_points():
    """Testet die get_curve_points Methode."""
    from sketcher.geometry import Point2D
    
    ellipse = Ellipse2D(
        center=Point2D(0, 0),
        radius_x=10.0,
        radius_y=5.0,
        rotation=0.0
    )
    
    points = ellipse.get_curve_points(64)
    assert len(points) == 65  # segments + 1
    
    # Erster und letzter Punkt sollten gleich sein (geschlossen)
    assert abs(points[0][0] - points[-1][0]) < 1e-6
    assert abs(points[0][1] - points[-1][1]) < 1e-6
