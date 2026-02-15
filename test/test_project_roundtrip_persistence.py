import json

from build123d import Solid
from shapely.geometry import Polygon

from modeling import (
    Body,
    ChamferFeature,
    Document,
    FilletFeature,
    ExtrudeFeature,
    DraftFeature,
    HollowFeature,
    HoleFeature,
    ShellFeature,
    Sketch,
    SurfaceTextureFeature,
    SweepFeature,
    ThreadFeature,
)
from modeling.geometric_selector import GeometricFaceSelector
from modeling.topology_indexing import edge_index_of, face_index_of
from modeling.tnp_system import ShapeID, ShapeType


def _shape_id(shape_type: ShapeType, feature_id: str, local_index: int) -> ShapeID:
    return ShapeID(
        uuid=f"{feature_id}_{shape_type.name.lower()}_{local_index}",
        shape_type=shape_type,
        feature_id=feature_id,
        local_index=local_index,
        geometry_hash=f"hash_{feature_id}_{local_index}",
        timestamp=123.456,
    )


def _face_selector(seed: float = 0.0) -> dict:
    return {
        "center": [10.0 + seed, 20.0 + seed, 30.0 + seed],
        "normal": [0.0, 0.0, 1.0],
        "area": 100.0 + seed,
        "surface_type": "plane",
        "tolerance": 1.0,
    }


def _make_document_with_tnp_refs() -> Document:
    doc = Document("persist_roundtrip")
    body = Body("BodyPersist", document=doc)
    body.id = "body_persist_01"
    body._build123d_solid = Solid.make_box(20.0, 15.0, 10.0)
    body.source_body_id = "body_origin_01"
    body.split_index = 3
    body.split_side = "above"

    sweep = SweepFeature(
        profile_data={"type": "body_face"},
        path_data={"type": "body_edge", "body_id": body.id, "edge_indices": [1, 2]},
    )
    sweep.id = "feat_sweep_01"
    sweep.profile_shape_id = _shape_id(ShapeType.FACE, sweep.id, 0)
    sweep.path_shape_id = _shape_id(ShapeType.EDGE, sweep.id, 1)
    sweep.profile_face_index = 6

    hole = HoleFeature(face_selectors=[_face_selector(1.0)], face_indices=[2])
    hole.id = "feat_hole_01"
    hole.face_shape_ids = [_shape_id(ShapeType.FACE, hole.id, 0)]

    draft = DraftFeature(face_selectors=[_face_selector(2.0)], face_indices=[3])
    draft.id = "feat_draft_01"
    draft.face_shape_ids = [_shape_id(ShapeType.FACE, draft.id, 0)]

    hollow = HollowFeature(
        opening_face_selectors=[_face_selector(3.0)],
        opening_face_indices=[4],
    )
    hollow.id = "feat_hollow_01"
    hollow.opening_face_shape_ids = [_shape_id(ShapeType.FACE, hollow.id, 0)]

    texture = SurfaceTextureFeature(
        texture_type="ripple",
        face_selectors=[_face_selector(4.0)],
        face_indices=[5],
    )
    texture.id = "feat_texture_01"
    texture.face_shape_ids = [_shape_id(ShapeType.FACE, texture.id, 0)]

    thread = ThreadFeature(face_selector=_face_selector(5.0), face_index=6)
    thread.id = "feat_thread_01"
    thread.face_shape_id = _shape_id(ShapeType.FACE, thread.id, 0)

    body.features = [sweep, hole, draft, hollow, texture, thread]
    doc.add_body(body, set_active=True)

    sketch = Sketch("SketchPersist")
    sketch.id = "sketch_persist_01"
    doc.sketches.append(sketch)
    doc.active_sketch = sketch
    return doc


def _make_square_profile(size: float = 20.0):
    half = size / 2.0
    return Polygon(
        [
            (-half, -half),
            (half, -half),
            (half, half),
            (-half, half),
        ]
    )


def _add_extrude_from_sketch(body: Body, sketch: Sketch, distance: float, operation: str) -> ExtrudeFeature:
    assert sketch.closed_profiles, "Sketch benötigt mindestens ein Profil"
    profile = sketch.closed_profiles[0]
    centroid = profile.centroid
    feature = ExtrudeFeature(
        sketch=sketch,
        distance=distance,
        operation=operation,
        profile_selector=[(centroid.x, centroid.y)],
        plane_origin=getattr(sketch, "plane_origin", (0.0, 0.0, 0.0)),
        plane_normal=getattr(sketch, "plane_normal", (0.0, 0.0, 1.0)),
        plane_x_dir=getattr(sketch, "plane_x_dir", (1.0, 0.0, 0.0)),
        plane_y_dir=getattr(sketch, "plane_y_dir", (0.0, 1.0, 0.0)),
    )
    body.add_feature(feature, rebuild=True)
    return feature


def _is_success_status(status: str) -> bool:
    return str(status or "").upper() in {"OK", "SUCCESS"}


def _top_face_and_index(solid):
    faces = list(solid.faces())
    assert faces, "Solid hat keine Faces"
    top_face = max(faces, key=lambda f: float(f.center().Z))
    top_index = face_index_of(solid, top_face)
    assert top_index is not None
    return top_face, int(top_index)


def _top_edge_indices(solid, limit: int = 4):
    top_face = max(list(solid.faces()), key=lambda f: float(f.center().Z))
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
    assert indices, "Keine Top-Edge-Indizes gefunden"
    return indices


def test_document_to_dict_from_dict_roundtrip_preserves_identity_and_split_metadata():
    doc = _make_document_with_tnp_refs()
    payload = doc.to_dict()
    restored = Document.from_dict(payload)
    restored_payload = restored.to_dict()

    assert restored_payload["version"] == "9.1"
    assert restored_payload["active_body_id"] == payload["active_body_id"]
    assert restored_payload["active_sketch_id"] == payload["active_sketch_id"]

    body_in = payload["root_component"]["bodies"][0]
    body_out = restored_payload["root_component"]["bodies"][0]

    assert body_out["id"] == body_in["id"]
    assert body_out["source_body_id"] == "body_origin_01"
    assert body_out["split_index"] == 3
    assert body_out["split_side"] == "above"

    in_feature_classes = [feat["feature_class"] for feat in body_in["features"]]
    out_feature_classes = [feat["feature_class"] for feat in body_out["features"]]
    assert out_feature_classes == in_feature_classes

    in_feature_ids = [feat["id"] for feat in body_in["features"]]
    out_feature_ids = [feat["id"] for feat in body_out["features"]]
    assert out_feature_ids == in_feature_ids


def test_project_save_load_roundtrip_preserves_tnp_v4_feature_refs(tmp_path):
    doc = _make_document_with_tnp_refs()
    save_path = tmp_path / "persist_roundtrip.mshcad"

    assert doc.save_project(str(save_path)) is True
    assert save_path.exists()

    with save_path.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)
    assert raw["version"] == "9.1"
    assert raw["root_component"]["bodies"][0]["id"] == "body_persist_01"

    loaded = Document.load_project(str(save_path))
    assert loaded is not None
    loaded_body = loaded.find_body_by_id("body_persist_01")
    assert loaded_body is not None

    assert loaded_body.source_body_id == "body_origin_01"
    assert loaded_body.split_index == 3
    assert loaded_body.split_side == "above"

    loaded_features = {type(feat).__name__: feat for feat in loaded_body.features}
    assert set(loaded_features.keys()) == {
        "SweepFeature",
        "HoleFeature",
        "DraftFeature",
        "HollowFeature",
        "SurfaceTextureFeature",
        "ThreadFeature",
    }

    sweep = loaded_features["SweepFeature"]
    assert isinstance(sweep.profile_shape_id, ShapeID)
    assert isinstance(sweep.path_shape_id, ShapeID)
    assert sweep.profile_face_index == 6

    hole = loaded_features["HoleFeature"]
    assert hole.face_indices == [2]
    assert hole.face_shape_ids and isinstance(hole.face_shape_ids[0], ShapeID)

    draft = loaded_features["DraftFeature"]
    assert draft.face_indices == [3]
    assert draft.face_shape_ids and isinstance(draft.face_shape_ids[0], ShapeID)

    hollow = loaded_features["HollowFeature"]
    assert hollow.opening_face_indices == [4]
    assert hollow.opening_face_shape_ids and isinstance(hollow.opening_face_shape_ids[0], ShapeID)

    texture = loaded_features["SurfaceTextureFeature"]
    assert texture.face_indices == [5]
    assert texture.face_shape_ids and isinstance(texture.face_shape_ids[0], ShapeID)

    thread = loaded_features["ThreadFeature"]
    assert thread.face_index == 6
    assert isinstance(thread.face_shape_id, ShapeID)

    backup_path = save_path.with_suffix(save_path.suffix + ".pre_nsided_migration.bak")
    assert not backup_path.exists()


def test_project_save_load_roundtrip_preserves_assembly_extrude_sketch_reference(tmp_path):
    doc = Document("assembly_extrude_roundtrip")
    root = doc.root_component
    assert root is not None

    sub = root.add_sub_component("PartA")
    assert doc.set_active_component(sub)

    sketch = doc.new_sketch("SketchA")
    sketch.id = "sketch_asm_01"
    sketch.plane_origin = (0.0, 0.0, 0.0)
    sketch.plane_normal = (0.0, 0.0, 1.0)
    sketch.plane_x_dir = (1.0, 0.0, 0.0)
    sketch.plane_y_dir = (0.0, 1.0, 0.0)
    sketch.closed_profiles = [_make_square_profile(20.0)]

    body = doc.new_body("BodyA")
    body.id = "body_asm_01"
    feature = _add_extrude_from_sketch(body, sketch, distance=10.0, operation="New Body")
    assert _is_success_status(feature.status)
    assert body._build123d_solid is not None

    doc.active_body = body
    doc.active_sketch = sketch

    save_path = tmp_path / "assembly_extrude_roundtrip.mshcad"
    assert doc.save_project(str(save_path)) is True

    loaded = Document.load_project(str(save_path))
    assert loaded is not None
    loaded_sub = loaded.root_component.find_component_by_id(sub.id)
    assert loaded_sub is not None
    assert loaded._active_component is not None
    assert loaded._active_component.id == sub.id

    loaded_body = loaded.find_body_by_id("body_asm_01")
    assert loaded_body is not None
    loaded_extrude = next(feat for feat in loaded_body.features if isinstance(feat, ExtrudeFeature))
    assert loaded_extrude.sketch is not None
    assert loaded_extrude.sketch.id == "sketch_asm_01"
    assert loaded.active_sketch is not None
    assert loaded.active_sketch.id == "sketch_asm_01"

    loaded_body._rebuild()
    assert _is_success_status(loaded_extrude.status)
    assert loaded_body._build123d_solid is not None


def test_after_load_assembly_body_can_add_second_extrude_without_missing_reference(tmp_path):
    doc = Document("assembly_extrude_second_pass")
    sub = doc.root_component.add_sub_component("PartB")
    assert doc.set_active_component(sub)

    sketch = doc.new_sketch("SketchB")
    sketch.id = "sketch_asm_02"
    sketch.plane_origin = (0.0, 0.0, 0.0)
    sketch.plane_normal = (0.0, 0.0, 1.0)
    sketch.plane_x_dir = (1.0, 0.0, 0.0)
    sketch.plane_y_dir = (0.0, 1.0, 0.0)
    sketch.closed_profiles = [_make_square_profile(16.0)]

    body = doc.new_body("BodyB")
    body.id = "body_asm_02"
    first = _add_extrude_from_sketch(body, sketch, distance=8.0, operation="New Body")
    assert _is_success_status(first.status)

    save_path = tmp_path / "assembly_extrude_second_pass.mshcad"
    assert doc.save_project(str(save_path))

    loaded = Document.load_project(str(save_path))
    assert loaded is not None

    loaded_body = loaded.find_body_by_id("body_asm_02")
    assert loaded_body is not None
    loaded_sketch = next((s for s in loaded.get_all_sketches() if s.id == "sketch_asm_02"), None)
    assert loaded_sketch is not None

    second = _add_extrude_from_sketch(loaded_body, loaded_sketch, distance=2.0, operation="Join")
    assert _is_success_status(second.status)
    assert loaded_body._build123d_solid is not None
    assert "referenz" not in (second.status_message or "").lower()


def test_after_load_assembly_extrude_with_existing_hole_has_no_missing_reference_error(tmp_path):
    doc = Document("assembly_stack_roundtrip")
    sub = doc.root_component.add_sub_component("PartC")
    assert doc.set_active_component(sub)

    sketch = doc.new_sketch("SketchC")
    sketch.id = "sketch_asm_03"
    sketch.plane_origin = (0.0, 0.0, 0.0)
    sketch.plane_normal = (0.0, 0.0, 1.0)
    sketch.plane_x_dir = (1.0, 0.0, 0.0)
    sketch.plane_y_dir = (0.0, 1.0, 0.0)
    sketch.closed_profiles = [_make_square_profile(24.0)]

    body = doc.new_body("BodyC")
    body.id = "body_asm_03"
    first_extrude = _add_extrude_from_sketch(body, sketch, distance=12.0, operation="New Body")
    assert _is_success_status(first_extrude.status)
    assert body._build123d_solid is not None

    top_face, top_face_index = _top_face_and_index(body._build123d_solid)
    top_center = top_face.center()
    top_normal = top_face.normal_at(top_center)
    top_selector = GeometricFaceSelector.from_face(top_face).to_dict()

    hole = HoleFeature(
        hole_type="simple",
        diameter=3.0,
        depth=0.0,
        face_indices=[top_face_index],
        face_selectors=[top_selector],
        position=(float(top_center.X), float(top_center.Y), float(top_center.Z)),
        direction=(-float(top_normal.X), -float(top_normal.Y), -float(top_normal.Z)),
    )
    body.add_feature(hole, rebuild=True)
    assert _is_success_status(hole.status)

    save_path = tmp_path / "assembly_stack_roundtrip.mshcad"
    assert doc.save_project(str(save_path))

    loaded = Document.load_project(str(save_path))
    assert loaded is not None
    loaded_body = loaded.find_body_by_id("body_asm_03")
    assert loaded_body is not None
    loaded_sketch = next((s for s in loaded.get_all_sketches() if s.id == "sketch_asm_03"), None)
    assert loaded_sketch is not None

    second_extrude = _add_extrude_from_sketch(
        loaded_body,
        loaded_sketch,
        distance=2.5,
        operation="Join",
    )
    assert _is_success_status(second_extrude.status)
    assert "referenz" not in (second_extrude.status_message or "").lower()

    loaded_hole = next(feat for feat in loaded_body.features if isinstance(feat, HoleFeature))
    assert _is_success_status(loaded_hole.status)
    assert "referenz" not in (loaded_hole.status_message or "").lower()


def test_after_load_assembly_surface_texture_keeps_references_when_adding_extrude(tmp_path):
    doc = Document("assembly_texture_roundtrip")
    sub = doc.root_component.add_sub_component("PartTexture")
    assert doc.set_active_component(sub)

    sketch = doc.new_sketch("SketchTexture")
    sketch.id = "sketch_asm_04"
    sketch.plane_origin = (0.0, 0.0, 0.0)
    sketch.plane_normal = (0.0, 0.0, 1.0)
    sketch.plane_x_dir = (1.0, 0.0, 0.0)
    sketch.plane_y_dir = (0.0, 1.0, 0.0)
    sketch.closed_profiles = [_make_square_profile(22.0)]

    body = doc.new_body("BodyTexture")
    body.id = "body_asm_04"
    first_extrude = _add_extrude_from_sketch(body, sketch, distance=10.0, operation="New Body")
    assert _is_success_status(first_extrude.status)
    assert body._build123d_solid is not None

    top_face, top_face_index = _top_face_and_index(body._build123d_solid)
    texture_selector = GeometricFaceSelector.from_face(top_face).to_dict()
    texture = SurfaceTextureFeature(
        texture_type="ripple",
        face_indices=[top_face_index],
        face_selectors=[texture_selector],
        depth=0.8,
        scale=1.2,
    )
    body.add_feature(texture, rebuild=True)
    assert _is_success_status(texture.status)

    save_path = tmp_path / "assembly_texture_roundtrip.mshcad"
    assert doc.save_project(str(save_path))

    loaded = Document.load_project(str(save_path))
    assert loaded is not None
    loaded_body = loaded.find_body_by_id("body_asm_04")
    assert loaded_body is not None
    loaded_sketch = next((s for s in loaded.get_all_sketches() if s.id == "sketch_asm_04"), None)
    assert loaded_sketch is not None

    second_extrude = _add_extrude_from_sketch(
        loaded_body,
        loaded_sketch,
        distance=1.5,
        operation="Join",
    )
    assert _is_success_status(second_extrude.status)
    assert "referenz" not in (second_extrude.status_message or "").lower()

    loaded_texture = next(feat for feat in loaded_body.features if isinstance(feat, SurfaceTextureFeature))
    assert _is_success_status(loaded_texture.status)
    assert "referenz" not in (loaded_texture.status_message or "").lower()

    report = loaded._shape_naming_service.get_health_report(loaded_body)
    texture_report = next(feat for feat in report["features"] if feat["type"] == "SurfaceTexture")
    assert texture_report["status"] != "broken"
    assert texture_report["broken"] == 0


def test_load_project_migrates_texture_shapeid_selector_refs_to_indices_and_rehydrates_service(tmp_path):
    doc = Document("assembly_texture_shapeid_only_roundtrip")
    sub = doc.root_component.add_sub_component("PartTextureMigrate")
    assert doc.set_active_component(sub)

    sketch = doc.new_sketch("SketchTextureMigrate")
    sketch.id = "sketch_asm_05"
    sketch.plane_origin = (0.0, 0.0, 0.0)
    sketch.plane_normal = (0.0, 0.0, 1.0)
    sketch.plane_x_dir = (1.0, 0.0, 0.0)
    sketch.plane_y_dir = (0.0, 1.0, 0.0)
    sketch.closed_profiles = [_make_square_profile(18.0)]

    body = doc.new_body("BodyTextureMigrate")
    body.id = "body_asm_05"
    first_extrude = _add_extrude_from_sketch(body, sketch, distance=9.0, operation="New Body")
    assert _is_success_status(first_extrude.status)
    assert body._build123d_solid is not None

    top_face, top_face_index = _top_face_and_index(body._build123d_solid)
    texture = SurfaceTextureFeature(
        texture_type="ripple",
        face_indices=[top_face_index],
        face_selectors=[GeometricFaceSelector.from_face(top_face).to_dict()],
        depth=0.6,
        scale=1.1,
    )
    texture.id = "feat_texture_shapeid_only_01"
    texture.face_shape_ids = [_shape_id(ShapeType.FACE, texture.id, 0)]
    body.add_feature(texture, rebuild=True)
    assert _is_success_status(texture.status)

    # Simuliere Legacy/Undo Snapshot: ShapeID + Selector vorhanden, Indizes fehlen.
    texture.face_indices = []

    save_path = tmp_path / "assembly_texture_shapeid_only_roundtrip.mshcad"
    assert doc.save_project(str(save_path))

    loaded = Document.load_project(str(save_path))
    assert loaded is not None
    loaded_body = loaded.find_body_by_id("body_asm_05")
    assert loaded_body is not None
    loaded_sketch = next((s for s in loaded.get_all_sketches() if s.id == "sketch_asm_05"), None)
    assert loaded_sketch is not None

    loaded_texture = next(feat for feat in loaded_body.features if isinstance(feat, SurfaceTextureFeature))
    assert loaded_texture.face_indices
    assert len(loaded_texture.face_shape_ids) == 1

    resolved = loaded._shape_naming_service.resolve_shape(
        loaded_texture.face_shape_ids[0],
        loaded_body._build123d_solid,
    )
    assert resolved is not None

    second_extrude = _add_extrude_from_sketch(
        loaded_body,
        loaded_sketch,
        distance=1.0,
        operation="Join",
    )
    assert _is_success_status(second_extrude.status)
    assert "referenz" not in (second_extrude.status_message or "").lower()


def test_after_load_fillet_edit_rebuild_keeps_reference_integrity(tmp_path):
    doc = Document("roundtrip_fillet_edit")
    sketch = doc.new_sketch("SketchFillet")
    sketch.id = "sketch_fillet_01"
    sketch.plane_origin = (0.0, 0.0, 0.0)
    sketch.plane_normal = (0.0, 0.0, 1.0)
    sketch.plane_x_dir = (1.0, 0.0, 0.0)
    sketch.plane_y_dir = (0.0, 1.0, 0.0)
    sketch.closed_profiles = [_make_square_profile(24.0)]

    body = doc.new_body("BodyFillet")
    body.id = "body_fillet_01"
    base = _add_extrude_from_sketch(body, sketch, distance=12.0, operation="New Body")
    assert _is_success_status(base.status)

    fillet = FilletFeature(radius=0.8, edge_indices=_top_edge_indices(body._build123d_solid, limit=4))
    body.add_feature(fillet, rebuild=True)
    assert _is_success_status(fillet.status)

    save_path = tmp_path / "roundtrip_fillet_edit.mshcad"
    assert doc.save_project(str(save_path))

    loaded = Document.load_project(str(save_path))
    assert loaded is not None
    loaded_body = loaded.find_body_by_id("body_fillet_01")
    assert loaded_body is not None

    loaded_fillet = next(feat for feat in loaded_body.features if isinstance(feat, FilletFeature))
    loaded_fillet.radius = 1.1
    loaded_body._rebuild()

    assert _is_success_status(loaded_fillet.status)
    assert "referenz" not in (loaded_fillet.status_message or "").lower()
    code = (loaded_fillet.status_details or {}).get("code")
    assert code not in {"tnp_ref_missing", "tnp_ref_mismatch", "tnp_ref_drift"}


def test_after_load_chamfer_edit_rebuild_keeps_reference_integrity(tmp_path):
    doc = Document("roundtrip_chamfer_edit")
    sketch = doc.new_sketch("SketchChamfer")
    sketch.id = "sketch_chamfer_01"
    sketch.plane_origin = (0.0, 0.0, 0.0)
    sketch.plane_normal = (0.0, 0.0, 1.0)
    sketch.plane_x_dir = (1.0, 0.0, 0.0)
    sketch.plane_y_dir = (0.0, 1.0, 0.0)
    sketch.closed_profiles = [_make_square_profile(20.0)]

    body = doc.new_body("BodyChamfer")
    body.id = "body_chamfer_01"
    base = _add_extrude_from_sketch(body, sketch, distance=10.0, operation="New Body")
    assert _is_success_status(base.status)

    chamfer = ChamferFeature(distance=0.6, edge_indices=_top_edge_indices(body._build123d_solid, limit=4))
    body.add_feature(chamfer, rebuild=True)
    assert _is_success_status(chamfer.status)

    save_path = tmp_path / "roundtrip_chamfer_edit.mshcad"
    assert doc.save_project(str(save_path))

    loaded = Document.load_project(str(save_path))
    assert loaded is not None
    loaded_body = loaded.find_body_by_id("body_chamfer_01")
    assert loaded_body is not None

    loaded_chamfer = next(feat for feat in loaded_body.features if isinstance(feat, ChamferFeature))
    loaded_chamfer.distance = 0.4
    loaded_body._rebuild()

    assert _is_success_status(loaded_chamfer.status)
    assert "referenz" not in (loaded_chamfer.status_message or "").lower()
    code = (loaded_chamfer.status_details or {}).get("code")
    assert code not in {"tnp_ref_missing", "tnp_ref_mismatch", "tnp_ref_drift"}


def test_after_load_shell_edit_rebuild_keeps_reference_integrity(tmp_path):
    doc = Document("roundtrip_shell_edit")
    sketch = doc.new_sketch("SketchShell")
    sketch.id = "sketch_shell_01"
    sketch.plane_origin = (0.0, 0.0, 0.0)
    sketch.plane_normal = (0.0, 0.0, 1.0)
    sketch.plane_x_dir = (1.0, 0.0, 0.0)
    sketch.plane_y_dir = (0.0, 1.0, 0.0)
    sketch.closed_profiles = [_make_square_profile(30.0)]

    body = doc.new_body("BodyShell")
    body.id = "body_shell_01"
    base = _add_extrude_from_sketch(body, sketch, distance=20.0, operation="New Body")
    assert _is_success_status(base.status)

    _, top_index = _top_face_and_index(body._build123d_solid)
    shell = ShellFeature(thickness=2.0, face_indices=[top_index])
    body.add_feature(shell, rebuild=True)
    assert _is_success_status(shell.status)

    save_path = tmp_path / "roundtrip_shell_edit.mshcad"
    assert doc.save_project(str(save_path))

    loaded = Document.load_project(str(save_path))
    assert loaded is not None
    loaded_body = loaded.find_body_by_id("body_shell_01")
    assert loaded_body is not None

    loaded_shell = next(feat for feat in loaded_body.features if isinstance(feat, ShellFeature))
    loaded_shell.thickness = 1.0
    loaded_body._rebuild()

    assert _is_success_status(loaded_shell.status)
    assert "referenz" not in (loaded_shell.status_message or "").lower()
    code = (loaded_shell.status_details or {}).get("code")
    assert code not in {"tnp_ref_missing", "tnp_ref_mismatch", "tnp_ref_drift"}
