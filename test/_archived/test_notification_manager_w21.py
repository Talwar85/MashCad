"""
W21 Paket D: Notification Manager Tests
========================================
Testet die neuen Notification Manager Features:
- Deduplication für identische Notifications
- Prioritätsregeln strikt implementiert
- Queue-Verhalten unter Last stabil
- Sichtbare Produktverbesserung

Author: AI-2 (Product Surface Cell)
Date: 2026-02-16
Branch: feature/v1-ux-aiB
"""

# CRITICAL: QT_OPENGL muss VOR jedem Qt/PyVista Import gesetzt werden
import os
os.environ["QT_OPENGL"] = "software"

import pytest
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtTest import QTest
from unittest.mock import Mock, patch
from datetime import datetime, timedelta
from collections import deque

from gui.managers.notification_manager import NotificationManager, NotificationEntry, _PRIORITY_ORDER


@pytest.fixture(scope="session")
def qt_app():
    """Session-weite QApplication Instanz."""
    app = QApplication.instance()
    if app is None:
        import sys
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def notification_manager(qt_app):
    """NotificationManager Fixture."""
    manager = NotificationManager(QWidget())
    yield manager
    # Cleanup
    for notif in manager.notifications:
        if notif.isVisible():
            notif.close()
        notif.deleteLater()


class TestNotificationDeduplication:
    """
    W21 Paket D: Tests für Deduplication.
    """

    def test_notification_entry_equality(self):
        """D-W21-R1: NotificationEntry Gleichheit basiert auf message und style."""
        entry1 = NotificationEntry("Test message", "error")
        entry2 = NotificationEntry("Test message", "error")
        entry3 = NotificationEntry("Test message", "warning")
        entry4 = NotificationEntry("Different message", "error")

        assert entry1 == entry2, "Same message and style should be equal"
        assert entry1 != entry3, "Different style should not be equal"
        assert entry1 != entry4, "Different message should not be equal"

    def test_notification_entry_hash(self):
        """D-W21-R2: NotificationEntry Hash basiert auf message und style."""
        entry1 = NotificationEntry("Test message", "error")
        entry2 = NotificationEntry("Test message", "error")

        assert hash(entry1) == hash(entry2), "Hash should be equal for same content"

    def test_dedup_window_exists(self, notification_manager):
        """D-W21-R3: Deduplication-Fenster ist definiert."""
        assert hasattr(notification_manager, '_dedup_window')
        assert notification_manager._dedup_window == timedelta(seconds=5)

    def test_duplicate_is_suppressed(self, notification_manager):
        """D-W21-R4: Duplikat im Zeitfenster wird unterdrückt."""
        # Erste Notification
        entry1 = NotificationEntry("Test message", "error")
        notification_manager._notification_history.append(entry1)

        # Gleiche Notification (Duplikat)
        entry2 = NotificationEntry("Test message", "error")
        is_dup = notification_manager._is_duplicate(entry2)

        assert is_dup, "Should detect duplicate within window"

    def test_old_notification_not_duplicate(self, notification_manager):
        """D-W21-R5: Alte Notification außerhalb Fenster ist kein Duplikat."""
        # Alte Notification (außerhalb Fenster)
        old_entry = NotificationEntry("Test message", "error",
                                       timestamp=datetime.now() - timedelta(seconds=10))
        notification_manager._notification_history.append(old_entry)

        # Neue gleich Nachricht
        new_entry = NotificationEntry("Test message", "error")
        is_dup = notification_manager._is_duplicate(new_entry)

        assert not is_dup, "Should not be duplicate outside window"

    def test_different_message_not_duplicate(self, notification_manager):
        """D-W21-R6: Andere Nachricht ist kein Duplikat."""
        entry1 = NotificationEntry("Message A", "error")
        notification_manager._notification_history.append(entry1)

        entry2 = NotificationEntry("Message B", "error")
        is_dup = notification_manager._is_duplicate(entry2)

        assert not is_dup, "Different message should not be duplicate"


class TestNotificationPriority:
    """
    W21 Paket D: Tests für Prioritätsregeln.
    """

    def test_priority_order_is_complete(self):
        """D-W21-R7: Prioritätsordnung ist vollständig definiert."""
        required_levels = ["critical", "error", "blocked", "warning", "info", "success"]
        for level in required_levels:
            assert level in _PRIORITY_ORDER, f"{level} should be in priority order"

    def test_critical_has_highest_priority(self):
        """D-W21-R8: Critical hat höchste Priority (niedrigster Score)."""
        entry_critical = NotificationEntry("Test", "critical")
        entry_error = NotificationEntry("Test", "error")

        assert entry_critical.priority_score() < entry_error.priority_score(), \
               "Critical should have higher priority than error"

    def test_error_has_higher_priority_than_warning(self):
        """D-W21-R9: Error hat höhere Priority als Warning."""
        entry_error = NotificationEntry("Test", "error")
        entry_warning = NotificationEntry("Test", "warning")

        assert entry_error.priority_score() < entry_warning.priority_score(), \
               "Error should have higher priority than warning"

    def test_warning_has_higher_priority_than_info(self):
        """D-W21-R10: Warning hat höhere Priority als Info."""
        entry_warning = NotificationEntry("Test", "warning")
        entry_info = NotificationEntry("Test", "info")

        assert entry_warning.priority_score() < entry_info.priority_score(), \
               "Warning should have higher priority than info"

    def test_pinned_has_higher_priority(self):
        """D-W21-R11: Pinned hat höhere Priority als nicht-pinned."""
        entry_pinned = NotificationEntry("Test", "info", pinned=True)
        entry_unpinned = NotificationEntry("Test", "error", pinned=False)

        # Pinned info sollte höhere Priority haben als unpinned error
        assert entry_pinned.priority_score() < entry_unpinned.priority_score(), \
               "Pinned should have higher priority"

    def test_status_class_mapping_critical(self, notification_manager):
        """D-W21-R12: CRITICAL status_class mappt zu error."""
        style = notification_manager._map_status_to_style(
            status_class="CRITICAL", severity="", level=""
        )
        assert style == "error", "CRITICAL should map to error"

    def test_status_class_mapping_blocked(self, notification_manager):
        """D-W21-R13: BLOCKED status_class mappt zu error."""
        style = notification_manager._map_status_to_style(
            status_class="BLOCKED", severity="", level=""
        )
        assert style == "error", "BLOCKED should map to error"

    def test_status_class_mapping_warning_recoverable(self, notification_manager):
        """D-W21-R14: WARNING_RECOVERABLE mappt zu warning."""
        style = notification_manager._map_status_to_style(
            status_class="WARNING_RECOVERABLE", severity="", level=""
        )
        assert style == "warning", "WARNING_RECOVERABLE should map to warning"


class TestNotificationQueue:
    """
    W21 Paket D: Tests für Queue-Verhalten.
    """

    def test_queue_exists(self, notification_manager):
        """D-W21-R15: Queue ist vorhanden."""
        assert hasattr(notification_manager, '_queue')
        assert isinstance(notification_manager._queue, deque)

    def test_max_concurrent_exists(self, notification_manager):
        """D-W21-R16: Max concurrent Limit ist definiert."""
        assert hasattr(notification_manager, '_max_concurrent')
        assert notification_manager._max_concurrent == 5

    def test_queue_timer_exists(self, notification_manager):
        """D-W21-R17: Queue-Timer ist vorhanden."""
        assert hasattr(notification_manager, '_queue_timer')

    def test_get_queue_size(self, notification_manager):
        """D-W21-R18: get_queue_size() liefert Queue-Größe."""
        notification_manager._queue.clear()
        assert notification_manager.get_queue_size() == 0

        notification_manager._queue.append(NotificationEntry("Test", "info"))
        assert notification_manager.get_queue_size() == 1

    def test_clear_queue(self, notification_manager):
        """D-W21-R19: clear_queue() leert die Queue."""
        notification_manager._queue.append(NotificationEntry("Test1", "info"))
        notification_manager._queue.append(NotificationEntry("Test2", "warning"))

        notification_manager.clear_queue()
        assert notification_manager.get_queue_size() == 0

    def test_get_history_count(self, notification_manager):
        """D-W21-R20: get_history_count() liefert History-Größe."""
        initial_count = notification_manager.get_history_count()

        # Ein paar Einträge hinzufügen
        for i in range(3):
            notification_manager._notification_history.append(
                NotificationEntry(f"Test {i}", "info")
            )

        assert notification_manager.get_history_count() >= initial_count + 3


class TestNotificationPinUnpin:
    """
    W21 Paket D: Tests für Pin/Unpin.
    """

    def test_pin_notification_method_exists(self, notification_manager):
        """D-W21-R21: pin_notification() Methode existiert."""
        assert hasattr(notification_manager, 'pin_notification')

    def test_unpin_notification_method_exists(self, notification_manager):
        """D-W21-R22: unpin_notification() Methode existiert."""
        assert hasattr(notification_manager, 'unpin_notification')

    def test_entry_pinned_attribute(self):
        """D-W21-R23: NotificationEntry hat pinned Attribut."""
        entry = NotificationEntry("Test", "info", pinned=False)
        assert not entry.pinned

        entry.pinned = True
        assert entry.pinned


class TestNotificationAnimationCoordinator:
    """
    W21 Paket D: Tests für Animation-Koordinator.
    """

    def test_animation_coordinator_exists(self, notification_manager):
        """D-W21-R24: AnimationCoordinator ist vorhanden."""
        assert hasattr(notification_manager, '_anim_coordinator')

    def test_coordinator_has_methods(self, notification_manager):
        """D-W21-R25: Koordinator hat show_notification und reposition_all."""
        coordinator = notification_manager._anim_coordinator
        assert hasattr(coordinator, 'show_notification')
        assert hasattr(coordinator, 'reposition_all')

    def test_coordinator_animating_flag(self, notification_manager):
        """D-W21-R26: Koordinator hat _animating Flag."""
        coordinator = notification_manager._anim_coordinator
        assert hasattr(coordinator, '_animating')


class TestNotificationProductImprovement:
    """
    W21 Paket D: Tests für sichtbare Produktverbesserung.
    """

    def test_show_notification_pinned_param(self, notification_manager):
        """D-W21-R27: show_notification() hat pinned Parameter."""
        import inspect
        sig = inspect.signature(notification_manager.show_notification)
        params = sig.parameters
        assert 'pinned' in params, "Should have pinned parameter"

    def test_show_toast_overlay_pinned_param(self, notification_manager):
        """D-W21-R28: show_toast_overlay() hat pinned Parameter."""
        import inspect
        sig = inspect.signature(notification_manager.show_toast_overlay)
        params = sig.parameters
        assert 'pinned' in params, "Should have pinned parameter"

    def test_reposition_uses_coordinator(self, notification_manager):
        """D-W21-R29: reposition_notifications() verwendet Koordinator."""
        import inspect
        source = inspect.getsource(notification_manager.reposition_notifications)

        # Sollte Animation-Koordinator verwenden
        assert "anim_coordinator" in source, "Should use animation coordinator"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
