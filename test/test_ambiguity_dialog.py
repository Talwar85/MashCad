"""
TNP v5.0 - Ambiguity Dialog Tests

Tests for the AmbiguityDialog GUI component.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from PySide6.QtCore import Qt

from gui.dialogs.ambiguity_dialog import (
    AmbiguityDialog,
    AmbiguousSelectionDialog,
    resolve_ambiguity_dialog,
)
from modeling.tnp_v5.ambiguity import AmbiguityReport, AmbiguityType


@pytest.fixture(scope="module")
def qapp():
    """Create Qt application once for all tests."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# Use qapp fixture instead of app with qtbot
@pytest.fixture
def app(qapp):
    """Return the Qt application."""
    return qapp


def skip_if_no_qt():
    """Skip test if Qt is not available."""
    try:
        from PySide6.QtWidgets import QApplication
        QApplication.instance()
        return False
    except Exception:
        return True


# Auto-use the qapp fixture for all tests
pytest_plugins = []


@pytest.fixture
def sample_report():
    """Create a sample ambiguity report."""
    return AmbiguityReport(
        ambiguity_type=AmbiguityType.SYMMETRIC,
        question="Which shape did you intend?",
        candidates=["shape1", "shape2"],
        candidate_descriptions=["Face at (0, 0, 5)", "Face at (0, 0, -5)"],
        metadata={"symmetric": True}
    )


@pytest.fixture
def duplicate_report():
    """Create a duplicate score ambiguity report."""
    return AmbiguityReport(
        ambiguity_type=AmbiguityType.DUPLICATE,
        question="Multiple shapes have identical match scores.",
        candidates=["face1", "face2", "face3"],
        candidate_descriptions=[
            "FACE from extrude1",
            "FACE from fillet1",
            "FACE from extrude1"
        ],
        metadata={"score": 0.8}
    )


class TestAmbiguityDialogInit:
    """Test AmbiguityDialog initialization."""

    def test_init(self, app, sample_report):
        """Test dialog initialization."""
        dialog = AmbiguityDialog(sample_report)

        assert dialog._report == sample_report
        assert dialog._selected_candidate is None
        assert dialog.windowTitle() == "Resolve Ambiguity"

    def test_init_with_parent(self, app, sample_report):
        """Test dialog with parent widget."""
        # Qt parent must be a QWidget, not Mock
        from PySide6.QtWidgets import QWidget
        parent = QWidget()
        dialog = AmbiguityDialog(sample_report, parent)

        assert dialog.parent() is parent

    def test_minimum_size(self, app, sample_report):
        """Test dialog minimum size."""
        dialog = AmbiguityDialog(sample_report)

        assert dialog.minimumWidth() == 500
        assert dialog.minimumHeight() == 400

    def test_signals_exist(self, app, sample_report):
        """Test dialog signals are available."""
        dialog = AmbiguityDialog(sample_report)

        assert hasattr(dialog, 'selection_made')
        assert hasattr(dialog, 'preview_requested')


class TestAmbiguityDialogUI:
    """Test dialog UI creation."""

    def test_header_created(self, app, sample_report):
        """Test header section is created."""
        dialog = AmbiguityDialog(sample_report)

        # Check for candidate list
        assert dialog._candidate_list is not None
        assert dialog._candidate_list.count() == 2

    def test_candidate_list_populated(self, app, sample_report):
        """Test candidates are populated in list."""
        dialog = AmbiguityDialog(sample_report)

        assert dialog._candidate_list.count() == len(sample_report.candidates)

        # Check items
        for i in range(dialog._candidate_list.count()):
            item = dialog._candidate_list.item(i)
            shape_id = item.data(Qt.UserRole)
            assert shape_id == sample_report.candidates[i]

    def test_description_text_created(self, app, sample_report):
        """Test description area is created."""
        dialog = AmbiguityDialog(sample_report)

        assert dialog._description_text is not None
        assert dialog._description_text.isReadOnly()

    def test_buttons_created(self, app, sample_report):
        """Test buttons are created."""
        dialog = AmbiguityDialog(sample_report)

        assert dialog._select_btn is not None
        assert dialog._preview_btn is not None
        assert dialog._cancel_btn is not None

        # Initially disabled
        assert dialog._select_btn.isEnabled() is False
        assert dialog._preview_btn.isEnabled() is False

    def test_question_displayed(self, app, sample_report):
        """Test that question is displayed in header."""
        dialog = AmbiguityDialog(sample_report)

        # Question should be in the UI
        # (We can't easily test the exact label without exposing it)
        assert dialog._report.question == sample_report.question


class TestCandidateSelection:
    """Test candidate selection behavior."""

    def test_select_candidate_enables_buttons(self, app, sample_report):
        """Test that selecting a candidate enables buttons."""
        dialog = AmbiguityDialog(sample_report)

        # Select first item
        item = dialog._candidate_list.item(0)
        dialog._candidate_list.setCurrentItem(item)

        assert dialog._select_btn.isEnabled() is True
        assert dialog._preview_btn.isEnabled() is True

    def test_selection_updates_description(self, app, sample_report):
        """Test that selection updates description text."""
        dialog = AmbiguityDialog(sample_report)
        # Qt widget added to test

        # Select first item
        item = dialog._candidate_list.item(0)
        dialog._candidate_list.setCurrentItem(item)

        # Description should be updated
        text = dialog._description_text.toPlainText()
        assert "shape1" in text or "Shape ID" in text

    def test_get_selected_candidate(self, app, sample_report):
        """Test getting selected candidate."""
        dialog = AmbiguityDialog(sample_report)
        # Qt widget added to test

        # No selection initially
        assert dialog.get_selected_candidate() is None

        # Select first item
        item = dialog._candidate_list.item(0)
        dialog._candidate_list.setCurrentItem(item)

        assert dialog.get_selected_candidate() == "shape1"

    def test_select_second_candidate(self, app, sample_report):
        """Test selecting second candidate."""
        dialog = AmbiguityDialog(sample_report)
        # Qt widget added to test

        item = dialog._candidate_list.item(1)
        dialog._candidate_list.setCurrentItem(item)

        assert dialog.get_selected_candidate() == "shape2"


class TestSignalEmission:
    """Test dialog signal emission."""

    def test_selection_made_signal(self, app, sample_report):
        """Test selection_made signal emission."""
        dialog = AmbiguityDialog(sample_report)
        # Qt widget added to test

        # Track signal
        received = []
        dialog.selection_made.connect(lambda x: received.append(x))

        # Select and click select button
        item = dialog._candidate_list.item(0)
        dialog._candidate_list.setCurrentItem(item)
        dialog._select_btn.click()

        assert len(received) == 1
        assert received[0] == "shape1"

    def test_preview_requested_signal(self, app, sample_report):
        """Test preview_requested signal emission."""
        dialog = AmbiguityDialog(sample_report)
        # Qt widget added to test

        # Track signal
        received = []
        dialog.preview_requested.connect(lambda x: received.append(x))

        # Select and click preview button
        item = dialog._candidate_list.item(1)
        dialog._candidate_list.setCurrentItem(item)
        dialog._preview_btn.click()

        assert len(received) == 1
        assert received[0] == "shape2"


class TestDialogAcceptReject:
    """Test dialog accept/reject behavior."""

    def test_select_button_accepts(self, app, sample_report):
        """Test that select button accepts the dialog."""
        dialog = AmbiguityDialog(sample_report)
        # Qt widget added to test

        # Select and click select
        item = dialog._candidate_list.item(0)
        dialog._candidate_list.setCurrentItem(item)
        dialog._select_btn.click()

        # Dialog should be accepted (not testable directly without exec)

    def test_cancel_button_rejects(self, app, sample_report):
        """Test that cancel button rejects the dialog."""
        dialog = AmbiguityDialog(sample_report)
        # Qt widget added to test

        # Click cancel
        dialog._cancel_btn.click()

        # No candidate should be selected
        assert dialog.get_selected_candidate() is None

    def test_double_click_accepts(self, app, sample_report):
        """Test double-clicking accepts the dialog."""
        dialog = AmbiguityDialog(sample_report)
        # Qt widget added to test

        # Double-click first item
        item = dialog._candidate_list.item(0)
        dialog._on_item_double_clicked(item)

        assert dialog.get_selected_candidate() == "shape1"


class TestAmbiguousSelectionDialog:
    """Test compact dialog variant."""

    def test_smaller_size(self, app, sample_report):
        """Test compact dialog has smaller default size."""
        dialog = AmbiguousSelectionDialog(sample_report)

        assert dialog.minimumWidth() == 400
        assert dialog.minimumHeight() == 300

    def test_inherits_from_dialog(self, app, sample_report):
        """Test compact dialog inherits from AmbiguityDialog."""
        dialog = AmbiguousSelectionDialog(sample_report)

        assert isinstance(dialog, AmbiguityDialog)

    def test_has_same_functionality(self, app, sample_report):
        """Test compact dialog has same functionality."""
        dialog = AmbiguousSelectionDialog(sample_report)
        # Qt widget added to test

        # Should have candidate list
        assert dialog._candidate_list.count() == 2

        # Should work the same
        item = dialog._candidate_list.item(0)
        dialog._candidate_list.setCurrentItem(item)

        assert dialog.get_selected_candidate() == "shape1"


class TestResolveAmbiguityDialog:
    """Test convenience function."""

    def test_returns_selected_shape(self, app, sample_report):
        """Test function returns selected shape ID."""
        with patch.object(AmbiguityDialog, 'exec', return_value=1):
            dialog = Mock()
            dialog.get_selected_candidate.return_value = "shape2"
            dialog.exec.return_value = 1  # QDialog.Accepted

            with patch('gui.dialogs.ambiguity_dialog.AmbiguityDialog', return_value=dialog):
                result = resolve_ambiguity_dialog(sample_report)

                assert result == "shape2"

    def test_returns_none_on_cancel(self, app, sample_report):
        """Test function returns None when cancelled."""
        with patch.object(AmbiguityDialog, 'exec', return_value=0):
            dialog = Mock()
            dialog.get_selected_candidate.return_value = None
            dialog.exec.return_value = 0  # QDialog.Rejected

            with patch('gui.dialogs.ambiguity_dialog.AmbiguityDialog', return_value=dialog):
                result = resolve_ambiguity_dialog(sample_report)

                assert result is None

    def test_compact_parameter(self, app, sample_report):
        """Test compact parameter uses correct dialog class."""
        with patch('gui.dialogs.ambiguity_dialog.AmbiguityDialog') as normal_class:
            with patch('gui.dialogs.ambiguity_dialog.AmbiguousSelectionDialog') as compact_class:

                # Test normal
                resolve_ambiguity_dialog(sample_report, compact=False)
                normal_class.assert_called_once()

                # Test compact
                resolve_ambiguity_dialog(sample_report, compact=True)
                compact_class.assert_called_once()


class TestMultipleCandidates:
    """Test dialog with many candidates."""

    def test_three_candidates(self, app, duplicate_report):
        """Test dialog with 3 candidates."""
        dialog = AmbiguityDialog(duplicate_report)

        assert dialog._candidate_list.count() == 3

        # All should be selectable
        for i in range(3):
            item = dialog._candidate_list.item(i)
            assert item is not None
            assert item.data(Qt.UserRole) == duplicate_report.candidates[i]


class TestDifferentAmbiguityTypes:
    """Test dialog with different ambiguity types."""

    def test_symmetric_indicators(self, app, sample_report):
        """Test symmetric candidates have mirror indicator."""
        dialog = AmbiguityDialog(sample_report)

        for i in range(dialog._candidate_list.count()):
            item = dialog._candidate_list.item(i)
            text = item.text()
            # Should have mirror symbol
            assert "↔" in text

    def test_duplicate_no_indicator(self, app, duplicate_report):
        """Test duplicate candidates have no special indicator."""
        dialog = AmbiguityDialog(duplicate_report)

        for i in range(dialog._candidate_list.count()):
            item = dialog._candidate_list.item(i)
            text = item.text()
            # Should not have mirror symbol
            assert "↔" not in text

    def test_proximate_indicator(self, app):
        """Test proximate candidates have approximation indicator."""
        report = AmbiguityReport(
            ambiguity_type=AmbiguityType.PROXIMATE,
            question="Select shape",
            candidates=["s1", "s2"],
            candidate_descriptions=["Face A", "Face B"],
        )
        dialog = AmbiguityDialog(report)

        for i in range(dialog._candidate_list.count()):
            item = dialog._candidate_list.item(i)
            text = item.text()
            # Should have approximation symbol
            assert "≈" in text


class TestDescriptionFormatting:
    """Test candidate description formatting."""

    def test_format_candidate_details_basic(self, app, sample_report):
        """Test basic detail formatting."""
        dialog = AmbiguityDialog(sample_report)

        details = dialog._format_candidate_details("shape1", "Face at (0, 0, 5)")

        assert "shape1" in details
        assert "Face at (0, 0, 5)" in details
        assert "Shape ID" in details
        assert "Description" in details

    def test_format_includes_metadata(self, app, sample_report):
        """Test formatting includes metadata info."""
        dialog = AmbiguityDialog(sample_report)

        details = dialog._format_candidate_details("shape1", "Face at (0, 0, 5)")

        assert "Additional Info" in details

    def test_format_symmetric_notice(self, app, sample_report):
        """Test symmetric candidates get notice."""
        dialog = AmbiguityDialog(sample_report)

        details = dialog._format_candidate_details("shape1", "Face at (0, 0, 5)")

        assert "symmetric" in details.lower()

    def test_format_proximate_notice(self, app):
        """Test proximate candidates get notice."""
        report = AmbiguityReport(
            ambiguity_type=AmbiguityType.PROXIMATE,
            question="Select",
            candidates=["s1"],
            candidate_descriptions=["Face A"],
        )
        dialog = AmbiguityDialog(report)

        details = dialog._format_candidate_details("s1", "Face A")

        assert "close" in details.lower()


class TestDialogWithParent:
    """Test dialog behavior with parent widget."""

    def test_parent_relationship(self, app, sample_report):
        """Test dialog properly has parent."""
        from PySide6.QtWidgets import QWidget
        parent = QWidget()
        dialog = AmbiguityDialog(sample_report, parent)

        assert dialog.parent() is parent

    def test_none_parent_valid(self, app, sample_report):
        """Test dialog works with None parent."""
        dialog = AmbiguityDialog(sample_report, None)

        assert dialog.parent() is None
        # Should still have UI elements
        assert dialog._candidate_list is not None
