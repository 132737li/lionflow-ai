"""
Modèle Log — journal d'activité.
Enregistre les actions utilisateurs pour audit et sécurité.
"""
from datetime import datetime, timezone
from app.extensions import db


def _utcnow():
    """Heure UTC naïve (compatible MySQL DATETIME)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Log(db.Model):
    __tablename__ = "logs"
    __table_args__ = (
        db.Index("idx_log_user_created", "user_id", "created_at"),
        db.Index("idx_log_action_created", "action", "created_at"),
    )

    id = db.Column(db.BigInteger, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )
    action = db.Column(db.String(80), nullable=False, index=True)
    description = db.Column(db.String(500))
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(255))

    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow, index=True)

    # ----- Relations -----
    user = db.relationship("User", back_populates="logs")

    def __repr__(self) -> str:
        return f"<Log {self.id} action={self.action} user={self.user_id}>"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "action": self.action,
            "description": self.description,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }