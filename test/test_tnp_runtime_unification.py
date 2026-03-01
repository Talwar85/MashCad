from modeling.document import Document
from modeling.tnp_system import ShapeNamingService, ShapeType
from modeling.tnp_v5 import SelectionContext
from modeling.tnp_v5.feature_integration import get_tnp_v5_service


def test_document_uses_single_tnp5_service_instance():
    doc = Document("tnp5_runtime_doc")

    assert isinstance(doc._shape_naming_service, ShapeNamingService)
    assert doc._tnp_v5_service is doc._shape_naming_service
    assert doc._shape_naming_service.document_id == "tnp5_runtime_doc"
    assert get_tnp_v5_service(doc) is doc._shape_naming_service


def test_primary_shape_naming_service_accepts_v5_selection_context():
    service = ShapeNamingService("tnp5_context_doc")
    context = SelectionContext(
        shape_id="",
        selection_point=(1.0, 2.0, 3.0),
        view_direction=(0.0, 0.0, 1.0),
        adjacent_shapes=[],
        feature_context="feat_ctx",
    )

    shape_id = service.register_shape(
        ocp_shape=object(),
        shape_type=ShapeType.FACE,
        feature_id="feat_ctx",
        local_index=0,
        geometry_data=(1.0, 2.0, 3.0, 4.0),
        context=context,
    )

    record = service.get_shape_record(shape_id.uuid)

    assert hasattr(shape_id, "timestamp")
    assert record is not None
    assert record.selection_context == context
    assert record.shape_id.uuid == shape_id.uuid
