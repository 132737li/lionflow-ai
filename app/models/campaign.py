"""
Modèle Campaign — campagne d'envoi WhatsApp.
Statuts : draft, scheduled, running, paused, completed, cancelled.
"""
from datetime import datetime, timezone
from app.extensions import db


def _utcnow():
    """Heure UTC naïve (compatible MySQL DATETIME)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# Table d'association many-to-many entre Campaign et Contact
campaign_contacts = db.Table(
    "campaign_contacts",
    db.Column(
        "campaign_id", db.Integer,
        db.ForeignKey("campaigns.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    db.Column(
        "contact_id", db.Integer,
        db.ForeignKey("contacts.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    db.Column("added_at", db.DateTime, default=_utcnow),
    db.Index("idx_cc_campaign", "campaign_id"),
    db.Index("idx_cc_contact", "contact_id"),
)


class Campaign(db.Model):
    __tablename__ = "campaigns"
    __table_args__ = (
        db.Index("idx_campaign_business_status", "business_id", "status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(
        db.Integer,
        db.ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    template_id = db.Column(
        db.Integer,
        db.ForeignKey("templates.id", ondelete="SET NULL"),
    )
    whatsapp_account_id = db.Column(
    db.Integer,
    db.ForeignKey("whatsapp_accounts.id", ondelete="SET NULL"),
    )
    # 📎 Média associé (image, PDF, vidéo)
    media_file_id = db.Column(
        db.Integer,
        db.ForeignKey("media_files.id", ondelete="SET NULL"),
        index=True,
    )
    name = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text)
    status = db.Column(
        db.Enum(
            "draft", "scheduled", "running", "paused",
            "completed", "cancelled",
            name="campaign_status",
        ),
        nullable=False,
        default="draft",
        index=True,
    )
    scheduled_at = db.Column(db.DateTime, index=True)
    timezone = db.Column(db.String(64), default="UTC")
    started_at = db.Column(db.DateTime)
    finished_at = db.Column(db.DateTime)

    total_contacts = db.Column(db.Integer, nullable=False, default=0)
    sent_count = db.Column(db.Integer, nullable=False, default=0)
    delivered_count = db.Column(db.Integer, nullable=False, default=0)
    read_count = db.Column(db.Integer, nullable=False, default=0)
    failed_count = db.Column(db.Integer, nullable=False, default=0)

    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    # ----- Relations -----
    business = db.relationship("Business", back_populates="campaigns")
    template = db.relationship("Template", back_populates="campaigns")
    whatsapp_account = db.relationship("WhatsAppAccount", back_populates="campaigns")
    media_file = db.relationship("MediaFile", foreign_keys=[media_file_id])
    messages = db.relationship(
        "Message",
        back_populates="campaign",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
    target_contacts = db.relationship(
        "Contact",
        secondary=campaign_contacts,
        lazy="dynamic",
        backref=db.backref("campaigns_targeting", lazy="dynamic"),
    )

    # ----- Propriétés -----
    @property
    def progress_pct(self) -> float:
        if not self.total_contacts:
            return 0.0
        processed = self.sent_count + self.failed_count
        return round(min(processed / self.total_contacts * 100, 100), 2)

    @property
    def can_start(self) -> bool:
        return self.status in ("draft", "scheduled", "paused")

    @property
    def can_pause(self) -> bool:
        return self.status == "running"

    @property
    def can_cancel(self) -> bool:
        return self.status not in ("completed", "cancelled")

    def reset_counters(self) -> None:
        self.sent_count = 0
        self.delivered_count = 0
        self.read_count = 0
        self.failed_count = 0

    def recalc_counters(self) -> None:
        """Recalcule les compteurs depuis la table messages."""
        from app.models.message import Message
        counts = dict(
            db.session.query(Message.status, db.func.count(Message.id))
            .filter(Message.campaign_id == self.id)
            .group_by(Message.status)
            .all()
        )
        self.sent_count = counts.get("sent", 0) + counts.get("delivered", 0) + counts.get("read", 0)
        self.delivered_count = counts.get("delivered", 0) + counts.get("read", 0)
        self.read_count = counts.get("read", 0)
        self.failed_count = counts.get("failed", 0)

    def __repr__(self) -> str:
        return f"<Campaign {self.id} {self.name} [{self.status}]>"

    def to_dict(self, include_messages: bool = False) -> dict:
        data = {
            "id": self.id,
            "business_id": self.business_id,
            "template_id": self.template_id,
            "whatsapp_account_id": self.whatsapp_account_id,
            "media_file_id": self.media_file_id,
            "name": self.name,
            "message": self.message,
            "status": self.status,
            "scheduled_at": self.scheduled_at.isoformat() if self.scheduled_at else None,
            "timezone": self.timezone,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "total_contacts": self.total_contacts,
            "sent_count": self.sent_count,
            "delivered_count": self.delivered_count,
            "read_count": self.read_count,
            "failed_count": self.failed_count,
            "progress_pct": self.progress_pct,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_messages:
            data["messages"] = [m.to_dict() for m in self.messages.limit(100)]
        return data