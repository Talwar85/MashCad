"""
Notification Manager - W21 Product Leap
========================================
Verwaltet Toast-Notifications mit Error UX v2 Support und Robustness-Features.

W10 Paket B: Error UX v2 Support (status_class/severity)
W21 Paket D: Deduplication, Prioritätsregeln, Queue-Stabilität
"""
from PySide6.QtCore import QPoint, QPropertyAnimation, Qt, QTimer
from PySide6.QtWidgets import QApplication
from collections import deque
from datetime import datetime, timedelta
from loguru import logger

from gui.widgets import NotificationWidget


# W21 Paket D: Prioritätsordnung für Notifications (höchste zuerst)
_PRIORITY_ORDER = {
    "critical": 0,
    "error": 1,
    "blocked": 2,
    "warning": 3,
    "info": 4,
    "success": 5,
}


class NotificationEntry:
    """
    W21 Paket D: Entry für Notification-Queue mit Metadaten.
    """
    def __init__(self, message, style, timestamp=None, pinned=False):
        self.message = message
        self.style = style
        self.timestamp = timestamp or datetime.now()
        self.pinned = pinned
        self.widget = None

    def __hash__(self):
        # Hash basierend auf message und style für Deduplication
        return hash((self.message, self.style))

    def __eq__(self, other):
        if not isinstance(other, NotificationEntry):
            return False
        return self.message == other.message and self.style == other.style

    def priority_score(self) -> int:
        """Gibt den Priority-Score zurück (niedriger = höhere Priority)."""
        base_priority = _PRIORITY_ORDER.get(self.style, 99)
        # Pinned Notifications haben höhere Priority
        return base_priority - 10 if self.pinned else base_priority


class NotificationManager:
    """
    Verwaltet Toast-Notifications mit Deduplication und Priorisierung.

    W21 Paket D Features:
    - Deduplication für identische Notifications im Zeitfenster
    - Strikte Prioritätsregeln
    - Queue-Verhalten unter Last stabil
    - Pin/Unpin für wichtige Meldungen
    """

    def __init__(self, parent):
        self.parent = parent
        self.notifications = []

        # W21 Paket D: History der letzten Notifications (für Queue/Deduplication)
        self._notification_history = deque(maxlen=50)  # Letzte 50 Notifications merken
        self._dedup_window = timedelta(seconds=5)  # 5 Sekunden Deduplication-Fenster

        # W21 Paket D: Queue für Burst-Situationen
        self._queue = deque()
        self._queue_timer = QTimer(parent)  # W19 Fix: parent (QObject) statt self übergeben
        self._queue_timer.setSingleShot(True)
        self._queue_timer.timeout.connect(self._process_queue)

        # W21 Paket D: Max gleichzeitige Notifications (um Überlappung zu vermeiden)
        self._max_concurrent = 5
        self._is_processing_queue = False

        # W21 Paket D: Animation-Koordinator (verhindert überlappende Animationen)
        self._anim_coordinator = AnimationCoordinator(self)

    def _map_status_to_style(self, level: str = "", status_class: str = "", severity: str = "") -> str:
        """
        W10 Paket B + W21 Paket D: Mappt Error UX v2 status_class/severity zu Notification-Styles.

        Priority: status_class > severity > level

        Args:
            level: Legacy level (info/warning/error/success/critical)
            status_class: status_class aus Error-Envelope v2 (WARNING_RECOVERABLE, BLOCKED, CRITICAL, ERROR)
            severity: severity aus Error-Envelope v2 (warning, blocked, critical, error)

        Returns:
            Notification style (info/warning/error/success)
        """
        # Zuerst status_class prüfen (höchste Priority)
        if status_class == "WARNING_RECOVERABLE":
            return "warning"
        elif status_class == "BLOCKED":
            return "error"
        elif status_class == "CRITICAL":
            return "error"
        elif status_class == "ERROR":
            return "error"

        # Dann severity prüfen (mittlere Priority)
        if severity == "warning":
            return "warning"
        elif severity == "blocked":
            return "error"
        elif severity == "critical":
            return "error"
        elif severity == "error":
            return "error"

        # Legacy level fallback (niedrigste Priority)
        if level in ["critical", "error"]:
            return "error"
        elif level == "warning":
            return "warning"
        elif level == "success":
            return "success"
        else:
            return "info"

    def show_toast_overlay(self, level, message, status_class="", severity="", pinned=False):
        """
        Erstellt das Toast-Popup mit Deduplication und Queue-Support.

        W21 Paket D:
        - Deduplication im 5-Sekunden-Fenster
        - Priority-basierte Queue bei Burst
        - Pin-Option für wichtige Meldungen
        """
        # Mapping von Loguru levels für Style
        style = self._map_status_to_style(level, status_class, severity)

        # W21 Paket D: Deduplication-Check
        entry = NotificationEntry(message, style, pinned=pinned)
        if self._is_duplicate(entry):
            logger.debug(f"[NOTIFICATION] Duplicate suppressed: {message[:50]}...")
            return  # Ignoriere Duplikat

        # Zur History hinzufügen
        self._notification_history.append(entry)

        # W21 Paket D: Queue-Prüfung bei vielen Notifications
        concurrent = len([n for n in self.notifications if n.isVisible()])
        if concurrent >= self._max_concurrent:
            # In die Queue einreihen
            self._queue.append(entry)
            logger.debug(f"[NOTIFICATION] Queued ({len(self._queue)} pending): {message[:50]}...")
            self._start_queue_timer()
            return

        # Widget erstellen
        notif = NotificationWidget(message, style, self.parent)
        entry.widget = notif
        self.notifications.append(notif)

        # W21 Paket D: Animation-Koordinator verwenden (keine überlappenden Animationen)
        self._anim_coordinator.show_notification(notif)

        # Cleanup-Planen
        self._schedule_cleanup(notif, entry)

    def show_notification(self, title: str, message: str, level: str = "info",
                         duration: int = 3000, status_class: str = "", severity: str = "",
                         pinned: bool = False):
        """
        Zeigt eine Toast-Notification an (für Result-Pattern Integration)

        W10 Paket B + W21 Paket D: Erweitert um status_class/severity Parameter und pinned-Option.

        Args:
            title: Titel der Notification
            message: Nachricht der Notification
            level: Legacy level (info/warning/error/success/critical)
            duration: Anzeigedauer in ms
            status_class: status_class aus Error-Envelope v2
            severity: severity aus Error-Envelope v2
            pinned: Ob diese Notification pinned sein soll (W21 Paket D)
        """
        # Kombiniere Title und Message
        if title:
            full_message = f"{title}: {message}"
        else:
            full_message = message

        # Nutze Toast-Overlay Methode mit allen Parametern
        self.show_toast_overlay(level, full_message, status_class=status_class,
                               severity=severity, pinned=pinned)

    def _is_duplicate(self, entry: NotificationEntry) -> bool:
        """
        W21 Paket D: Prüft ob die Notification ein Duplikat im Zeitfenster ist.

        Args:
            entry: Zu prüfende NotificationEntry

        Returns:
            True wenn die Nachricht im Deduplication-Fenster bereits angezeigt wurde
        """
        cutoff = datetime.now() - self._dedup_window

        # Prüfe ob gleiche Nachricht kürzlich angezeigt wurde
        for historic in self._notification_history:
            if historic.timestamp > cutoff and historic == entry:
                return True

        return False

    def _start_queue_timer(self):
        """W21 Paket D: Startet den Queue-Verarbeitungs-Timer."""
        if not self._queue_timer.isActive():
            # Verzögerung basierend auf Queue-Größe
            delay = min(500, 100 * len(self._queue))
            self._queue_timer.start(delay)

    def _process_queue(self):
        """W21 Paket D: Verarbeitet die Queue von wartenden Notifications."""
        if not self._queue:
            return

        # Prüfe ob Kapazität frei ist
        concurrent = len([n for n in self.notifications if n.isVisible()])
        if concurrent >= self._max_concurrent:
            # Noch voll, später erneut versuchen
            self._start_queue_timer()
            return

        # Nächstes Element aus Queue holen (nach Priority sortieren)
        sorted_queue = sorted(self._queue, key=lambda e: e.priority_score())
        entry = sorted_queue.pop(0)
        self._queue = deque(sorted_queue)

        # Notification anzeigen
        notif = NotificationWidget(entry.message, entry.style, self.parent)
        entry.widget = notif
        self.notifications.append(notif)
        self._notification_history.append(entry)

        self._anim_coordinator.show_notification(notif)
        self._schedule_cleanup(notif, entry)

        # Wenn noch mehr in Queue, weiters verarbeiten
        if self._queue:
            self._start_queue_timer()

    def _schedule_cleanup(self, notif, entry: NotificationEntry):
        """Plant das Cleanup für eine Notification."""
        # Pinned Notifications werden nicht automatisch geschlossen
        if entry.pinned:
            return

        # Cleanup-Timeout nach Anzeigezeit
        def cleanup_after_animation():
            if notif and notif.isVisible():
                QTimer.singleShot(3000, lambda: self._close_notification(notif, entry))

        # Wenn Animation fertig ist, Timer starten
        if hasattr(notif, 'anim') and notif.anim:
            notif.anim.finished.connect(cleanup_after_animation)

    def _close_notification(self, notif, entry: NotificationEntry):
        """Schließt eine Notification und verarbeitet Queue."""
        if notif in self.notifications:
            self.notifications.remove(notif)
        notif.close_anim()

        # Queue verarbeiten
        if self._queue:
            self._process_queue()

    def cleanup_notification(self, notif):
        """Entfernt eine Notification aus der Liste."""
        if notif in self.notifications:
            self.notifications.remove(notif)
        notif.deleteLater()

    def reposition_notifications(self):
        """
        Berechnet Positionen und startet Animationen.

        W21 Paket D: Verwendet Animation-Koordinator für keine überlappenden Animationen.
        """
        self._anim_coordinator.reposition_all()

    def pin_notification(self, notif):
        """
        W21 Paket D: Pinnt eine Notification (wird nicht automatisch geschlossen).

        Args:
            notif: Die zu pinnende Notification
        """
        # Zugehörigen Entry finden
        for entry in self._notification_history:
            if entry.widget == notif:
                entry.pinned = True
                logger.debug(f"[NOTIFICATION] Pinned: {entry.message[:50]}...")
                break

    def unpin_notification(self, notif):
        """
        W21 Paket D: Unpinnt eine Notification.

        Args:
            notif: Die zu unpinnende Notification
        """
        for entry in self._notification_history:
            if entry.widget == notif:
                entry.pinned = False
                logger.debug(f"[NOTIFICATION] Unpinned: {entry.message[:50]}...")
                # Notification nach kurzer Zeit schließen
                QTimer.singleShot(1000, lambda: self._close_notification(notif, entry))
                break

    def get_queue_size(self) -> int:
        """W21 Paket D: Gibt die aktuelle Queue-Größe zurück."""
        return len(self._queue)

    def get_history_count(self) -> int:
        """W21 Paket D: Gibt die Anzahl der Notifications in der History zurück."""
        return len(self._notification_history)

    def clear_queue(self):
        """W21 Paket D: Leert die Queue."""
        cleared = len(self._queue)
        self._queue.clear()
        logger.debug(f"[NOTIFICATION] Queue cleared ({cleared} items)")


class AnimationCoordinator:
    """
    W21 Paket D: Koordiniert Notification-Animationen um Überlappung zu vermeiden.

    Stellt sicher dass Animationen sequentiell ablaufen und keine
    visuellen Artefakte durch gleichzeitige Animationen entstehen.
    """

    def __init__(self, manager: NotificationManager):
        self.manager = manager
        self._animating = False
        self._pending_repositions = []

    def show_notification(self, notif):
        """Zeigt eine Notification mit koordinierter Animation an."""
        top_margin = 90
        spacing = 10
        y_pos = top_margin

        # Position berechnen
        for existing in self.manager.notifications:
            if existing.isVisible():
                y_pos += existing.height() + spacing

        x = (self.manager.parent.width() - notif.width()) // 2
        notif.show_anim(QPoint(x, y_pos))

    def reposition_all(self):
        """Repositioniert alle Notifications ohne Überlappung."""
        if self._animating:
            # Wenn bereits am animieren, postpone
            QTimer.singleShot(100, self.reposition_all)
            return

        self._animating = True
        try:
            top_margin = 90
            spacing = 10
            y_pos = top_margin

            for notif in self.manager.notifications:
                if notif.isVisible():
                    x = (self.manager.parent.width() - notif.width()) // 2
                    # Direkt positionieren ohne Animation (bei Reposition)
                    notif.move(QPoint(x, y_pos))
                    y_pos += notif.height() + spacing
        finally:
            self._animating = False
