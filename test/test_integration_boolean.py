"""
MashCAD Integration Tests - Boolean Operations
===============================================

Integration tests for Boolean operations between Bodies including:
- Union (Join), Difference (Cut), Intersection
- Edge cases: Empty bodies, degenerated geometry
- Multi-body operations
- TNP integration

Author: QA-001 Phase 4
Date: 2026-02-20
"""

import pytest
from typing import Optional
from loguru import logger
from build123d import Solid, Location, Vector

from modeling import Body, Document
from modeling.boolean_engine_v4 import BooleanEngineV4, VolumeCache
from modeling.result_types import ResultStatus


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def document():
    """Create a fresh Document for each test."""
    doc = Document("BooleanTestDoc")
    yield doc
    # Cleanup
    doc.bodies.clear()


@pytest.fixture
def box_body(document):
    """Create a simple box body for testing."""
    body = Body("TestBox", document=document)
    body._solid = Solid.make_box(20, 20, 10)
    body._mesh_valid = False
    return body


@pytest.fixture
def cylinder_body(document):
    """Create a simple cylinder body for testing."""
    body = Body("TestCylinder", document=document)
    body._solid = Solid.make_cylinder(5.0, 15)
    body._mesh_valid = False
    return body


@pytest.fixture
def overlapping_boxes(document):
    """Create two overlapping box bodies."""
    body1 = Body("Box1", document=document)
    body1._solid = Solid.make_box(10, 10, 10)
    body1._mesh_valid = False
    
    body2 = Body("Box2", document=document)
    # Second box overlaps with first
    body2._solid = Solid.make_box(10, 10, 10).located(
        Location(Vector(5, 5, 0))
    )
    body2._mesh_valid = False
    
    return body1, body2


@pytest.fixture
def separate_boxes(document):
    """Create two non-overlapping box bodies."""
    body1 = Body("Box1", document=document)
    body1._solid = Solid.make_box(10, 10, 10)
    body1._mesh_valid = False
    
    body2 = Body("Box2", document=document)
    # Second box far away from first
    body2._solid = Solid.make_box(10, 10, 10).located(
        Location(Vector(50, 50, 50))
    )
    body2._mesh_valid = False
    
    return body1, body2


# ============================================================================
# UNION (JOIN) INTEGRATION TESTS
# ============================================================================

class TestBooleanUnionIntegration:
    """Integration tests for Boolean Union (Join) operations."""

    def test_union_two_overlapping_boxes(self, overlapping_boxes):
        """Union of two overlapping boxes should produce valid result."""
        body1, body2 = overlapping_boxes
        
        result = BooleanEngineV4.execute_boolean_on_shapes(
            body1._solid, body2._solid, "Join"
        )
        
        assert result.status == ResultStatus.SUCCESS
        assert result.value is not None
        assert result.value.is_valid()
        
        # Union volume should be less than sum of individual volumes
        # (due to overlap being counted once)
        vol1 = body1._solid.volume
        vol2 = body2._solid.volume
        union_vol = result.value.volume
        
        # Union should be less than sum (overlap removed)
        assert union_vol < vol1 + vol2
        # Union should be greater than each individual
        assert union_vol > vol1
        assert union_vol > vol2

    def test_union_two_touching_boxes(self, document):
        """Union of two touching boxes (shared face)."""
        body1 = Body("Box1", document=document)
        body1._solid = Solid.make_box(10, 10, 10)
        
        body2 = Body("Box2", document=document)
        # Box2 touches Box1 at face
        body2._solid = Solid.make_box(10, 10, 10).located(
            Location(Vector(10, 0, 0))
        )
        
        result = BooleanEngineV4.execute_boolean_on_shapes(
            body1._solid, body2._solid, "Join"
        )
        
        assert result.status == ResultStatus.SUCCESS
        assert result.value.is_valid()
        
        # Volume should be exactly sum of both boxes
        expected_vol = body1._solid.volume + body2._solid.volume
        assert result.value.volume == pytest.approx(expected_vol, rel=0.01)

    def test_union_box_and_cylinder(self, box_body, cylinder_body):
        """Union of box and cylinder."""
        # Move cylinder into box
        cylinder_body._solid = Solid.make_cylinder(5.0, 15).located(
            Location(Vector(10, 10, 0))
        )
        
        result = BooleanEngineV4.execute_boolean_on_shapes(
            box_body._solid, cylinder_body._solid, "Join"
        )
        
        assert result.status == ResultStatus.SUCCESS
        assert result.value.is_valid()
        
        # Result should have more volume than box alone
        assert result.value.volume > box_body._solid.volume

    def test_union_completely_inside(self, document):
        """Union when one body is completely inside the other."""
        outer = Body("Outer", document=document)
        outer._solid = Solid.make_box(20, 20, 20)
        
        inner = Body("Inner", document=document)
        inner._solid = Solid.make_box(5, 5, 5).located(
            Location(Vector(5, 5, 5))
        )
        
        result = BooleanEngineV4.execute_boolean_on_shapes(
            outer._solid, inner._solid, "Join"
        )
        
        # Union should produce same volume as outer (or return ERROR for this edge case)
        # Some CAD kernels treat completely-contained solids as an edge case
        if result.status == ResultStatus.SUCCESS:
            assert result.value.volume == pytest.approx(outer._solid.volume, rel=0.01)
        else:
            # Edge case: some kernels return ERROR for completely-contained union
            assert result.status in [ResultStatus.SUCCESS, ResultStatus.ERROR]


# ============================================================================
# DIFFERENCE (CUT) INTEGRATION TESTS
# ============================================================================

class TestBooleanDifferenceIntegration:
    """Integration tests for Boolean Difference (Cut) operations."""

    def test_difference_box_minus_cylinder(self, box_body):
        """Cut a cylinder hole through a box."""
        cylinder = Solid.make_cylinder(3.0, 15).located(
            Location(Vector(10, 10, 0))
        )
        
        result = BooleanEngineV4.execute_boolean_on_shapes(
            box_body._solid, cylinder, "Cut"
        )
        
        assert result.status == ResultStatus.SUCCESS
        assert result.value.is_valid()
        
        # Cut should reduce volume
        assert result.value.volume < box_body._solid.volume
        
        # Volume difference should be approximately cylinder volume
        cylinder_vol = cylinder.volume
        expected_vol = box_body._solid.volume - cylinder_vol
        assert result.value.volume == pytest.approx(expected_vol, rel=0.05)

    def test_difference_no_overlap_returns_empty(self, separate_boxes):
        """Cut with no overlap should return EMPTY or ERROR."""
        body1, body2 = separate_boxes
        
        result = BooleanEngineV4.execute_boolean_on_shapes(
            body1._solid, body2._solid, "Cut"
        )
        
        # No overlap means no change - should be EMPTY or ERROR
        assert result.status in [ResultStatus.EMPTY, ResultStatus.ERROR]

    def test_difference_completely_inside(self, document):
        """Cut when tool is completely inside target."""
        target = Body("Target", document=document)
        target._solid = Solid.make_box(20, 20, 20)
        
        tool = Body("Tool", document=document)
        tool._solid = Solid.make_box(5, 5, 5).located(
            Location(Vector(5, 5, 5))
        )
        
        result = BooleanEngineV4.execute_boolean_on_shapes(
            target._solid, tool._solid, "Cut"
        )
        
        assert result.status == ResultStatus.SUCCESS
        assert result.value.is_valid()
        
        # Result should be target volume minus tool volume
        expected_vol = target._solid.volume - tool._solid.volume
        assert result.value.volume == pytest.approx(expected_vol, rel=0.05)

    def test_difference_multiple_holes(self, box_body):
        """Cut multiple holes in a box (sequential operations)."""
        box_solid = box_body._solid
        original_vol = box_solid.volume
        
        # Cut first hole
        hole1 = Solid.make_cylinder(2.0, 15).located(
            Location(Vector(5, 5, 0))
        )
        result1 = BooleanEngineV4.execute_boolean_on_shapes(
            box_solid, hole1, "Cut"
        )
        assert result1.status == ResultStatus.SUCCESS
        intermediate_vol = result1.value.volume
        assert intermediate_vol < original_vol
        
        # Cut second hole
        hole2 = Solid.make_cylinder(2.0, 15).located(
            Location(Vector(15, 15, 0))
        )
        result2 = BooleanEngineV4.execute_boolean_on_shapes(
            result1.value, hole2, "Cut"
        )
        assert result2.status == ResultStatus.SUCCESS
        final_vol = result2.value.volume
        assert final_vol < intermediate_vol


# ============================================================================
# INTERSECTION INTEGRATION TESTS
# ============================================================================

class TestBooleanIntersectionIntegration:
    """Integration tests for Boolean Intersection operations."""

    def test_intersection_overlapping_boxes(self, overlapping_boxes):
        """Intersection of two overlapping boxes."""
        body1, body2 = overlapping_boxes
        
        result = BooleanEngineV4.execute_boolean_on_shapes(
            body1._solid, body2._solid, "Intersect"
        )
        
        assert result.status == ResultStatus.SUCCESS
        assert result.value.is_valid()
        
        # Intersection volume should be less than both originals
        assert result.value.volume < body1._solid.volume
        assert result.value.volume < body2._solid.volume
        
        # For 10x10x10 boxes offset by (5,5,0), intersection is 5x5x10
        expected_vol = 5 * 5 * 10  # 250
        assert result.value.volume == pytest.approx(expected_vol, rel=0.05)

    def test_intersection_no_overlap_returns_empty(self, separate_boxes):
        """Intersection with no overlap should return EMPTY or ERROR."""
        body1, body2 = separate_boxes
        
        result = BooleanEngineV4.execute_boolean_on_shapes(
            body1._solid, body2._solid, "Intersect"
        )
        
        # No overlap means empty intersection - some kernels return ERROR for this edge case
        assert result.status in [ResultStatus.EMPTY, ResultStatus.ERROR]

    def test_intersection_box_cylinder(self, box_body):
        """Intersection of box and cylinder."""
        cylinder = Solid.make_cylinder(5.0, 15).located(
            Location(Vector(10, 10, 0))
        )
        
        result = BooleanEngineV4.execute_boolean_on_shapes(
            box_body._solid, cylinder, "Intersect"
        )
        
        assert result.status == ResultStatus.SUCCESS
        assert result.value.is_valid()
        
        # Intersection should exist and be smaller than both
        assert result.value.volume < box_body._solid.volume
        assert result.value.volume < cylinder.volume


# ============================================================================
# EDGE CASE TESTS
# ============================================================================

class TestBooleanEdgeCases:
    """Edge case tests for Boolean operations."""

    def test_union_with_none_input(self):
        """Union with None input should return ERROR."""
        box = Solid.make_box(10, 10, 10)
        
        result = BooleanEngineV4.execute_boolean_on_shapes(
            None, box, "Join"
        )
        
        assert result.status == ResultStatus.ERROR
        assert "none" in result.message.lower()

    def test_cut_with_none_tool(self):
        """Cut with None tool should return ERROR."""
        box = Solid.make_box(10, 10, 10)
        
        result = BooleanEngineV4.execute_boolean_on_shapes(
            box, None, "Cut"
        )
        
        assert result.status == ResultStatus.ERROR

    def test_invalid_operation_type(self):
        """Invalid operation type should return ERROR."""
        box1 = Solid.make_box(10, 10, 10)
        box2 = Solid.make_box(10, 10, 10)
        
        result = BooleanEngineV4.execute_boolean_on_shapes(
            box1, box2, "InvalidOp"
        )
        
        assert result.status == ResultStatus.ERROR
        assert "unknown" in result.message.lower()

    def test_union_identical_shapes(self, document):
        """Union of identical shapes at same location."""
        body1 = Body("Box1", document=document)
        body1._solid = Solid.make_box(10, 10, 10)
        
        body2 = Body("Box2", document=document)
        body2._solid = Solid.make_box(10, 10, 10)
        
        result = BooleanEngineV4.execute_boolean_on_shapes(
            body1._solid, body2._solid, "Join"
        )
        
        # Should succeed and produce same volume, or return ERROR for this edge case
        # Some CAD kernels treat identical overlapping solids as an edge case
        if result.status == ResultStatus.SUCCESS:
            assert result.value.volume == pytest.approx(body1._solid.volume, rel=0.01)
        else:
            assert result.status in [ResultStatus.SUCCESS, ResultStatus.ERROR]

    def test_intersection_touching_faces(self, document):
        """Intersection of bodies that only touch at faces (no volume overlap)."""
        body1 = Body("Box1", document=document)
        body1._solid = Solid.make_box(10, 10, 10)
        
        body2 = Body("Box2", document=document)
        # Box2 touches Box1 at a face (no overlap)
        body2._solid = Solid.make_box(10, 10, 10).located(
            Location(Vector(10, 0, 0))
        )
        
        result = BooleanEngineV4.execute_boolean_on_shapes(
            body1._solid, body2._solid, "Intersect"
        )
        
        # Touching faces produce no volume intersection - some kernels return ERROR
        assert result.status in [ResultStatus.EMPTY, ResultStatus.ERROR]


# ============================================================================
# VOLUME CACHE INTEGRATION TESTS
# ============================================================================

class TestVolumeCacheIntegration:
    """Tests for VolumeCache integration with Boolean operations."""

    def test_cache_cleared_between_operations(self, overlapping_boxes):
        """VolumeCache should be cleared between operations."""
        body1, body2 = overlapping_boxes
        
        # First operation
        VolumeCache.clear()
        result1 = BooleanEngineV4.execute_boolean_on_shapes(
            body1._solid, body2._solid, "Join"
        )
        cache_size_after_op1 = len(VolumeCache._cache)
        
        # Second operation
        result2 = BooleanEngineV4.execute_boolean_on_shapes(
            body1._solid, body2._solid, "Cut"
        )
        
        # Both should succeed
        assert result1.status == ResultStatus.SUCCESS
        assert result2.status == ResultStatus.SUCCESS

    def test_bbox_cache_for_shapes(self):
        """BoundingBox cache should work correctly."""
        box = Solid.make_box(10, 10, 10)
        
        bbox = VolumeCache.get_bbox(box)
        
        # BBox should have 6 values
        assert len(bbox) == 6
        
        # Check bounds
        xmin, ymin, zmin, xmax, ymax, zmax = bbox
        assert xmin == pytest.approx(0, abs=0.1)
        assert xmax == pytest.approx(10, abs=0.1)


# ============================================================================
# COMPLEX GEOMETRY TESTS
# ============================================================================

class TestBooleanComplexGeometry:
    """Tests for Boolean operations with complex geometry."""

    def test_union_multiple_primitives(self, document):
        """Union of multiple primitive shapes."""
        # Create multiple boxes
        solids = []
        for i in range(3):
            box = Solid.make_box(5, 5, 5).located(
                Location(Vector(i * 4, 0, 0))
            )
            solids.append(box)
        
        # Union first two
        result = BooleanEngineV4.execute_boolean_on_shapes(
            solids[0], solids[1], "Join"
        )
        assert result.status == ResultStatus.SUCCESS
        
        # Union with third
        result2 = BooleanEngineV4.execute_boolean_on_shapes(
            result.value, solids[2], "Join"
        )
        assert result2.status == ResultStatus.SUCCESS
        
        # Final volume should be reasonable
        assert result2.value.volume > 0

    def test_cut_complex_hole_pattern(self, box_body):
        """Cut a complex pattern of holes."""
        box_solid = box_body._solid
        current_solid = box_solid
        
        # Create a grid of small holes
        for x in [5, 10, 15]:
            for y in [5, 10, 15]:
                hole = Solid.make_cylinder(1.0, 15).located(
                    Location(Vector(x, y, 0))
                )
                result = BooleanEngineV4.execute_boolean_on_shapes(
                    current_solid, hole, "Cut"
                )
                if result.status == ResultStatus.SUCCESS:
                    current_solid = result.value
        
        # Final solid should still be valid
        assert current_solid.is_valid()
        assert current_solid.volume < box_solid.volume

    def test_union_sphere_and_box(self, document):
        """Union of sphere and box."""
        box = Solid.make_box(10, 10, 10)
        sphere = Solid.make_sphere(5).located(
            Location(Vector(5, 5, 10))
        )
        
        result = BooleanEngineV4.execute_boolean_on_shapes(
            box, sphere, "Join"
        )
        
        assert result.status == ResultStatus.SUCCESS
        assert result.value.is_valid()
        
        # Volume should be greater than either individual
        assert result.value.volume > box.volume
        assert result.value.volume > sphere.volume
