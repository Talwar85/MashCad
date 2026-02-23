"""
CadQuery Workplane Compatibility Layer for MashCad

This module provides adapters to convert CadQuery Workplane API calls
to Build123d equivalents, enabling existing CadQuery scripts to work
in MashCad.

CadQuery Pattern -> Build123d Equivalent:
- cq.Workplane('XY') -> BuildPart with Plane.XY
- .box(1,2,3) -> Box(1,2,3) in BuildPart
- .circle(10) -> Circle(10) in BuildSketch
- .extrude(5) -> extrude(amount=5)
- .faces('>Z') -> faces().filter_by(Axis.Z)
- .edges('|Z') -> edges().filter_by(Axis.Z)
- .val() -> Extract solid from BuildPart
"""

import re
from typing import Any, Union, List, Optional, Tuple
from loguru import logger


class CadQueryCompatError(Exception):
    """Exception raised when CadQuery compatibility fails."""
    pass


class WorkplaneAdapter:
    """
    Adapter that mimics CadQuery's Workplane API using Build123d.

    This allows code like:
        cq.Workplane('XY').box(10, 20, 30).faces('>Z').fillet(2)

    To work via:
        with BuildPart() as w:
            Box(10, 20, 30)
        fillet(w.faces().filter_by(Axis.Z), 2)
    """

    def __init__(self, build123d_module):
        """Initialize with Build123d module."""
        self.b123d = build123d_module
        self._current_part = None
        self._stack = []  # For tracking workplane state

        # Map plane names
        self._planes = {
            'XY': self.b123d.Plane.XY,
            'XZ': self.b123d.Plane.XZ,
            'YZ': self.b123d.Plane.YZ,
            'front': self.b123d.Plane.XZ,
            'back': self.b123d.Plane.XZ.rotated((0, 0, 180)),
            'left': self.b123d.Plane.YZ,
            'right': self.b123d.Plane.YZ.rotated((0, 0, 90)),
            'top': self.b123d.Plane.XY,
            'bottom': self.b123d.Plane.XY.rotated((0, 0, 180))
        }

    def Workplane(self, plane: str = 'XY') -> 'Workplane':
        """Create a new workplane (mimics cq.Workplane())."""
        return Workplane(self, plane)


class Workplane:
    """
    CadQuery Workplane compatibility wrapper.

    Supports chaining operations like:
        cq.Workplane('XY').box(10, 20, 30).faces('>Z').fillet(2)

    The workplane builds up operations and creates the solid when .val() is called.
    """

    def __init__(self, adapter: WorkplaneAdapter, plane: str = 'XY'):
        self.adapter = adapter
        self.b123d = adapter.b123d
        self.plane = adapter._planes.get(plane, adapter.b123d.Plane.XY)
        self._operations = []  # List of operations to execute
        self._solid = None  # Cached result
        self._context = None  # BuildPart context for operations

    def box(self, length: float, width: float, height: float, centered: bool = True) -> 'Workplane':
        """Add a box operation."""
        self._operations.append(('box', {'length': length, 'width': width, 'height': height, 'centered': centered}))
        return self

    def cylinder(self, radius: float, height: float, centered: bool = True) -> 'Workplane':
        """Add a cylinder operation."""
        self._operations.append(('cylinder', {'radius': radius, 'height': height, 'centered': centered}))
        return self

    def circle(self, radius: float) -> 'Workplane':
        """Add a circle to the workplane sketch."""
        self._operations.append(('circle', {'radius': radius}))
        return self

    def extrude(self, distance: float) -> 'Workplane':
        """Add an extrude operation."""
        self._operations.append(('extrude', {'distance': distance, 'plane': self.plane}))
        return self

    def faces(self, selector: str = None) -> 'Selector':
        """Select faces - returns selector for chaining."""
        sel = Selector(self, 'face', selector)
        # Store selector info for next operation (fillet/chamfer)
        self._pending_selector = sel
        return sel

    def edges(self, selector: str = None) -> 'Selector':
        """Select edges - returns selector for chaining."""
        sel = Selector(self, 'edge', selector)
        # Store selector info for next operation (fillet/chamfer)
        self._pending_selector = sel
        return sel

    def fillet(self, radius: float, edges=None) -> 'Workplane':
        """Add a fillet operation."""
        if edges is not None:
            self._operations.append(('fillet', {'radius': radius, 'edges': edges, 'selector': None}))
        elif hasattr(self, '_selected_edges'):
            self._operations.append(('fillet', {'radius': radius, 'edges': self._selected_edges, 'selector': None}))
            delattr(self, '_selected_edges')
        elif hasattr(self, '_pending_selector'):
            # Store selector info for deferred execution
            selector_info = self._pending_selector.get_info() if hasattr(self._pending_selector, 'get_info') else None
            self._operations.append(('fillet', {'radius': radius, 'edges': None, 'selector': selector_info}))
            delattr(self, '_pending_selector')
        return self

    def chamfer(self, length: float, edges=None) -> 'Workplane':
        """Add a chamfer operation."""
        if edges is not None:
            self._operations.append(('chamfer', {'length': length, 'edges': edges, 'selector': None}))
        elif hasattr(self, '_selected_edges'):
            self._operations.append(('chamfer', {'length': length, 'edges': self._selected_edges, 'selector': None}))
            delattr(self, '_selected_edges')
        elif hasattr(self, '_pending_selector'):
            selector_info = self._pending_selector.get_info() if hasattr(self._pending_selector, 'get_info') else None
            self._operations.append(('chamfer', {'length': length, 'edges': None, 'selector': selector_info}))
            delattr(self, '_pending_selector')
        return self

    def val(self) -> Any:
        """
        Execute all operations and return the resulting solid.

        This is called automatically by the importer to extract the geometry.
        """
        if self._solid is not None:
            return self._solid

        if not self._operations:
            return None

        try:
            # Execute operations in BuildPart context
            with self.b123d.BuildPart() as part:
                self._context = part

                for op_type, params in self._operations:
                    if op_type == 'box':
                        align = self.b123d.Align.CENTER if params.get('centered', True) else self.b123d.Align.MIN
                        self.b123d.Box(params['length'], params['width'], params['height'], align=align)

                    elif op_type == 'cylinder':
                        align = self.b123d.Align.CENTER if params.get('centered', True) else self.b123d.Align.MIN
                        self.b123d.Cylinder(params['radius'], params['height'], align=align)

                    elif op_type == 'circle':
                        # Add circle - this needs to be in a sketch before extrude
                        # Store for next extrude operation
                        self._pending_circle = params['radius']

                    elif op_type == 'extrude':
                        plane = params.get('plane', self.plane)
                        with self.b123d.BuildSketch(plane):
                            if hasattr(self, '_pending_circle'):
                                self.b123d.Circle(self._pending_circle)
                                delattr(self, '_pending_circle')
                        self.b123d.extrude(amount=params['distance'])

                    elif op_type == 'fillet':
                        edges = params.get('edges')
                        selector_info = params.get('selector')

                        # If edges not provided but we have a selector, get edges from selector
                        if edges is None and selector_info is not None:
                            # Resolve selector to get actual edges
                            direction, axis = self._parse_selector_info(selector_info)
                            if direction is not None and axis is not None:
                                shapes = part.edges
                                if direction == '>':
                                    edges = list(shapes.filter_by(axis, reverse=True))
                                elif direction == '<':
                                    edges = list(shapes.filter_by(axis))
                                elif direction == '|':
                                    edges = list(shapes.filter_by(axis))
                                else:
                                    edges = list(shapes)

                        if edges is not None and len(edges) > 0:
                            self.b123d.fillet(edges, params['radius'])

                    elif op_type == 'chamfer':
                        edges = params.get('edges')
                        selector_info = params.get('selector')

                        # If edges not provided but we have a selector, get edges from selector
                        if edges is None and selector_info is not None:
                            direction, axis = self._parse_selector_info(selector_info)
                            if direction is not None and axis is not None:
                                shapes = part.edges
                                if direction == '>':
                                    edges = list(shapes.filter_by(axis, reverse=True))
                                elif direction == '<':
                                    edges = list(shapes.filter_by(axis))
                                elif direction == '|':
                                    edges = list(shapes.filter_by(axis))
                                else:
                                    edges = list(shapes)

                        if edges is not None and len(edges) > 0:
                            self.b123d.chamfer(edges, params['length'])

                # Cache the result
                if hasattr(part, '_obj'):
                    self._solid = part._obj

            return self._solid

        except Exception as e:
            logger.error(f"Workplane.val() failed: {e}")
            return None

    def _parse_selector_info(self, selector_info) -> Tuple:
        """Parse selector info tuple/dict."""
        if isinstance(selector_info, tuple):
            return selector_info
        elif isinstance(selector_info, dict):
            return (selector_info.get('direction'), selector_info.get('axis'))
        elif isinstance(selector_info, Selector):
            return selector_info._parse_selector()
        return None, None

    def workplane(self, offset: float = 0) -> 'Workplane':
        """Create a new workplane offset from current."""
        new_plane = self.plane.offset(offset) if offset != 0 else self.plane
        result = Workplane(self.adapter, '')
        result.plane = new_plane
        result._operations = self._operations.copy()  # Share operations
        return result

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, *args):
        """Context manager exit - finalize solid."""
        self.val()


class Selector:
    """
    CadQuery selector compatibility (.faces('>Z'), .edges('|Z')).

    Supports:
    - '>Z' - faces/edges in positive Z direction
    - '<Z' - faces/edges in negative Z direction
    - '|Z' - faces/edges parallel to Z axis
    - '>X', '<X', '|X' - X axis variants
    - '>Y', '<Y', '|Y' - Y axis variants
    """

    def __init__(self, workplane: Workplane, shape_type: str, selector: str):
        self.workplane = workplane
        self.b123d = workplane.b123d
        self.shape_type = shape_type
        self.selector = selector
        self._items = None

    def _parse_selector(self) -> Tuple:
        """Parse selector string into (direction, axis)."""
        if not self.selector:
            return None, None

        # Format: '>Z', '<X', '|Y', etc.
        if len(self.selector) >= 2:
            direction = self.selector[0]
            axis_char = self.selector[1].upper()

            # Map axis character to Axis object
            axis_map = {
                'X': self.b123d.Axis.X,
                'Y': self.b123d.Axis.Y,
                'Z': self.b123d.Axis.Z
            }
            axis = axis_map.get(axis_char)

            return (direction, axis)

        return None, None

    def get_info(self) -> Tuple:
        """Get parsed selector info (direction, axis) for deferred execution."""
        return self._parse_selector()

    def items(self):
        """Get selected items (faces or edges)."""
        if self._items is not None:
            return self._items

        if self.workplane._context is None:
            return []

        direction, axis = self._parse_selector()
        if direction is None or axis is None:
            return []

        part = self.workplane._context

        # Get faces or edges from part
        if self.shape_type == 'face':
            shapes = part.faces
        else:
            shapes = part.edges

        # Filter by direction
        if direction == '>':
            # Positive direction
            filtered = shapes.filter_by(axis, reverse=True)
        elif direction == '<':
            # Negative direction
            filtered = shapes.filter_by(axis)
        elif direction == '|':
            # Parallel to axis
            filtered = shapes.filter_by(axis)
        else:
            filtered = shapes

        self._items = list(filtered) if hasattr(filtered, '__iter__') else [filtered]
        return self._items

    def fillet(self, radius: float) -> Workplane:
        """Apply fillet to selected edges."""
        items = self.items()
        self.workplane._selected_edges = items
        return self.workplane.fillet(radius)

    def chamfer(self, length: float) -> Workplane:
        """Apply chamfer to selected edges."""
        items = self.items()
        self.workplane._selected_edges = items
        return self.workplane.chamfer(length)


def convert_workplane_to_build123d(code: str) -> str:
    """
    Convert CadQuery Workplane code to Build123d.

    This is a simple text-based conversion for common patterns.
    For complex scripts, use the runtime adapter instead.

    Conversions:
    - cq.Workplane('XY') -> removed (handled by adapter)
    - .box(1,2,3) -> Box(1,2,3)
    - .circle(r) -> Circle(r)
    - .extrude(d) -> extrude(amount=d)
    - .faces('>Z') -> faces().filter_by(Axis.Z)
    - .edges('|Z') -> edges().filter_by(Axis.Z)
    """
    # This is a simplified conversion - the adapter is preferred
    conversions = [
        (r'\.faces\([\'"]>([XYZ])[\'\" ]\)', r'.faces().filter_by(Axis.\1)'),
        (r'\.edges\([\'"]\|([XYZ])[\'\" ]\)', r'.edges().filter_by(Axis.\1)'),
    ]

    result = code
    for pattern, replacement in conversions:
        result = re.sub(pattern, replacement, result)

    return result


def create_cadquery_namespace(build123d_module) -> dict:
    """
    Create a namespace with both CadQuery and Build123d APIs.

    This allows scripts to use 'cq' namespace which actually calls Build123d.
    """
    adapter = WorkplaneAdapter(build123d_module)

    namespace = {
        'cq': type('obj', (object,), {
            'Workplane': lambda plane='XY': Workplane(adapter, plane)
        }),
        'Workplane': Workplane,
    }

    return namespace
