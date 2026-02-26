"""
TNP v5.0 - Adjacency Tracker Tests

Unit tests for the adjacency tracking functionality.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch

from modeling.tnp_v5 import (
    AdjacencyTracker,
    AdjacencyGraph,
    compute_adjacency_similarity,
    ShapeID,
    ShapeType
)


class TestAdjacencyGraph:
    """Test AdjacencyGraph dataclass."""

    def test_init(self):
        """Test graph initialization."""
        graph = AdjacencyGraph()
        assert len(graph._adjacency) == 0
        assert len(graph._edge_to_faces) == 0
        assert len(graph._face_to_edges) == 0
        assert len(graph._vertex_to_edges) == 0

    def test_add_adjacency(self):
        """Test adding adjacency between shapes."""
        graph = AdjacencyGraph()
        graph.add_adjacency("shape_a", "shape_b")

        assert "shape_b" in graph._adjacency["shape_a"]
        assert "shape_a" in graph._adjacency["shape_b"]

    def test_add_adjacency_idempotent(self):
        """Test adding same adjacency multiple times."""
        graph = AdjacencyGraph()
        graph.add_adjacency("shape_a", "shape_b")
        graph.add_adjacency("shape_a", "shape_b")

        assert len(graph._adjacency["shape_a"]) == 1
        assert len(graph._adjacency["shape_b"]) == 1

    def test_add_adjacency_ignores_self(self):
        """Test that self-adjacency is ignored."""
        graph = AdjacencyGraph()
        graph.add_adjacency("shape_a", "shape_a")

        assert len(graph._adjacency) == 0

    def test_add_adjacency_ignores_none(self):
        """Test that None values are handled."""
        graph = AdjacencyGraph()
        graph.add_adjacency("shape_a", None)
        graph.add_adjacency(None, "shape_b")
        graph.add_adjacency(None, None)

        assert len(graph._adjacency) == 0

    def test_remove_adjacency(self):
        """Test removing adjacency."""
        graph = AdjacencyGraph()
        graph.add_adjacency("shape_a", "shape_b")
        graph.remove_adjacency("shape_a", "shape_b")

        assert "shape_b" not in graph._adjacency["shape_a"]
        assert "shape_a" not in graph._adjacency["shape_b"]

    def test_remove_nonexistent_adjacency(self):
        """Test removing non-existent adjacency doesn't error."""
        graph = AdjacencyGraph()
        graph.remove_adjacency("shape_a", "shape_b")  # Should not error

    def test_get_adjacent(self):
        """Test getting adjacent shapes."""
        graph = AdjacencyGraph()
        graph.add_adjacency("shape_a", "shape_b")
        graph.add_adjacency("shape_a", "shape_c")

        adjacent = graph.get_adjacent("shape_a")
        assert adjacent == {"shape_b", "shape_c"}

    def test_get_adjacent_returns_copy(self):
        """Test that get_adjacent returns a copy."""
        graph = AdjacencyGraph()
        graph.add_adjacency("shape_a", "shape_b")

        adjacent = graph.get_adjacent("shape_a")
        adjacent.add("shape_c")

        assert "shape_c" not in graph._adjacency["shape_a"]

    def test_get_adjacent_empty_for_unknown(self):
        """Test getting adjacent for unknown shape."""
        graph = AdjacencyGraph()
        assert graph.get_adjacent("unknown") == set()

    def test_are_adjacent(self):
        """Test checking if shapes are adjacent."""
        graph = AdjacencyGraph()
        graph.add_adjacency("shape_a", "shape_b")

        assert graph.are_adjacent("shape_a", "shape_b")
        assert graph.are_adjacent("shape_b", "shape_a")
        assert not graph.are_adjacent("shape_a", "shape_c")

    def test_clear(self):
        """Test clearing the graph."""
        graph = AdjacencyGraph()
        graph.add_adjacency("shape_a", "shape_b")
        graph._edge_to_faces["edge1"].add("face1")

        graph.clear()

        assert len(graph._adjacency) == 0
        assert len(graph._edge_to_faces) == 0

    def test_size_property(self):
        """Test size property."""
        graph = AdjacencyGraph()
        assert graph.size == 0

        graph.add_adjacency("shape_a", "shape_b")
        assert graph.size == 2

        graph.add_adjacency("shape_c", "shape_d")
        assert graph.size == 4


class TestAdjacencyTracker:
    """Test AdjacencyTracker class."""

    def test_init(self):
        """Test tracker initialization."""
        tracker = AdjacencyTracker()
        assert tracker._graph.size == 0
        assert tracker._build_count == 0
        assert tracker._last_build_size == 0

    def test_add_adjacency(self):
        """Test manually adding adjacency."""
        tracker = AdjacencyTracker()
        tracker.add_adjacency("shape_a", "shape_b")

        assert tracker.get_adjacent("shape_a") == {"shape_b"}
        assert tracker.get_adjacent("shape_b") == {"shape_a"}

    def test_get_adjacent(self):
        """Test getting adjacent shapes."""
        tracker = AdjacencyTracker()
        tracker.add_adjacency("shape_a", "shape_b")
        tracker.add_adjacency("shape_a", "shape_c")

        result = tracker.get_adjacent("shape_a")
        assert result == {"shape_b", "shape_c"}

    def test_are_adjacent(self):
        """Test checking adjacency."""
        tracker = AdjacencyTracker()
        tracker.add_adjacency("shape_a", "shape_b")

        assert tracker.are_adjacent("shape_a", "shape_b")
        assert not tracker.are_adjacent("shape_a", "shape_c")

    def test_get_adjacent_faces(self):
        """Test getting faces for an edge."""
        tracker = AdjacencyTracker()
        tracker._graph._edge_to_faces["edge1"].add("face1")
        tracker._graph._edge_to_faces["edge1"].add("face2")

        faces = tracker.get_adjacent_faces("edge1")
        assert faces == {"face1", "face2"}

    def test_get_adjacent_edges(self):
        """Test getting edges for a face."""
        tracker = AdjacencyTracker()
        tracker._graph._face_to_edges["face1"].add("edge1")
        tracker._graph._face_to_edges["face1"].add("edge2")

        edges = tracker.get_adjacent_edges("face1")
        assert edges == {"edge1", "edge2"}

    def test_get_adjacent_edges_for_vertex(self):
        """Test getting edges for a vertex."""
        tracker = AdjacencyTracker()
        tracker._graph._vertex_to_edges["vertex1"].add("edge1")
        tracker._graph._vertex_to_edges["vertex1"].add("edge2")

        edges = tracker.get_adjacent_edges_for_vertex("vertex1")
        assert edges == {"edge1", "edge2"}

    def test_get_shared_faces(self):
        """Test getting faces shared by two edges."""
        tracker = AdjacencyTracker()
        tracker._graph._edge_to_faces["edge1"] = {"face1", "face2"}
        tracker._graph._edge_to_faces["edge2"] = {"face2", "face3"}

        shared = tracker.get_shared_faces("edge1", "edge2")
        assert shared == {"face2"}

    def test_get_shared_faces_empty(self):
        """Test getting shared faces when none."""
        tracker = AdjacencyTracker()
        tracker._graph._edge_to_faces["edge1"] = {"face1"}
        tracker._graph._edge_to_faces["edge2"] = {"face2"}

        shared = tracker.get_shared_faces("edge1", "edge2")
        assert shared == set()

    def test_find_shortest_path_direct(self):
        """Test finding shortest path with direct adjacency."""
        tracker = AdjacencyTracker()
        tracker.add_adjacency("a", "b")
        tracker.add_adjacency("b", "c")

        path = tracker.find_shortest_path("a", "b")
        assert path == ["a", "b"]

    def test_find_shortest_path_two_hop(self):
        """Test finding shortest path with two hops."""
        tracker = AdjacencyTracker()
        tracker.add_adjacency("a", "b")
        tracker.add_adjacency("b", "c")

        path = tracker.find_shortest_path("a", "c")
        assert path == ["a", "b", "c"]

    def test_find_shortest_path_no_path(self):
        """Test finding path when none exists."""
        tracker = AdjacencyTracker()
        tracker.add_adjacency("a", "b")
        tracker.add_adjacency("c", "d")  # Disconnected component

        path = tracker.find_shortest_path("a", "c")
        assert path is None

    def test_find_shortest_path_same_node(self):
        """Test finding path to same node."""
        tracker = AdjacencyTracker()
        tracker.add_adjacency("a", "b")

        path = tracker.find_shortest_path("a", "a")
        assert path == ["a"]

    def test_find_shortest_path_max_hops(self):
        """Test max_hops limit."""
        tracker = AdjacencyTracker()
        tracker.add_adjacency("a", "b")
        tracker.add_adjacency("b", "c")
        tracker.add_adjacency("c", "d")
        tracker.add_adjacency("d", "e")

        # Should find path within max_hops
        path = tracker.find_shortest_path("a", "d", max_hops=2)
        assert path == ["a", "b", "c", "d"]

        # Should return None if path too long
        path = tracker.find_shortest_path("a", "e", max_hops=2)
        assert path is None

    def test_find_path_via_shape_type(self):
        """Test finding path via specific shape type."""
        tracker = AdjacencyTracker()
        tracker.add_adjacency("face1", "edge1")
        tracker.add_adjacency("edge1", "face2")

        # Create shape records with types
        shape_records = {}
        for name, shape_type in [("face1", ShapeType.FACE),
                                  ("edge1", ShapeType.EDGE),
                                  ("face2", ShapeType.FACE)]:
            sid = ShapeID.create(shape_type, "test", 0, (name,))
            record = Mock()
            record.shape_id = sid
            shape_records[name] = record

        path = tracker.find_path_via_shape_type(
            "face1", "face2", shape_records, ShapeType.EDGE
        )
        assert path == ["face1", "edge1", "face2"]

    def test_find_path_via_shape_type_wrong_type(self):
        """Test path via wrong type returns None."""
        tracker = AdjacencyTracker()
        tracker.add_adjacency("face1", "edge1")
        tracker.add_adjacency("edge1", "face2")

        shape_records = {}
        for name, shape_type in [("face1", ShapeType.FACE),
                                  ("edge1", ShapeType.EDGE),
                                  ("face2", ShapeType.FACE)]:
            sid = ShapeID.create(shape_type, "test", 0, (name,))
            record = Mock()
            record.shape_id = sid
            shape_records[name] = record

        # Looking for VERTEX intermediate but only EDGE exists
        path = tracker.find_path_via_shape_type(
            "face1", "face2", shape_records, ShapeType.VERTEX
        )
        assert path is None

    def test_get_stats(self):
        """Test getting statistics."""
        tracker = AdjacencyTracker()
        tracker.add_adjacency("a", "b")
        tracker.add_adjacency("a", "c")
        tracker.add_adjacency("d", "e")

        stats = tracker.get_stats()

        assert stats['num_shapes'] == 5  # a, b, c, d, e
        # a has degree 2, b has 1, c has 1, d has 1, e has 1
        # avg = (2 + 1 + 1 + 1 + 1) / 5 = 1.2
        assert stats['avg_degree'] == 1.2
        assert stats['max_degree'] == 2  # node 'a'
        assert stats['build_count'] == 0
        assert stats['last_build_size'] == 0

    def test_clear(self):
        """Test clearing tracker."""
        tracker = AdjacencyTracker()
        tracker.add_adjacency("a", "b")
        tracker._graph._edge_to_faces["edge1"].add("face1")

        tracker.clear()

        assert tracker._graph.size == 0
        assert len(tracker._graph._edge_to_faces) == 0

    def test_to_dict(self):
        """Test serialization to dict."""
        tracker = AdjacencyTracker()
        tracker.add_adjacency("a", "b")
        tracker._graph._edge_to_faces["edge1"] = {"face1"}

        data = tracker.to_dict()

        assert 'adjacency' in data
        assert 'edge_to_faces' in data
        assert 'face_to_edges' in data
        assert 'stats' in data
        assert data['adjacency']['a'] == ['b']
        assert data['adjacency']['b'] == ['a']

    def test_from_dict(self):
        """Test deserialization from dict."""
        data = {
            'adjacency': {'a': ['b'], 'b': ['a']},
            'edge_to_faces': {'edge1': ['face1']},
            'face_to_edges': {},
            'vertex_to_edges': {}
        }

        tracker = AdjacencyTracker.from_dict(data)

        assert tracker.get_adjacent("a") == {"b"}
        assert tracker.get_adjacent_faces("edge1") == {"face1"}

    def test_from_dict_roundtrip(self):
        """Test serialization roundtrip."""
        tracker1 = AdjacencyTracker()
        tracker1.add_adjacency("a", "b")
        tracker1.add_adjacency("b", "c")
        tracker1._graph._edge_to_faces["edge1"] = {"face1"}

        data = tracker1.to_dict()
        tracker2 = AdjacencyTracker.from_dict(data)

        assert tracker2.get_adjacent("a") == {"b"}
        assert tracker2.get_adjacent("b") == {"a", "c"}
        assert tracker2.get_adjacent_faces("edge1") == {"face1"}


class TestBuildFromSolid:
    """Test building adjacency from solid."""

    def test_build_from_solid_empty(self):
        """Test building with empty shape records."""
        tracker = AdjacencyTracker()

        # Empty shape_records should return 0
        count = tracker.build_from_solid(None, {})
        assert count == 0

    def test_build_from_solid_creates_map(self):
        """Test that OCP map is created during build."""
        tracker = AdjacencyTracker()

        # Create mock shape records with proper hash implementation
        mock_edge = Mock()
        mock_edge_wrapped = Mock()
        mock_edge.wrapped = mock_edge_wrapped

        mock_face = Mock()
        mock_face_wrapped = Mock()
        mock_face.wrapped = mock_face_wrapped

        shape_records = {
            "edge_uuid": Mock(ocp_shape=mock_edge),
            "face_uuid": Mock(ocp_shape=mock_face)
        }

        ocp_map = tracker._build_ocp_map(shape_records)

        # Map should have entries using object id()
        assert len(ocp_map) == 2

    def test_build_ocp_map_with_shape_id(self):
        """Test building OCP map from shape_id nested structure."""
        tracker = AdjacencyTracker()

        # Create a proper mock structure
        mock_ocp_wrapped = Mock()

        sid = ShapeID.create(ShapeType.EDGE, "test", 0, ())

        # Create record with shape_id containing ocp_shape
        record = Mock()
        record.ocp_shape = None
        record.shape_id = sid
        # Note: ShapeID doesn't have ocp_shape attribute in our implementation
        # The _build_ocp_map checks record.ocp_shape first

        ocp_map = tracker._build_ocp_map({"edge_uuid": record})

        # Since record.ocp_shape is None and shape_id doesn't have ocp_shape,
        # the map should be empty for this record
        assert isinstance(ocp_map, dict)


class TestComputeAdjacencySimilarity:
    """Test adjacency similarity computation."""

    def test_similarity_identical(self):
        """Test identical adjacency sets."""
        tracker = AdjacencyTracker()
        tracker.add_adjacency("a", "x")
        tracker.add_adjacency("a", "y")
        tracker.add_adjacency("b", "x")
        tracker.add_adjacency("b", "y")

        similarity = compute_adjacency_similarity(tracker, "a", "b")
        assert similarity == 1.0

    def test_similarity_disjoint(self):
        """Test disjoint adjacency sets."""
        tracker = AdjacencyTracker()
        tracker.add_adjacency("a", "x")
        tracker.add_adjacency("a", "y")
        tracker.add_adjacency("b", "z")
        tracker.add_adjacency("b", "w")

        similarity = compute_adjacency_similarity(tracker, "a", "b")
        assert similarity == 0.0

    def test_similarity_partial(self):
        """Test partially overlapping adjacency sets."""
        tracker = AdjacencyTracker()
        tracker.add_adjacency("a", "x")
        tracker.add_adjacency("a", "y")
        tracker.add_adjacency("a", "z")
        tracker.add_adjacency("b", "x")
        tracker.add_adjacency("b", "y")
        tracker.add_adjacency("b", "w")

        similarity = compute_adjacency_similarity(tracker, "a", "b")
        # Jaccard: intersection(2) / union(4) = 0.5
        assert abs(similarity - 0.5) < 0.01

    def test_similarity_both_empty(self):
        """Test both shapes have no adjacents."""
        tracker = AdjacencyTracker()

        similarity = compute_adjacency_similarity(tracker, "a", "b")
        assert similarity == 1.0

    def test_similarity_one_empty(self):
        """Test one shape has no adjacents."""
        tracker = AdjacencyTracker()
        tracker.add_adjacency("a", "x")

        similarity = compute_adjacency_similarity(tracker, "a", "b")
        assert similarity == 0.0

    def test_compute_adjacency_similarity_direct(self):
        """Test using imported function."""
        from modeling.tnp_v5.adjacency import compute_adjacency_similarity as func

        tracker = AdjacencyTracker()
        tracker.add_adjacency("a", "x")
        tracker.add_adjacency("b", "x")

        similarity = func(tracker, "a", "b")
        assert similarity > 0


class TestAdjacencyTrackerIntegration:
    """Integration tests for AdjacencyTracker."""

    def test_face_edge_topology(self):
        """Test tracking face-edge relationships."""
        tracker = AdjacencyTracker()

        # Create a simple topology: face with 4 edges
        face_uuid = "face1"
        edge_uuids = ["edge1", "edge2", "edge3", "edge4"]

        for edge_uuid in edge_uuids:
            tracker.add_adjacency(face_uuid, edge_uuid)
            tracker._graph._face_to_edges[face_uuid].add(edge_uuid)
            tracker._graph._edge_to_faces[edge_uuid].add(face_uuid)

        # Query back
        assert tracker.get_adjacent_edges(face_uuid) == set(edge_uuids)
        for edge_uuid in edge_uuids:
            assert tracker.get_adjacent_faces(edge_uuid) == {face_uuid}

    def test_path_finding_complex(self):
        """Test path finding in complex graph."""
        tracker = AdjacencyTracker()

        # Create a diamond graph
        #     a
        #    / \
        #   b   c
        #    \ /
        #     d
        tracker.add_adjacency("a", "b")
        tracker.add_adjacency("a", "c")
        tracker.add_adjacency("b", "d")
        tracker.add_adjacency("c", "d")

        # Shortest path from a to d
        path = tracker.find_shortest_path("a", "d")
        assert len(path) == 3  # a -> b/c -> d
        assert path[0] == "a"
        assert path[-1] == "d"

    def test_statistics_accuracy(self):
        """Test statistics are accurate."""
        tracker = AdjacencyTracker()

        # Create known topology
        for i in range(10):
            tracker.add_adjacency(f"node_{i}", f"node_{i+1}")

        stats = tracker.get_stats()

        assert stats['num_shapes'] == 11  # 0-10
        assert stats['avg_degree'] > 0
        assert stats['max_degree'] == 2  # Interior nodes have degree 2
