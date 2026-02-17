"""
LiteCAD Sketcher Module
"""

from .geometry import (
    Point2D, Line2D, Circle2D, Arc2D, Ellipse2D, Polygon2D, Rectangle2D, Spline2D,
    GeometryType,
    line_line_intersection, circle_line_intersection,
    points_are_coincident, lines_are_parallel, lines_are_perpendicular
)

from .constraints import (
    Constraint, ConstraintType, ConstraintStatus,
    make_fixed, make_coincident, make_horizontal, make_vertical,
    make_parallel, make_perpendicular, make_equal_length,
    make_length, make_distance, make_radius, make_diameter,
    make_angle, make_point_on_line, make_midpoint, make_concentric,
    make_tangent, make_symmetric,
    calculate_constraint_error, is_constraint_satisfied
)

from .solver import ConstraintSolver, SolverResult

from .sketch import Sketch, SketchState
