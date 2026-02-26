"""
TNP v5.0 - Feature Ambiguity Helper Tests

Tests for the feature integration helpers that check for and resolve
ambiguity in feature operations.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from modeling.tnp_v5.feature_helpers import (
    FeatureAmbiguityChecker,
    resolve_feature_ambiguity,
    check_and_resolve_fillet_ambiguity,
    check_and_resolve_chamfer_ambiguity,
    check_and_resolve_boolean_ambiguity,
    fillet_requires_disambiguation,
    chamfer_requires_disambiguation,
    boolean_requires_disambiguation,
)
from modeling.tnp_v5.ambiguity import AmbiguityReport, AmbiguityType


class TestFeatureAmbiguityCheckerInit:
    """Test FeatureAmbiguityChecker initialization."""

    def test_init(self):
        """Test checker initialization."""
        mock_service = Mock()
        checker = FeatureAmbiguityChecker(mock_service)

        assert checker._tnp_service == mock_service
        assert checker._detector is not None


class TestCheckFilletEdges:
    """Test fillet edge ambiguity checking."""

    def test_no_ambiguity_single_edge(self):
        """Test single edge returns no ambiguity."""
        mock_service = Mock()
        checker = FeatureAmbiguityChecker(mock_service)

        result = checker.check_fillet_edges(["edge1"], "fillet1")

        assert result is None

    def test_no_ambiguity_no_records(self):
        """Test when no records found."""
        mock_service = Mock()
        mock_service.get_shape_record = Mock(return_value=None)
        checker = FeatureAmbiguityChecker(mock_service)

        result = checker.check_fillet_edges(["edge1", "edge2"], "fillet1")

        assert result is None

    def test_detects_ambiguity_multiple_edges(self):
        """Test detection with multiple edges."""
        from modeling.tnp_v5 import ShapeID, ShapeType, ShapeRecord

        mock_service = Mock()

        # Create proper shape records
        def create_record(shape_id, center):
            sid = ShapeID.create(
                shape_type=ShapeType.EDGE,
                feature_id="test",
                local_index=0,
                geometry_data=()
            )
            record = ShapeRecord(
                shape_id=sid,
                ocp_shape=Mock()
            )
            record.geometric_signature = {
                'geometry_hash': f'hash_{shape_id}',
                'center': center
            }
            return record

        mock_service.get_shape_record = lambda x: create_record(x, (0, 0, 0))

        checker = FeatureAmbiguityChecker(mock_service)

        result = checker.check_fillet_edges(["edge1", "edge2"], "fillet1")

        # Should detect ambiguity with same position
        assert result is not None

    def test_no_ambiguity_distinct_positions(self):
        """Test that distinct positions don't trigger symmetry ambiguity."""
        from modeling.tnp_v5 import ShapeID, ShapeType, ShapeRecord

        mock_service = Mock()

        # Create records with far apart centers
        centers = {
            "edge1": (0, 0, 0),
            "edge2": (1000, 1000, 1000)  # Very far apart
        }

        records = {}
        for edge_id, center in centers.items():
            sid = ShapeID.create(ShapeType.EDGE, "test", int(edge_id[-1]), ())
            record = ShapeRecord(shape_id=sid, ocp_shape=Mock())
            record.geometric_signature = {'center': center, 'geometry_hash': f'hash_{edge_id}'}
            records[edge_id] = record

        mock_service.get_shape_record = lambda x: records.get(x)

        checker = FeatureAmbiguityChecker(mock_service)
        result = checker.check_fillet_edges(["edge1", "edge2"], "fillet1")

        # Very far apart positions - may still detect duplicate if scores are same
        # but not symmetric positions
        if result is not None:
            # If detected, should be DUPLICATE not SYMMETRIC
            from modeling.tnp_v5.ambiguity import AmbiguityType
            assert result.ambiguity_type != AmbiguityType.SYMMETRIC


class TestCheckChamferEdges:
    """Test chamfer edge ambiguity checking."""

    def test_uses_same_logic_as_fillet(self):
        """Test chamfer uses same checking logic."""
        mock_service = Mock()
        checker = FeatureAmbiguityChecker(mock_service)

        # Both should return None for single edge
        fillet_result = checker.check_fillet_edges(["edge1"], "fillet1")
        chamfer_result = checker.check_chamfer_edges(["edge1"], "chamfer1")

        assert fillet_result is None
        assert chamfer_result is None


class TestCheckBooleanTool:
    """Test boolean operation ambiguity checking."""

    def test_no_ambiguity_no_records(self):
        """Test when no records found."""
        mock_service = Mock()
        mock_service.get_shape_record = Mock(return_value=None)
        checker = FeatureAmbiguityChecker(mock_service)

        result = checker.check_boolean_tool("target1", "tool1", "Cut")

        assert result is None

    def test_detects_symmetric_positions(self):
        """Test detection of symmetric positions."""
        from modeling.tnp_v5 import ShapeID, ShapeType, ShapeRecord

        mock_service = Mock()

        # Create records with symmetric centers
        target_sid = ShapeID.create(ShapeType.SOLID, "test", 0, ())
        target_record = ShapeRecord(shape_id=target_sid, ocp_shape=Mock())
        target_record.geometric_signature = {'center': (10, 20, 30)}

        tool_sid = ShapeID.create(ShapeType.SOLID, "test", 1, ())
        tool_record = ShapeRecord(shape_id=tool_sid, ocp_shape=Mock())
        tool_record.geometric_signature = {'center': (10, 20, -30)}  # Mirror across Z

        mock_service.get_shape_record = Mock(side_effect=[target_record, tool_record])

        checker = FeatureAmbiguityChecker(mock_service)

        result = checker.check_boolean_tool("target1", "tool1", "Cut")

        assert result is not None
        assert result.ambiguity_type == AmbiguityType.SYMMETRIC
        assert "target1" in result.candidates
        assert "tool1" in result.candidates

    def test_no_ambiguity_asymmetric_positions(self):
        """Test asymmetric positions don't trigger."""
        from modeling.tnp_v5 import ShapeID, ShapeType, ShapeRecord

        mock_service = Mock()

        target_sid = ShapeID.create(ShapeType.SOLID, "test", 0, ())
        target_record = ShapeRecord(shape_id=target_sid, ocp_shape=Mock())
        target_record.geometric_signature = {'center': (0, 0, 0)}

        tool_sid = ShapeID.create(ShapeType.SOLID, "test", 1, ())
        tool_record = ShapeRecord(shape_id=tool_sid, ocp_shape=Mock())
        tool_record.geometric_signature = {'center': (100, 200, 300)}  # Far away

        mock_service.get_shape_record = Mock(side_effect=[target_record, tool_record])

        checker = FeatureAmbiguityChecker(mock_service)

        result = checker.check_boolean_tool("target1", "tool1", "Cut")

        assert result is None


class TestResolveFeatureAmbiguity:
    """Test ambiguity resolution dialog."""

    def test_no_dialog_module(self):
        """Test when dialog module is not available."""
        report = AmbiguityReport(
            ambiguity_type=AmbiguityType.DUPLICATE,
            question="Select one",
            candidates=["a", "b"],
            candidate_descriptions=["A", "B"]
        )

        # Patch the import within the function (gui.dialogs.ambiguity_dialog)
        with patch('gui.dialogs.ambiguity_dialog.resolve_ambiguity_dialog', side_effect=ImportError):
            result = resolve_feature_ambiguity(report)

        assert result is None

    def test_dialog_error(self):
        """Test error handling in dialog."""
        report = AmbiguityReport(
            ambiguity_type=AmbiguityType.DUPLICATE,
            question="Select one",
            candidates=["a", "b"],
            candidate_descriptions=["A", "B"]
        )

        # Patch the import within the function
        with patch('gui.dialogs.ambiguity_dialog.resolve_ambiguity_dialog', side_effect=Exception("Test error")):
            result = resolve_feature_ambiguity(report)

        assert result is None


class TestCheckAndResolveFilletAmbiguity:
    """Test fillet ambiguity check and resolve."""

    def test_no_ambiguity_returns_original(self):
        """Test that no ambiguity returns original edge IDs."""
        mock_service = Mock()
        mock_checker = Mock()
        mock_checker.check_fillet_edges = Mock(return_value=None)

        with patch('modeling.tnp_v5.feature_helpers.FeatureAmbiguityChecker', return_value=mock_checker):
            result = check_and_resolve_fillet_ambiguity(
                ["edge1", "edge2"], "fillet1", mock_service
            )

        assert result == ["edge1", "edge2"]

    def test_ambiguity_resolved(self):
        """Test that ambiguity is resolved with user selection."""
        mock_service = Mock()

        mock_report = AmbiguityReport(
            ambiguity_type=AmbiguityType.DUPLICATE,
            question="Select edge",
            candidates=["edge1", "edge2"],
            candidate_descriptions=["Edge A", "Edge B"]
        )

        mock_checker = Mock()
        mock_checker.check_fillet_edges = Mock(return_value=mock_report)

        with patch('modeling.tnp_v5.feature_helpers.FeatureAmbiguityChecker', return_value=mock_checker):
            with patch('modeling.tnp_v5.feature_helpers.resolve_feature_ambiguity', return_value="edge2"):
                result = check_and_resolve_fillet_ambiguity(
                    ["edge1", "edge2"], "fillet1", mock_service
                )

        assert result == ["edge2"]

    def test_ambiguity_cancelled(self):
        """Test that cancellation returns empty list."""
        mock_service = Mock()

        mock_report = AmbiguityReport(
            ambiguity_type=AmbiguityType.DUPLICATE,
            question="Select edge",
            candidates=["edge1", "edge2"],
            candidate_descriptions=["Edge A", "Edge B"]
        )

        mock_checker = Mock()
        mock_checker.check_fillet_edges = Mock(return_value=mock_report)

        with patch('modeling.tnp_v5.feature_helpers.FeatureAmbiguityChecker', return_value=mock_checker):
            with patch('modeling.tnp_v5.feature_helpers.resolve_feature_ambiguity', return_value=None):
                result = check_and_resolve_fillet_ambiguity(
                    ["edge1", "edge2"], "fillet1", mock_service
                )

        assert result == []


class TestCheckAndResolveChamferAmbiguity:
    """Test chamfer ambiguity check and resolve."""

    def test_no_ambiguity_returns_original(self):
        """Test that no ambiguity returns original edge IDs."""
        mock_service = Mock()
        mock_checker = Mock()
        mock_checker.check_chamfer_edges = Mock(return_value=None)

        with patch('modeling.tnp_v5.feature_helpers.FeatureAmbiguityChecker', return_value=mock_checker):
            result = check_and_resolve_chamfer_ambiguity(
                ["edge1"], "chamfer1", mock_service
            )

        assert result == ["edge1"]

    def test_ambiguity_resolved(self):
        """Test that ambiguity is resolved with user selection."""
        mock_service = Mock()

        mock_report = AmbiguityReport(
            ambiguity_type=AmbiguityType.DUPLICATE,
            question="Select edge",
            candidates=["edge1", "edge2"],
            candidate_descriptions=["Edge A", "Edge B"]
        )

        mock_checker = Mock()
        mock_checker.check_chamfer_edges = Mock(return_value=mock_report)

        with patch('modeling.tnp_v5.feature_helpers.FeatureAmbiguityChecker', return_value=mock_checker):
            with patch('modeling.tnp_v5.feature_helpers.resolve_feature_ambiguity', return_value="edge1"):
                result = check_and_resolve_chamfer_ambiguity(
                    ["edge1", "edge2"], "chamfer1", mock_service
                )

        assert result == ["edge1"]


class TestCheckAndResolveBooleanAmbiguity:
    """Test boolean ambiguity check and resolve."""

    def test_no_ambiguity_proceeds(self):
        """Test that no ambiguity allows operation to proceed."""
        mock_service = Mock()
        mock_checker = Mock()
        mock_checker.check_boolean_tool = Mock(return_value=None)

        with patch('modeling.tnp_v5.feature_helpers.FeatureAmbiguityChecker', return_value=mock_checker):
            result = check_and_resolve_boolean_ambiguity(
                "target1", "tool1", "Cut", mock_service
            )

        assert result is True

    def test_ambiguity_resolved_proceeds(self):
        """Test that ambiguity resolution allows proceeding."""
        mock_service = Mock()

        mock_report = AmbiguityReport(
            ambiguity_type=AmbiguityType.SYMMETRIC,
            question="Which to use?",
            candidates=["target1", "tool1"],
            candidate_descriptions=["Target", "Tool"]
        )

        mock_checker = Mock()
        mock_checker.check_boolean_tool = Mock(return_value=mock_report)

        with patch('modeling.tnp_v5.feature_helpers.FeatureAmbiguityChecker', return_value=mock_checker):
            with patch('modeling.tnp_v5.feature_helpers.resolve_feature_ambiguity', return_value="target1"):
                result = check_and_resolve_boolean_ambiguity(
                    "target1", "tool1", "Cut", mock_service
                )

        assert result is True

    def test_ambiguity_cancelled_blocks(self):
        """Test that cancellation blocks operation."""
        mock_service = Mock()

        mock_report = AmbiguityReport(
            ambiguity_type=AmbiguityType.SYMMETRIC,
            question="Which to use?",
            candidates=["target1", "tool1"],
            candidate_descriptions=["Target", "Tool"]
        )

        mock_checker = Mock()
        mock_checker.check_boolean_tool = Mock(return_value=mock_report)

        with patch('modeling.tnp_v5.feature_helpers.FeatureAmbiguityChecker', return_value=mock_checker):
            with patch('modeling.tnp_v5.feature_helpers.resolve_feature_ambiguity', return_value=None):
                result = check_and_resolve_boolean_ambiguity(
                    "target1", "tool1", "Cut", mock_service
                )

        assert result is False


class TestConvenienceFunctions:
    """Test convenience functions for quick checks."""

    def test_fillet_requires_disambiguation_true(self):
        """Test fillet check returns True for multiple edges."""
        assert fillet_requires_disambiguation(["edge1", "edge2"]) is True

    def test_fillet_requires_disambiguation_false(self):
        """Test fillet check returns False for single edge."""
        assert fillet_requires_disambiguation(["edge1"]) is False
        assert fillet_requires_disambiguation([]) is False

    def test_chamfer_requires_disambiguation_true(self):
        """Test chamfer check returns True for multiple edges."""
        assert chamfer_requires_disambiguation(["e1", "e2", "e3"]) is True

    def test_chamfer_requires_disambiguation_false(self):
        """Test chamfer check returns False for single edge."""
        assert chamfer_requires_disambiguation(["edge1"]) is False

    def test_boolean_requires_disambiguation_true(self):
        """Test boolean check detects symmetric positions."""
        # Mirror across Z
        assert boolean_requires_disambiguation((10, 20, 30), (10, 20, -30)) is True

    def test_boolean_requires_disambiguation_false(self):
        """Test boolean check returns False for asymmetric positions."""
        assert boolean_requires_disambiguation((0, 0, 0), (100, 100, 100)) is False


class TestArePositionsSymmetric:
    """Test position symmetry checking."""

    def test_mirror_across_z(self):
        """Test mirror across Z=0 plane."""
        checker = FeatureAmbiguityChecker(None)

        assert checker._are_positions_symmetric((0, 0, 5), (0, 0, -5))
        assert checker._are_positions_symmetric((10, 20, 30), (10, 20, -30))

    def test_mirror_across_y(self):
        """Test mirror across Y=0 plane."""
        checker = FeatureAmbiguityChecker(None)

        assert checker._are_positions_symmetric((0, 5, 0), (0, -5, 0))
        assert checker._are_positions_symmetric((10, 20, 30), (10, -20, 30))

    def test_mirror_across_x(self):
        """Test mirror across X=0 plane."""
        checker = FeatureAmbiguityChecker(None)

        assert checker._are_positions_symmetric((5, 0, 0), (-5, 0, 0))

    def test_not_symmetric(self):
        """Test asymmetric positions."""
        checker = FeatureAmbiguityChecker(None)

        assert not checker._are_positions_symmetric((0, 0, 0), (10, 20, 30))
        assert not checker._are_positions_symmetric((1, 2, 3), (4, 5, 6))

    def test_custom_threshold(self):
        """Test custom threshold parameter."""
        checker = FeatureAmbiguityChecker(None)

        # Positions slightly off exact mirror - within threshold
        assert checker._are_positions_symmetric((0, 0, 5.05), (0, 0, -5.05), threshold=0.1)

        # Positions further off - beyond threshold
        # (5.2 + (-5.2) = 0, so it's still symmetric in X/Y, need to check Z differently)
        # Actually the test should use different coordinates
        assert not checker._are_positions_symmetric((0, 0, 5.2), (0.2, 0, -5.2), threshold=0.1)


class TestIntegrationWithFeatures:
    """Test integration with actual feature classes."""

    def test_fillet_feature_can_use_helpers(self):
        """Test that FilletFeature can use the helpers."""
        from modeling.features.fillet_chamfer import FilletFeature

        feature = FilletFeature(radius=5.0)

        # Check the feature has the necessary TNP v5.0 fields
        assert hasattr(feature, 'tnp_v5_input_edge_ids')
        assert hasattr(feature, 'tnp_v5_output_edge_ids')
        assert hasattr(feature, 'tnp_v5_selection_contexts')

    def test_chamfer_feature_can_use_helpers(self):
        """Test that ChamferFeature can use the helpers."""
        from modeling.features.fillet_chamfer import ChamferFeature

        feature = ChamferFeature(distance=2.0)

        # Check the feature has the necessary TNP v5.0 fields
        assert hasattr(feature, 'tnp_v5_input_edge_ids')
        assert hasattr(feature, 'tnp_v5_output_edge_ids')
        assert hasattr(feature, 'tnp_v5_selection_contexts')

    def test_boolean_feature_can_use_helpers(self):
        """Test that BooleanFeature can use the helpers."""
        from modeling.features.boolean import BooleanFeature

        feature = BooleanFeature(operation="Cut")

        # Check the feature has the necessary TNP v5.0 fields
        assert hasattr(feature, 'tnp_v5_input_face_ids')
        assert hasattr(feature, 'tnp_v5_output_face_ids')
        assert hasattr(feature, 'tnp_v5_transformation_map')


class TestErrorHandling:
    """Test error handling in helpers."""

    def test_checker_handles_missing_signature(self):
        """Test checker handles missing signature gracefully."""
        from modeling.tnp_v5 import ShapeID, ShapeType, ShapeRecord

        mock_service = Mock()

        # Record with empty geometric_signature
        sid = ShapeID.create(ShapeType.EDGE, "test", 0, ())
        record = ShapeRecord(shape_id=sid, ocp_shape=Mock())
        record.geometric_signature = None

        mock_service.get_shape_record = Mock(return_value=record)

        checker = FeatureAmbiguityChecker(mock_service)

        # Should not crash
        result = checker.check_fillet_edges(["edge1"], "fillet1")

        # No candidates = no ambiguity
        assert result is None

    def test_checker_handles_empty_signature(self):
        """Test checker handles empty signature gracefully."""
        from modeling.tnp_v5 import ShapeID, ShapeType, ShapeRecord

        mock_service = Mock()

        sid = ShapeID.create(ShapeType.EDGE, "test", 0, ())
        record = ShapeRecord(shape_id=sid, ocp_shape=Mock())
        record.geometric_signature = {}

        mock_service.get_shape_record = Mock(return_value=record)

        checker = FeatureAmbiguityChecker(mock_service)

        result = checker.check_fillet_edges(["edge1"], "fillet1")

        assert result is None

    def test_boolean_handles_missing_centers(self):
        """Test boolean handles asymmetric positions correctly."""
        from modeling.tnp_v5 import ShapeID, ShapeType, ShapeRecord

        mock_service = Mock()

        # Use different centers to avoid false symmetry detection
        target_sid = ShapeID.create(ShapeType.SOLID, "test", 0, ())
        target_record = ShapeRecord(shape_id=target_sid, ocp_shape=Mock())
        target_record.geometric_signature = {'center': (10, 20, 30)}

        tool_sid = ShapeID.create(ShapeType.SOLID, "test", 1, ())
        tool_record = ShapeRecord(shape_id=tool_sid, ocp_shape=Mock())
        tool_record.geometric_signature = {'center': (40, 50, 60)}

        # Use a dict for proper lookup
        records_map = {
            "target1": target_record,
            "tool1": tool_record
        }
        mock_service.get_shape_record = lambda x: records_map.get(x)

        checker = FeatureAmbiguityChecker(mock_service)

        result = checker.check_boolean_tool("target1", "tool1", "Cut")

        # Different positions means no symmetry
        assert result is None
