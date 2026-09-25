"""
Modèle Notification — notifications utilisateur.
Types : success, info, warning, error.
"""
from datetime import datetime, timezone
from app.extensions import db


def _utcnow():
    """Heure UTC naïve (compatible MySQL DATETIME)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text)
    type = db.Column(
        db.Enum("success", "info", "warning", "error", name="notif_type"),
        nullable=False,
        default="info",
    )
    is_read = db.Column(db.Boolean, nullable=False, default=False, index=True)
    link = db.Column(db.String(500))

    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)

    # ----- Relations -----
    user = db.relationship("User", back_populates="notifications")

    def mark_read(self) -> None:
        self.is_read = True

    def __repr__(self) -> str:
        return f"<Notification {self.id} user={self.user_id} [{self.type}]>"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title,
            "message": self.message,
            "type": self.type,
            "is_read": self.is_read,
            "link": self.link,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }