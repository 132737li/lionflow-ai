"""
Modèle ChatbotConversation — conversation entre un client et le chatbot.
Permet de tracer l'historique et de gérer le transfert vers un humain.
"""
from datetime import datetime, timezone
from app.extensions import db


def _utcnow():
    """Heure UTC naïve (compatible MySQL DATETIME)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ChatbotConversation(db.Model):
    __tablename__ = "chatbot_conversations"
    __table_args__ = (
        db.Index("idx_chatbot_conv_business_status", "business_id", "status"),
        db.Index("idx_chatbot_conv_contact", "contact_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(
        db.Integer,
        db.ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    contact_id = db.Column(
        db.Integer,
        db.ForeignKey("contacts.id", ondelete="SET NULL"),
        index=True,
    )

    # État de la conversation
    status = db.Column(
        db.Enum(
            "active",       # Le chatbot répond automatiquement
            "waiting",      # En attente de réponse humaine
            "human",        # Prise en main par un humain
            "closed",       # Terminée
            name="chatbot_conv_status",
        ),
        nullable=False,
        default="active",
        index=True,
    )

    # Message du client qui a déclenché
    trigger_message = db.Column(db.Text)

    # Nombre de messages automatiques envoyés
    auto_replies_count = db.Column(db.Integer, nullable=False, default=0)

    # Priorité : élevée si le client demande un humain
    escalated = db.Column(db.Boolean, nullable=False, default=False)

    # Notes internes
    notes = db.Column(db.Text)

    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow, index=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)
    closed_at = db.Column(db.DateTime)

    # ----- Relations -----
    business = db.relationship("Business", backref=db.backref("chatbot_conversations", lazy="dynamic"))
    contact = db.relationship("Contact", backref=db.backref("chatbot_conversations", lazy="dynamic"))

    # ----- Méthodes -----
    def escalate(self) -> None:
        """Marque la conversation comme nécessitant un humain."""
        self.status = "waiting"
        self.escalated = True

    def take_over(self) -> None:
        """Un humain prend la main."""
        self.status = "human"

    def close(self) -> None:
        """Ferme la conversation."""
        self.status = "closed"
        self.closed_at = _utcnow()

    def __repr__(self) -> str:
        return f"<ChatbotConversation {self.id} status={self.status}>"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "business_id": self.business_id,
            "contact_id": self.contact_id,
            "contact_name": self.contact.full_name if self.contact else None,
            "contact_phone": self.contact.phone if self.contact else None,
            "status": self.status,
            "trigger_message": self.trigger_message,
            "auto_replies_count": self.auto_replies_count,
            "escalated": self.escalated,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }