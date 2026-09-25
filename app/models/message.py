"""
Modèle Message — message individuel envoyé dans une campagne.
Statuts : pending, sent, delivered, read, failed.
"""
from datetime import datetime, timezone
from app.extensions import db


def _utcnow():
    """Heure UTC naïve (compatible MySQL DATETIME)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Message(db.Model):
    __tablename__ = "messages"
    __table_args__ = (
        db.Index("idx_message_campaign_status", "campaign_id", "status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(
        db.Integer,
        db.ForeignKey("campaigns.id", ondelete="CASCADE"),
        index=True,
    )
    contact_id = db.Column(
        db.Integer,
        db.ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    whatsapp_account_id = db.Column(
        db.Integer,
        db.ForeignKey("whatsapp_accounts.id", ondelete="SET NULL"),
    )
    content = db.Column(db.Text)
    status = db.Column(
        db.Enum(
            "pending", "sent", "delivered", "read", "failed",
            name="message_status",
        ),
        nullable=False,
        default="pending",
        index=True,
    )
    external_id = db.Column(db.String(120), index=True)
    error = db.Column(db.String(500))

    sent_at = db.Column(db.DateTime)
    delivered_at = db.Column(db.DateTime)
    read_at = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    # ----- Relations -----
    campaign = db.relationship("Campaign", back_populates="messages")
    contact = db.relationship("Contact", back_populates="messages")
    whatsapp_account = db.relationship("WhatsAppAccount", back_populates="messages")

    # ----- Transitions -----
    def mark_sent(self, external_id: str | None = None) -> None:
        self.status = "sent"
        self.sent_at = _utcnow()
        if external_id:
            self.external_id = external_id

    def mark_delivered(self) -> None:
        self.status = "delivered"
        self.delivered_at = _utcnow()

    def mark_read(self) -> None:
        self.status = "read"
        self.read_at = _utcnow()

    def mark_failed(self, error: str) -> None:
        self.status = "failed"
        self.error = (error or "")[:500]

    def __repr__(self) -> str:
        return f"<Message {self.id} contact={self.contact_id} [{self.status}]>"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "campaign_id": self.campaign_id,
            "contact_id": self.contact_id,
            "whatsapp_account_id": self.whatsapp_account_id,
            "content": self.content,
            "status": self.status,
            "external_id": self.external_id,
            "error": self.error,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "delivered_at": self.delivered_at.isoformat() if self.delivered_at else None,
            "read_at": self.read_at.isoformat() if self.read_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }