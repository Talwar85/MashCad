
from PySide6.QtCore import QPoint, QPropertyAnimation, Qt
from gui.widgets import NotificationWidget

class NotificationManager:
    def __init__(self, parent):
        self.parent = parent
        self.notifications = []

    def show_toast_overlay(self, level, message):
        """Erstellt das Toast-Popup (ehemals _show_notification)"""
        # Mapping von Loguru levels für Style
        if level in ["critical", "error"]: style = "error"
        elif level == "warning": style = "warning"
        elif level == "success": style = "success"
        else: style = "info"

        # Widget erstellen
        notif = NotificationWidget(message, style, self.parent)
        self.notifications.append(notif)
        self.reposition_notifications()

    def show_notification(self, title: str, message: str, level: str = "info", duration: int = 3000):
        """
        Zeigt eine Toast-Notification an (für Result-Pattern Integration)
        """
        # Kombiniere Title und Message
        if title:
            full_message = f"{title}: {message}"
        else:
            full_message = message

        # Nutze bestehende Toast-Overlay Methode
        self.show_toast_overlay(level, full_message)

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
