"""
Service de notifications.
Crée des notifications utilisateur liées à différents événements.
"""
from app.extensions import db
from app.models.notification import Notification


class NotificationService:

    @staticmethod
    def notify(
        user_id: int,
        title: str,
        message: str = "",
        type: str = "info",
        link: str | None = None,
    ) -> Notification:
        """Crée et enregistre une notification."""
        if type not in ("success", "info", "warning", "error"):
            type = "info"
        notif = Notification(
            user_id=user_id,
            title=title[:200],
            message=(message or "")[:2000],
            type=type,
            link=link,
        )
        db.session.add(notif)
        db.session.commit()
        return notif

    @staticmethod
    def mark_all_read(user_id: int) -> int:
        count = (
            Notification.query
            .filter_by(user_id=user_id, is_read=False)
            .update({"is_read": True})
        )
        db.session.commit()
        return count

    @staticmethod
    def unread_count(user_id: int) -> int:
        return Notification.query.filter_by(user_id=user_id, is_read=False).count()