"""
MashCad - Sketch Tools Enums
Tool types and snap types for the 2D sketch editor
"""

from enum import Enum, auto


class SketchTool(Enum):
    """Available sketch tools"""
    SELECT = auto()
    LINE = auto()
    RECTANGLE = auto()
    RECTANGLE_CENTER = auto()
    CIRCLE = auto()
    CIRCLE_2POINT = auto()
    CIRCLE_3POINT = auto()
    POLYGON = auto()
    ARC_3POINT = auto()
    SLOT = auto()
    POINT = auto()
    SPLINE = auto()
    MOVE = auto()
    COPY = auto()
    ROTATE = auto()
    MIRROR = auto()
    SCALE = auto()
    TRIM = auto()
    EXTEND = auto()
    OFFSET = auto()
    FILLET_2D = auto()
    CHAMFER_2D = auto()
    DIMENSION = auto()
    DIMENSION_ANGLE = auto()
    HORIZONTAL = auto()
    VERTICAL = auto()
    PARALLEL = auto()
    PERPENDICULAR = auto()
    EQUAL = auto()
    CONCENTRIC = auto()
    TANGENT = auto()
    PATTERN_LINEAR = auto()
    PATTERN_CIRCULAR = auto()
    GEAR = auto()
    STAR = auto()
    NUT = auto()
    TEXT = auto()


class SnapType(Enum):
    """Snap point types"""
    NONE = auto()
    ENDPOINT = auto()
    MIDPOINT = auto()
    CENTER = auto()
    INTERSECTION = auto()
    QUADRANT = auto()
    GRID = auto()
    PERPENDICULAR = auto()
    TANGENT = auto()
