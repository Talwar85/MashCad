"""
Notification Manager - W10 Error UX v2 Integration
====================================================
Verwaltet Toast-Notifications mit Error UX v2 Support.

W10 Paket B: Erweitert um status_class/severity Support aus Error-Envelope v2.
"""
from PySide6.QtCore import QPoint, QPropertyAnimation, Qt
from gui.widgets import NotificationWidget

class NotificationManager:
    def __init__(self, parent):
        self.parent = parent
        self.notifications = []

    def _map_status_to_style(self, level: str = "", status_class: str = "", severity: str = "") -> str:
        """
        W10 Paket B: Mappt Error UX v2 status_class/severity zu Notification-Styles.

        Priority: status_class > severity > level

        Args:
            level: Legacy level (info/warning/error/success/critical)
            status_class: status_class aus Error-Envelope v2 (WARNING_RECOVERABLE, BLOCKED, CRITICAL, ERROR)
            severity: severity aus Error-Envelope v2 (warning, blocked, critical, error)

        Returns:
            Notification style (info/warning/error/success)
        """
        # W10: Priorisiere status_class über severity über legacy level
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

    def show_toast_overlay(self, level, message, status_class="", severity=""):
        """Erstellt das Toast-Popup (ehemals _show_notification)

        W10 Paket B: Erweitert um status_class/severity Parameter."""
        # Mapping von Loguru levels für Style
        style = self._map_status_to_style(level, status_class, severity)

        # Widget erstellen
        notif = NotificationWidget(message, style, self.parent)
        self.notifications.append(notif)
        self.reposition_notifications()

    def show_notification(self, title: str, message: str, level: str = "info",
                         duration: int = 3000, status_class: str = "", severity: str = ""):
        """
        Zeigt eine Toast-Notification an (für Result-Pattern Integration)

        W10 Paket B: Erweitert um status_class/severity Parameter aus Error-Envelope v2.

        Args:
            title: Titel der Notification
            message: Nachricht der Notification
            level: Legacy level (info/warning/error/success/critical)
            duration: Anzeigedauer in ms
            status_class: status_class aus Error-Envelope v2 (WARNING_RECOVERABLE, BLOCKED, CRITICAL, ERROR)
            severity: severity aus Error-Envelope v2 (warning, blocked, critical, error)
        """
        # Kombiniere Title und Message
        if title:
            full_message = f"{title}: {message}"
        else:
            full_message = message

        # Nutze bestehende Toast-Overlay Methode mit Error UX v2 Support
        self.show_toast_overlay(level, full_message, status_class=status_class, severity=severity)

    def cleanup_notification(self, notif):
        if notif in self.notifications:
            self.notifications.remove(notif)
        notif.deleteLater()
        # Nach dem Löschen die anderen aufrücken lassen

    def reposition_notifications(self):
        """Berechnet Positionen und startet Animationen"""
        top_margin = 90
        spacing = 10
        y_pos = top_margin
        
        # Iteriere über alle aktiven Notifications
        for notif in self.notifications:
            if not notif.isVisible() and not notif.target_pos:
                # Neue Notification (noch nicht animiert)
                # Zentrieren
                x = (self.parent.width() - notif.width()) // 2
                
                # Cleanup Signal verbinden
                notif.anim.finished.connect(
                    lambda n=notif: self.cleanup_notification(n) if n.anim.direction() == QPropertyAnimation.Backward else None
                )
                
                # Animation starten
                notif.show_anim(QPoint(x, y_pos))
            
            elif notif.isVisible():
                # Bereits sichtbare Notifications verschieben wir nicht (einfacher Stack)
                pass
            
            # Platz für die nächste berechnen
            y_pos += notif.height() + spacing
