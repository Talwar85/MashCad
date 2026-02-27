"""
Performance under load tests using current modeling APIs.
"""

import gc
import time

from shapely.geometry import Polygon

from build123d import Box, Location

from modeling import Body, Document, ExtrudeFeature, FilletFeature, PrimitiveFeature
from modeling.performance_benchmark import BenchmarkTimer
from modeling.topology_indexing import edge_index_of, face_index_of
from modeling.tnp_system import ShapeType


def _make_imported_box_body(name: str, size: float, offset_x: float = 0.0) -> Body:
    solid = Box(size, size, size).locate(Location((offset_x, 0.0, 0.0)))
    return Body.from_solid(solid, name=name)


def _warm_up_tessellation() -> None:
    warmup_body = _make_imported_box_body("warmup_body", 2.0, offset_x=-999.0)
    assert warmup_body.vtk_mesh is not None


def _make_doc_body(name: str) -> tuple[Document, Body]:
    doc = Document(f"{name}_doc")
    body = Body(name, document=doc)
    doc.add_body(body, set_active=True)
    return doc, body


def _is_non_error(status: str) -> bool:
    return str(status or "").upper() in {"OK", "SUCCESS", "WARNING", "COSMETIC"}


def _add_box_base(body: Body, *, length: float, width: float, height: float, name: str) -> PrimitiveFeature:
    feature = PrimitiveFeature(
        primitive_type="box",
        length=length,
        width=width,
        height=height,
        name=name,
    )
    body.add_feature(feature, rebuild=True)
    assert _is_non_error(feature.status), f"Base feature failed: {feature.status}"
    assert body._build123d_solid is not None
    return feature


def _pick_face_by_direction(solid, direction):
    dx, dy, dz = direction
    return max(
        list(solid.faces()),
        key=lambda face: (float(face.center().X) * dx)
        + (float(face.center().Y) * dy)
        + (float(face.center().Z) * dz),
    )


def _register_face_shape_id(doc: Document, face, feature_seed: str, local_index: int):
    center = face.center()
    return doc._shape_naming_service.register_shape(
        ocp_shape=face.wrapped,
        shape_type=ShapeType.FACE,
        feature_id=feature_seed,
        local_index=int(local_index),
        geometry_data=(float(center.X), float(center.Y), float(center.Z), float(face.area)),
    )


def _add_pushpull_join(
    doc: Document,
    body: Body,
    *,
    step_id: str,
    direction: tuple[float, float, float],
    distance: float,
) -> ExtrudeFeature:
    solid = body._build123d_solid
    assert solid is not None

    face = _pick_face_by_direction(solid, direction)
    face_idx = face_index_of(solid, face)
    assert face_idx is not None
    face_idx = int(face_idx)

    shape_id = _register_face_shape_id(doc, face, step_id, face_idx)
    feature = ExtrudeFeature(
        sketch=None,
        distance=float(distance),
        operation="Join",
        face_index=face_idx,
        face_shape_id=shape_id,
        precalculated_polys=[Polygon([(0.0, 0.0), (1.2, 0.0), (1.2, 1.2), (0.0, 1.2)])],
        name=f"Perf Push/Pull {step_id}",
    )
    body.add_feature(feature, rebuild=True)
    assert _is_non_error(feature.status), f"Push/Pull failed: {feature.status}"
    assert body._build123d_solid is not None
    return feature


def _build_feature_rich_body(name: str, step_count: int) -> tuple[Document, Body, list[ExtrudeFeature]]:
    axis_directions = (
        (1.0, 0.0, 0.0),
        (-1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, -1.0, 0.0),
        (0.0, 0.0, 1.0),
        (0.0, 0.0, -1.0),
    )

    doc, body = _make_doc_body(name)
    _add_box_base(body, length=24.0, width=22.0, height=18.0, name=f"{name}_base")

    features = []
    for step in range(step_count):
        direction = axis_directions[step % len(axis_directions)]
        distance = 0.8 + 0.1 * (step % 5)
        features.append(
            _add_pushpull_join(
                doc,
                body,
                step_id=f"{name}_step_{step}",
                direction=direction,
                distance=distance,
            )
        )
    return doc, body, features


def _top_edge_indices(solid, limit: int = 4) -> list[int]:
    top_face = max(list(solid.faces()), key=lambda face: float(face.center().Z))
    indices = []
    for edge in top_face.edges():
        edge_idx = edge_index_of(solid, edge)
        if edge_idx is None:
            continue
        idx = int(edge_idx)
        if idx not in indices:
            indices.append(idx)
        if len(indices) >= limit:
            break
    return indices


def _vertical_ray_for_mesh(mesh):
    xmin, xmax, ymin, ymax, zmin, zmax = mesh.bounds
    cx = 0.5 * (xmin + xmax)
    cy = 0.5 * (ymin + ymax)
    start = (cx, cy, zmax + 25.0)
    end = (cx, cy, zmin - 25.0)
    return start, end


class TestManyBodiesPerformance:
    def test_render_10_bodies(self):
        _warm_up_tessellation()
        bodies = [_make_imported_box_body(f"body_{i}", 10.0, offset_x=i * 15.0) for i in range(10)]

        with BenchmarkTimer("render_10_bodies") as timer:
            for body in bodies:
                assert body.vtk_mesh is not None or body.vtk_edges is not None

        print(f"  10 Bodies: {timer.duration_ms:.2f}ms")
        assert timer.duration_ms < 750, f"10 Bodies render took {timer.duration_ms:.2f}ms"

    def test_render_50_bodies(self):
        _warm_up_tessellation()
        bodies = [_make_imported_box_body(f"body_{i}", 5.0, offset_x=i * 7.0) for i in range(50)]

        with BenchmarkTimer("render_50_bodies") as timer:
            for body in bodies:
                assert body.vtk_mesh is not None or body.vtk_edges is not None

        print(f"  50 Bodies: {timer.duration_ms:.2f}ms")
        assert timer.duration_ms < 2500, f"50 Bodies render took {timer.duration_ms:.2f}ms"

    def test_tessellation_cache_with_many_bodies(self):
        from modeling.cad_tessellator import CADTessellator

        CADTessellator.clear_cache()
        initial_cache_size = len(CADTessellator._mesh_cache)
        print(f"  Initial cache size: {initial_cache_size}")

        bodies = [_make_imported_box_body(f"body_{i}", 10.0, offset_x=i * 15.0) for i in range(10)]

        with BenchmarkTimer("tessellate_10_bodies_uncached") as uncached:
            for body in bodies:
                assert body.vtk_mesh is not None

        cache_after = len(CADTessellator._mesh_cache)
        print(f"  Cache after 10 bodies: {cache_after}")

        start = time.perf_counter()
        for body in bodies:
            assert body.vtk_mesh is not None
        cached_time = (time.perf_counter() - start) * 1000.0

        print(f"  Uncached tessellation: {uncached.duration_ms:.2f}ms")
        print(f"  Cached tessellation: {cached_time:.2f}ms")

        assert cached_time < uncached.duration_ms, "Cached tessellation should be faster than uncached"


class TestManyFeaturesPerformance:
    def test_rebuild_with_10_features(self):
        _, body, _ = _build_feature_rich_body("rebuild10", step_count=10)

        with BenchmarkTimer("rebuild_10_features") as timer:
            body._rebuild()

        print(f"  Rebuild 10 features: {timer.duration_ms:.2f}ms")
        assert body._build123d_solid is not None
        assert timer.duration_ms < 5000, f"Rebuild 10 features took {timer.duration_ms:.2f}ms"

    def test_rebuild_incremental_vs_full(self):
        _, body, features = _build_feature_rich_body("incremental", step_count=12)
        changed_feature = features[-1]

        start = time.perf_counter()
        body._rebuild()
        full_rebuild_time = (time.perf_counter() - start) * 1000.0

        changed_feature.distance += 0.25
        start = time.perf_counter()
        body.update_feature(changed_feature)
        incremental_time = (time.perf_counter() - start) * 1000.0

        print(f"  Full rebuild: {full_rebuild_time:.2f}ms")
        print(f"  Incremental rebuild: {incremental_time:.2f}ms")

        assert body._build123d_solid is not None
        assert incremental_time < full_rebuild_time, "Incremental rebuild should be faster than full rebuild"


class TestBrowserPerformance:
    def test_large_browser_render_time(self):
        doc = Document("browser_perf_doc")
        bodies = []
        for i in range(30):
            body = _make_imported_box_body(f"body_{i}", 5.0, offset_x=i * 8.0)
            doc.add_body(body)
            bodies.append(body)

        with BenchmarkTimer("browser_update_30") as timer:
            infos = []
            for body in bodies:
                solid = body._build123d_solid
                infos.append(
                    {
                        "name": body.name,
                        "id": body.id,
                        "feature_count": len(body.features),
                        "volume": float(solid.volume) if solid is not None else 0.0,
                    }
                )

        print(f"  Browser update (30): {timer.duration_ms:.2f}ms")
        assert len(infos) == 30
        assert timer.duration_ms < 100, f"Browser update took {timer.duration_ms:.2f}ms"


class TestSelectionPerformance:
    def test_selection_raycast_performance(self):
        from modeling.cad_tessellator import CADTessellator

        bodies = [_make_imported_box_body(f"body_{i}", 10.0, offset_x=i * 12.0) for i in range(20)]

        CADTessellator.clear_cache()
        meshes = []
        for body in bodies:
            mesh = body.vtk_mesh
            assert mesh is not None
            meshes.append(mesh)

        hits = 0
        with BenchmarkTimer("100_raycasts") as timer:
            for i in range(100):
                mesh = meshes[i % len(meshes)]
                start, end = _vertical_ray_for_mesh(mesh)
                points, _ = mesh.ray_trace(start, end)
                hits += len(points)

        print(f"  100 raycasts: {timer.duration_ms:.2f}ms")
        print(f"  Total hits: {hits}")

        assert hits > 0, "Ray tracing should hit tessellated body meshes"
        assert timer.duration_ms < 1000, f"100 raycasts took {timer.duration_ms:.2f}ms"


class TestMemoryUnderLoad:
    def test_no_memory_leak_on_rebuilds(self):
        _, body, _ = _build_feature_rich_body("memory", step_count=6)

        gc.collect()
        objects_before = len(gc.get_objects())

        for _ in range(10):
            body._rebuild()

        gc.collect()
        objects_after = len(gc.get_objects())
        growth = objects_after - objects_before

        print(f"  Object growth after 10 rebuilds: {growth}")

        assert body._build123d_solid is not None
        assert growth < 5000, f"Excessive object growth: {growth}"


class TestComplexGeometryPerformance:
    def test_complex_fillet_performance(self):
        _, body = _make_doc_body("fillet_perf")
        _add_box_base(body, length=50.0, width=50.0, height=50.0, name="fillet_base")

        edge_indices = _top_edge_indices(body._build123d_solid, limit=4)
        assert edge_indices, "Expected filletable top edges"

        feature = FilletFeature(radius=1.0, edge_indices=edge_indices, name="Perf Fillet")

        pre_volume = float(body._build123d_solid.volume)
        with BenchmarkTimer("fillet_4_edges") as timer:
            body.add_feature(feature, rebuild=True)

        post_volume = float(body._build123d_solid.volume)

        print(f"  Fillet 4 edges: {timer.duration_ms:.2f}ms")

        assert _is_non_error(feature.status), f"Fillet failed: {feature.status}"
        assert body._build123d_solid is not None
        assert post_volume < pre_volume, "Fillet should remove material from the base solid"
        assert timer.duration_ms < 2000, f"Fillet took {timer.duration_ms:.2f}ms"


class TestPerformanceRegressionPrevention:
    def test_tessellation_performance_baseline(self):
        from modeling.cad_tessellator import CADTessellator

        CADTessellator.clear_cache()

        times = []
        for i in range(10):
            body = _make_imported_box_body(f"perf_{i}", 10.0 + i, offset_x=i * 15.0)
            start = time.perf_counter()
            assert body.vtk_mesh is not None
            times.append((time.perf_counter() - start) * 1000.0)

        avg_time = sum(times) / len(times)
        max_time = max(times)

        print(f"  Tessellation avg: {avg_time:.2f}ms")
        print(f"  Tessellation max: {max_time:.2f}ms")

        assert avg_time < 150, f"Average tessellation {avg_time:.2f}ms too slow"
        assert max_time < 500, f"Max tessellation {max_time:.2f}ms too slow"
