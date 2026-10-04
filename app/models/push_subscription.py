"""
Modèle PushSubscription — abonnement aux notifications push.
Stocke les infos d'abonnement PWA de chaque utilisateur.
"""
from datetime import datetime, timezone
from app.extensions import db


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class PushSubscription(db.Model):
    __tablename__ = "push_subscriptions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Endpoint unique fourni par le navigateur (max ~500 caractères)
    endpoint = db.Column(db.String(500), nullable=False, unique=True)
    # Clés de chiffrement (p256dh + auth)
    p256dh = db.Column(db.String(255), nullable=False)
    auth = db.Column(db.String(255), nullable=False)
    # User agent (pour distinguer les appareils)
    user_agent = db.Column(db.String(255))
    # Statut
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    last_used_at = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    # Relations
    user = db.relationship("User", backref=db.backref("push_subscriptions", lazy="dynamic"))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "endpoint": self.endpoint[:50] + "…",
            "user_agent": self.user_agent,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f"<PushSubscription {self.id} user={self.user_id}>"