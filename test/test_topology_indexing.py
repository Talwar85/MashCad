import numpy as np

from build123d import Solid

from modeling.cad_tessellator import CADTessellator
from modeling.shape_reference import create_reference_map, find_face_by_id
from modeling.topology_indexing import (
    dump_topology_edges,
    dump_topology_faces,
    edge_index_of,
    edge_from_index,
    face_index_of,
    face_from_index,
    iter_edges_with_indices,
    iter_faces_with_indices,
    map_index_to_edge,
    map_index_to_face,
)


def _make_box():
    return Solid.make_box(10.0, 20.0, 30.0)


def test_face_from_index_matches_build123d_faces_order():
    solid = _make_box()
    faces = list(solid.faces())
    assert len(faces) > 0

    for idx, expected in enumerate(faces):
        resolved = face_from_index(solid, idx)
        assert resolved is not None
        assert resolved.wrapped.IsSame(expected.wrapped)

        # Alias sollte identisch funktionieren
        resolved_alias = map_index_to_face(solid, idx)
        assert resolved_alias is not None
        assert resolved_alias.wrapped.IsSame(expected.wrapped)

    assert face_from_index(solid, -1) is None
    assert face_from_index(solid, len(faces)) is None


def test_edge_from_index_matches_build123d_edges_order():
    solid = _make_box()
    edges = list(solid.edges())
    assert len(edges) > 0

    for idx, expected in enumerate(edges):
        resolved = edge_from_index(solid, idx)
        assert resolved is not None
        assert resolved.wrapped.IsSame(expected.wrapped)

        resolved_alias = map_index_to_edge(solid, idx)
        assert resolved_alias is not None
        assert resolved_alias.wrapped.IsSame(expected.wrapped)

    assert edge_from_index(solid, -1) is None
    assert edge_from_index(solid, len(edges)) is None


def test_face_index_of_matches_enumerated_topology_index():
    solid = _make_box()
    for idx, face in enumerate(solid.faces()):
        assert face_index_of(solid, face) == idx


def test_edge_index_of_matches_enumerated_topology_index():
    solid = _make_box()
    for idx, edge in enumerate(solid.edges()):
        assert edge_index_of(solid, edge) == idx


def test_iter_faces_with_indices_is_dense_zero_based():
    solid = _make_box()
    indexed_faces = list(iter_faces_with_indices(solid))

    assert indexed_faces
    assert [idx for idx, _ in indexed_faces] == list(range(len(indexed_faces)))


def test_iter_edges_with_indices_is_dense_zero_based():
    solid = _make_box()
    indexed_edges = list(iter_edges_with_indices(solid))

    assert indexed_edges
    assert [idx for idx, _ in indexed_edges] == list(range(len(indexed_edges)))


def test_dump_topology_faces_contains_all_face_indices():
    solid = _make_box()
    dump = dump_topology_faces(solid)

    assert dump
    assert [entry["index"] for entry in dump] == list(range(len(dump)))
    assert all("center" in entry for entry in dump)


def test_dump_topology_edges_contains_all_edge_indices():
    solid = _make_box()
    dump = dump_topology_edges(solid)

    assert dump
    assert [entry["index"] for entry in dump] == list(range(len(dump)))
    assert all("center" in entry for entry in dump)


def test_tessellate_with_face_ids_uses_consistent_face_index_domain():
    solid = _make_box()
    mesh, _, face_info = CADTessellator.tessellate_with_face_ids(solid, quality=0.5)

    assert mesh is not None
    assert face_info
    assert "face_id" in mesh.cell_data

    face_ids = np.asarray(mesh.cell_data["face_id"], dtype=np.int32)
    assert face_ids.size > 0

    unique_ids = sorted(int(x) for x in np.unique(face_ids))
    expected_ids = list(range(len(list(solid.faces()))))
    assert unique_ids == expected_ids
    assert sorted(face_info.keys()) == expected_ids


def test_shape_reference_face_id_mapping_matches_topology_indexing():
    solid = _make_box()
    ref_map = create_reference_map(solid.wrapped)

    assert ref_map
    for idx in range(len(list(solid.faces()))):
        face_ocp = find_face_by_id(solid.wrapped, idx)
        assert face_ocp is not None

        mapped = face_from_index(solid, idx)
        assert mapped is not None
        assert mapped.wrapped.IsSame(face_ocp)


def test_face_from_index_prefers_direct_face_from_index_hook():
    sentinel = object()

    class _Shape:
        def face_from_index(self, index):
            return sentinel if index == 5 else None

    shape = _Shape()
    assert face_from_index(shape, 5) is sentinel
    assert face_from_index(shape, 3) is None


def test_edge_from_index_prefers_direct_edge_from_index_hook():
    sentinel = object()

    class _Shape:
        def edge_from_index(self, index):
            return sentinel if index == 2 else None

    shape = _Shape()
    assert edge_from_index(shape, 2) is sentinel
    assert edge_from_index(shape, 1) is None


def test_map_index_aliases_support_map_index_hooks():
    sentinel_face = object()
    sentinel_edge = object()

    class _Shape:
        def map_index_to_face(self, index):
            if index == 0:
                return sentinel_face
            return None

        def map_index_to_edge(self, index):
            if index == 0:
                return sentinel_edge
            return None

    shape = _Shape()
    assert map_index_to_face(shape, 0) is sentinel_face
    assert map_index_to_edge(shape, 0) is sentinel_edge
