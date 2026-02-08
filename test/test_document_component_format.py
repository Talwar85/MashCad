from modeling import Body, Document, Sketch


def test_document_to_dict_always_emits_component_format():
    doc = Document("component_out")

    # Simuliere einen Flat-Laufzeitzustand ohne aktive Assembly.
    doc._assembly_enabled = False
    doc.root_component = None
    doc._active_component = None

    body = Body("BodyFlat")
    doc.add_body(body)
    doc._sketches.append(Sketch("SketchFlat"))

    data = doc.to_dict()

    assert data["version"] == "9.1"
    assert data["assembly_enabled"] is True
    assert "root_component" in data
    assert "bodies" not in data
    assert len(data["root_component"]["bodies"]) == 1
    assert data["root_component"]["bodies"][0]["name"] == "BodyFlat"
    assert len(data["root_component"]["sketches"]) == 1


def test_document_from_dict_migrates_flat_payload_to_component_format():
    legacy_like = {
        "version": "8.3",
        "name": "flat_in",
        "bodies": [Body("LegacyBody").to_dict()],
        "sketches": [Sketch("LegacySketch").to_dict()],
        "planes": [],
        "active_body_id": None,
        "active_sketch_id": None,
    }

    doc = Document.from_dict(legacy_like)

    assert doc._assembly_enabled is True
    assert doc.root_component is not None
    assert len(doc.get_all_bodies()) == 1
    assert doc.get_all_bodies()[0].name == "LegacyBody"
    assert len(doc.get_all_sketches()) == 1
    assert doc.get_all_sketches()[0].name == "LegacySketch"
