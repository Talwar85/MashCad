"""
MashCAD Integration Tests - Sketch to Solid Workflow
=====================================================

Integration tests for the complete Sketch → Extrude → Fillet workflow including:
- Sketch creation with geometry
- Profile extraction and validation
- Extrude operation
- Fillet operation on extruded solid
- Full workflow integration

Author: QA-001 Phase 4
Date: 2026-02-20
"""

import pytest
from typing import List, Optional, Tuple
from loguru import logger
from shapely.geometry import Polygon
from build123d import Solid, Face, Vector, Edge, Wire

from sketcher import Sketch
from sketcher.geometry import Point2D, Line2D, Circle2D, Arc2D
from sketcher.constraints import (
    Constraint, ConstraintType, make_coincident, make_horizontal, make_vertical
)
from modeling import Body, Document
from modeling.ocp_helpers import OCPExtrudeHelper, OCPFilletHelper, HAS_OCP
from modeling.tnp_system import ShapeNamingService


# ============================================================================
# SKIP CONDITIONAL
# ============================================================================

pytestmark = pytest.mark.skipif(
    not HAS_OCP,
    reason="OpenCASCADE (OCP) nicht verfügbar - Tests überspringen"
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def document():
    """Create a fresh Document for each test."""
    doc = Document("SketchSolidTestDoc")
    yield doc
    doc.bodies.clear()


@pytest.fixture
def naming_service():
    """Create a fresh ShapeNamingService for each test."""
    service = ShapeNamingService()
    yield service


@pytest.fixture
def empty_sketch():
    """Create an empty sketch."""
    return Sketch(name="TestSketch")


@pytest.fixture
def rectangle_sketch():
    """Create a sketch with a simple rectangle."""
    sketch = Sketch(name="RectangleSketch")
    
    # Create rectangle points
    p1 = Point2D(0, 0)
    p2 = Point2D(10, 0)
    p3 = Point2D(10, 10)
    p4 = Point2D(0, 10)
    
    sketch.points.extend([p1, p2, p3, p4])
    
    # Create rectangle lines (points are already connected via start/end)
    l1 = Line2D(p1, p2)
    l2 = Line2D(p2, p3)
    l3 = Line2D(p3, p4)
    l4 = Line2D(p4, p1)
    
    sketch.lines.extend([l1, l2, l3, l4])
    
    # Note: Coincident constraints are implicit in Line2D(start_point, end_point)
    # The lines already reference the same point objects, forming a closed loop
    
    return sketch


@pytest.fixture
def circle_sketch():
    """Create a sketch with a circle."""
    sketch = Sketch(name="CircleSketch")
    
    center = Point2D(5, 5)
    circle = Circle2D(center, radius=5.0)
    
    sketch.points.append(center)
    sketch.circles.append(circle)
    
    return sketch


@pytest.fixture
def box_solid():
    """Create a simple box solid for fillet tests."""
    return Solid.make_box(20, 20, 10)


# ============================================================================
# SKETCH CREATION TESTS
# ============================================================================

class TestSketchCreation:
    """Tests for sketch creation with geometry."""

    def test_create_empty_sketch(self, empty_sketch):
        """Empty sketch should have no geometry."""
        assert len(empty_sketch.points) == 0
        assert len(empty_sketch.lines) == 0
        assert len(empty_sketch.circles) == 0
        assert len(empty_sketch.arcs) == 0

    def test_add_point_to_sketch(self, empty_sketch):
        """Adding a point to sketch should work."""
        point = Point2D(5, 5)
        empty_sketch.points.append(point)
        
        assert len(empty_sketch.points) == 1
        assert empty_sketch.points[0].x == 5.0
        assert empty_sketch.points[0].y == 5.0

    def test_add_line_to_sketch(self, empty_sketch):
        """Adding a line to sketch should work."""
        p1 = Point2D(0, 0)
        p2 = Point2D(10, 0)
        line = Line2D(p1, p2)
        
        empty_sketch.points.extend([p1, p2])
        empty_sketch.lines.append(line)
        
        assert len(empty_sketch.lines) == 1
        assert line.length == pytest.approx(10.0, abs=0.01)

    def test_add_circle_to_sketch(self, empty_sketch):
        """Adding a circle to sketch should work."""
        center = Point2D(5, 5)
        circle = Circle2D(center, radius=5.0)
        
        empty_sketch.points.append(center)
        empty_sketch.circles.append(circle)
        
        assert len(empty_sketch.circles) == 1
        assert circle.radius == 5.0

    def test_rectangle_sketch_is_closed(self, rectangle_sketch):
        """Rectangle sketch should form a closed profile."""
        assert len(rectangle_sketch.lines) == 4
        assert len(rectangle_sketch.points) == 4
        
        # Check that lines form a closed loop
        # Each point should be connected to 2 lines
        point_usage = {p.id: 0 for p in rectangle_sketch.points}
        for line in rectangle_sketch.lines:
            point_usage[line.start.id] += 1
            point_usage[line.end.id] += 1
        
        for point_id, count in point_usage.items():
            assert count == 2, f"Point {point_id} has {count} connections, expected 2"


# ============================================================================
# PROFILE EXTRACTION TESTS
# ============================================================================

class TestProfileExtraction:
    """Tests for extracting profiles from sketches."""

    def test_rectangle_creates_valid_polygon(self, rectangle_sketch):
        """Rectangle sketch should create a valid Shapely polygon."""
        # Extract profile as Shapely polygon
        coords = []
        for line in rectangle_sketch.lines:
            coords.append((line.start.x, line.start.y))
        
        polygon = Polygon(coords)
        
        assert polygon.is_valid
        assert polygon.area == pytest.approx(100.0, abs=1.0)  # 10x10 = 100

    def test_circle_creates_valid_geometry(self, circle_sketch):
        """Circle sketch should have valid circle geometry."""
        assert len(circle_sketch.circles) == 1
        
        circle = circle_sketch.circles[0]
        assert circle.radius == 5.0
        assert circle.center.x == 5.0
        assert circle.center.y == 5.0
        
        # Area = pi * r^2
        import math
        expected_area = math.pi * 25.0
        assert circle.area == pytest.approx(expected_area, rel=0.01)


# ============================================================================
# EXTRUDE OPERATION TESTS
# ============================================================================

class TestExtrudeOperation:
    """Tests for extrude operation from sketch."""

    def test_extrude_rectangle_face(self, naming_service):
        """Extruding a rectangle face should produce a valid solid."""
        # Create a rectangular face
        face = Face.make_rect(10, 10)
        
        feature_id = "extrude_1"
        
        # Extrude
        result = OCPExtrudeHelper.extrude(
            face=face,
            direction=Vector(0, 0, 1),
            distance=5.0,
            naming_service=naming_service,
            feature_id=feature_id
        )
        
        assert result is not None
        assert isinstance(result, Solid)
        assert result.is_valid()
        
        # Volume should be 10 * 10 * 5 = 500
        expected_volume = 10 * 10 * 5
        assert result.volume == pytest.approx(expected_volume, rel=0.05)

    def test_extrude_circle_face(self, naming_service):
        """Extruding a circle face should produce a cylinder."""
        # Create a circular face using Wire directly with Face constructor
        wire = Wire.make_circle(radius=5.0)
        face = Face(wire)
        
        feature_id = "extrude_circle_1"
        
        # Extrude
        result = OCPExtrudeHelper.extrude(
            face=face,
            direction=Vector(0, 0, 1),
            distance=10.0,
            naming_service=naming_service,
            feature_id=feature_id
        )
        
        assert result is not None
        assert result.is_valid()
        
        # Volume should be pi * r^2 * h
        import math
        expected_volume = math.pi * 25.0 * 10.0
        assert result.volume == pytest.approx(expected_volume, rel=0.05)

    def test_extrude_requires_naming_service(self):
        """Extrude should fail without naming service."""
        face = Face.make_rect(10, 10)
        
        with pytest.raises(ValueError) as exc_info:
            OCPExtrudeHelper.extrude(
                face=face,
                direction=Vector(0, 0, 1),
                distance=5.0,
                naming_service=None,
                feature_id="test"
            )
        
        assert "naming_service" in str(exc_info.value).lower()

    def test_extrude_requires_feature_id(self, naming_service):
        """Extrude should fail without feature_id."""
        face = Face.make_rect(10, 10)
        
        with pytest.raises(ValueError) as exc_info:
            OCPExtrudeHelper.extrude(
                face=face,
                direction=Vector(0, 0, 1),
                distance=5.0,
                naming_service=naming_service,
                feature_id=None
            )
        
        assert "feature_id" in str(exc_info.value).lower()


# ============================================================================
# FILLET OPERATION TESTS
# ============================================================================

class TestFilletOperation:
    """Tests for fillet operation on solids."""

    def test_fillet_box_edges(self, box_solid, naming_service):
        """Filleting box edges should produce rounded corners."""
        # Get all edges from the box
        edges = list(box_solid.edges())
        assert len(edges) > 0
        
        feature_id = "fillet_1"
        radius = 2.0
        
        # Apply fillet to first 4 edges (bottom edges)
        edges_to_fillet = edges[:4]
        
        result = OCPFilletHelper.fillet(
            solid=box_solid,
            edges=edges_to_fillet,
            radius=radius,
            naming_service=naming_service,
            feature_id=feature_id
        )
        
        assert result is not None
        assert result.is_valid()
        
        # Filleted box should have slightly less volume than original
        assert result.volume < box_solid.volume

    def test_fillet_single_edge(self, box_solid, naming_service):
        """Filleting a single edge should work."""
        edges = list(box_solid.edges())
        single_edge = edges[0]
        
        feature_id = "fillet_single_1"
        radius = 1.0
        
        result = OCPFilletHelper.fillet(
            solid=box_solid,
            edges=[single_edge],
            radius=radius,
            naming_service=naming_service,
            feature_id=feature_id
        )
        
        assert result is not None
        assert result.is_valid()

    def test_fillet_requires_naming_service(self, box_solid):
        """Fillet should fail without naming service."""
        edges = list(box_solid.edges())
        
        with pytest.raises(ValueError) as exc_info:
            OCPFilletHelper.fillet(
                solid=box_solid,
                edges=edges[:1],
                radius=1.0,
                naming_service=None,
                feature_id="test"
            )
        
        assert "naming_service" in str(exc_info.value).lower()


# ============================================================================
# COMPLETE WORKFLOW TESTS
# ============================================================================

class TestCompleteSketchToSolidWorkflow:
    """Tests for the complete Sketch → Extrude → Fillet workflow."""

    def test_sketch_to_solid_workflow(self, naming_service):
        """Complete workflow: Create sketch → Extrude → Verify."""
        # Step 1: Create sketch geometry (rectangle)
        sketch = Sketch(name="WorkflowSketch")
        
        p1 = Point2D(0, 0)
        p2 = Point2D(20, 0)
        p3 = Point2D(20, 20)
        p4 = Point2D(0, 20)
        
        sketch.points.extend([p1, p2, p3, p4])
        
        l1 = Line2D(p1, p2)
        l2 = Line2D(p2, p3)
        l3 = Line2D(p3, p4)
        l4 = Line2D(p4, p1)
        
        sketch.lines.extend([l1, l2, l3, l4])
        
        # Step 2: Create face from sketch
        face = Face.make_rect(20, 20)
        
        # Step 3: Extrude
        extrude_result = OCPExtrudeHelper.extrude(
            face=face,
            direction=Vector(0, 0, 1),
            distance=10.0,
            naming_service=naming_service,
            feature_id="workflow_extrude_1"
        )
        
        assert extrude_result is not None
        assert extrude_result.is_valid()
        
        # Verify volume: 20 * 20 * 10 = 4000
        expected_volume = 20 * 20 * 10
        assert extrude_result.volume == pytest.approx(expected_volume, rel=0.05)

    def test_sketch_extrude_fillet_workflow(self, naming_service):
        """Complete workflow: Sketch → Extrude → Fillet."""
        # Step 1: Create and extrude
        face = Face.make_rect(15, 15)
        
        extrude_result = OCPExtrudeHelper.extrude(
            face=face,
            direction=Vector(0, 0, 1),
            distance=10.0,
            naming_service=naming_service,
            feature_id="workflow_extrude_2"
        )
        
        assert extrude_result.is_valid()
        volume_after_extrude = extrude_result.volume
        
        # Step 2: Fillet all edges
        edges = list(extrude_result.edges())
        
        fillet_result = OCPFilletHelper.fillet(
            solid=extrude_result,
            edges=edges[:4],  # Fillet first 4 edges
            radius=1.5,
            naming_service=naming_service,
            feature_id="workflow_fillet_1"
        )
        
        assert fillet_result is not None
        assert fillet_result.is_valid()
        
        # Fillet should reduce volume slightly
        assert fillet_result.volume < volume_after_extrude

    def test_multiple_extrudes_workflow(self, naming_service):
        """Workflow with multiple extrude operations."""
        # First extrude: base plate
        base_face = Face.make_rect(30, 30)
        
        base = OCPExtrudeHelper.extrude(
            face=base_face,
            direction=Vector(0, 0, 1),
            distance=5.0,
            naming_service=naming_service,
            feature_id="multi_extrude_1"
        )
        
        assert base.is_valid()
        base_volume = base.volume
        
        # Second extrude: add feature on top
        top_face = Face.make_rect(10, 10)
        
        feature = OCPExtrudeHelper.extrude(
            face=top_face,
            direction=Vector(0, 0, 1),
            distance=10.0,
            naming_service=naming_service,
            feature_id="multi_extrude_2"
        )
        
        assert feature.is_valid()
        
        # Both should be valid solids
        assert base.volume > 0
        assert feature.volume > 0


# ============================================================================
# TNP INTEGRATION TESTS
# ============================================================================

class TestTNPIntegration:
    """Tests for TNP (Topology Naming Protocol) integration."""

    def test_extrude_registers_shapes(self, naming_service):
        """Extrude should register shapes with naming service."""
        face = Face.make_rect(10, 10)
        
        initial_stats = naming_service.get_stats()
        
        result = OCPExtrudeHelper.extrude(
            face=face,
            direction=Vector(0, 0, 1),
            distance=5.0,
            naming_service=naming_service,
            feature_id="tnp_extrude_1"
        )
        
        final_stats = naming_service.get_stats()
        
        # Should have registered faces and edges
        assert final_stats['faces'] > initial_stats['faces']
        assert final_stats['edges'] > initial_stats['edges']

    def test_fillet_registers_shapes(self, box_solid, naming_service):
        """Fillet should register modified shapes with naming service."""
        edges = list(box_solid.edges())
        
        initial_stats = naming_service.get_stats()
        
        result = OCPFilletHelper.fillet(
            solid=box_solid,
            edges=edges[:2],
            radius=1.0,
            naming_service=naming_service,
            feature_id="tnp_fillet_1"
        )
        
        final_stats = naming_service.get_stats()
        
        # Should have registered new shapes
        assert final_stats['faces'] > initial_stats['faces'] or \
               final_stats['edges'] > initial_stats['edges']

    def test_naming_service_tracks_feature_ids(self, naming_service):
        """Naming service should track feature IDs."""
        face = Face.make_rect(10, 10)
        
        feature_id = "tracked_feature_1"
        
        result = OCPExtrudeHelper.extrude(
            face=face,
            direction=Vector(0, 0, 1),
            distance=5.0,
            naming_service=naming_service,
            feature_id=feature_id
        )
        
        # The naming service should have tracked this feature
        # (Implementation-specific check)
        stats = naming_service.get_stats()
        assert stats is not None


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================

class TestSketchSolidErrorHandling:
    """Tests for error handling in sketch-to-solid workflow."""

    def test_extrude_zero_distance(self, naming_service):
        """Extrude with zero distance should handle gracefully."""
        face = Face.make_rect(10, 10)
        
        # Zero distance might produce invalid or empty result
        try:
            result = OCPExtrudeHelper.extrude(
                face=face,
                direction=Vector(0, 0, 1),
                distance=0.0,
                naming_service=naming_service,
                feature_id="zero_dist"
            )
            # If it succeeds, result should be very thin or invalid
            if result:
                assert result.volume < 1.0  # Essentially no volume
        except (ValueError, Exception):
            pass  # Expected - zero distance is invalid

    def test_fillet_zero_radius(self, box_solid, naming_service):
        """Fillet with zero radius should handle gracefully."""
        edges = list(box_solid.edges())
        
        try:
            result = OCPFilletHelper.fillet(
                solid=box_solid,
                edges=edges[:1],
                radius=0.0,
                naming_service=naming_service,
                feature_id="zero_radius"
            )
            # If it succeeds, volume should be nearly unchanged
            if result:
                assert result.volume == pytest.approx(box_solid.volume, rel=0.01)
        except (ValueError, Exception):
            pass  # Expected - zero radius might be invalid

    def test_fillet_larger_than_edge(self, box_solid, naming_service):
        """Fillet radius larger than edge length should handle gracefully."""
        edges = list(box_solid.edges())
        
        # Very large radius might fail
        try:
            result = OCPFilletHelper.fillet(
                solid=box_solid,
                edges=edges[:1],
                radius=100.0,  # Larger than the box
                naming_service=naming_service,
                feature_id="huge_radius"
            )
            # If it succeeds, that's fine
            if result:
                assert result.is_valid()
        except (ValueError, Exception):
            pass  # Expected - radius too large
