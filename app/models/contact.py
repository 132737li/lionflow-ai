"""
Modèle Contact — contact WhatsApp d'une entreprise.
Contrainte unique : (business_id, phone) pour éviter les doublons.
"""
from datetime import datetime, timezone
from app.extensions import db


def _utcnow():
    """Heure UTC naïve (compatible MySQL DATETIME)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Contact(db.Model):
    __tablename__ = "contacts"
    __table_args__ = (
        db.UniqueConstraint("business_id", "phone", name="uq_contact_business_phone"),
        db.Index("idx_contact_business_status", "business_id", "status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(
        db.Integer,
        db.ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    first_name = db.Column(db.String(120))
    last_name = db.Column(db.String(120))
    phone = db.Column(db.String(30), nullable=False)
    email = db.Column(db.String(255))
    company = db.Column(db.String(200))
    tags = db.Column(db.String(500))
    status = db.Column(
        db.Enum("active", "inactive", "blocked", name="contact_status"),
        nullable=False,
        default="active",
        index=True,
    )

    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    # ----- Relations -----
    business = db.relationship("Business", back_populates="contacts")
    messages = db.relationship(
        "Message",
        back_populates="contact",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )

    # ----- Propriétés -----
    @property
    def full_name(self) -> str:
        parts = [self.first_name or "", self.last_name or ""]
        name = " ".join(p for p in parts if p).strip()
        return name or self.phone

    @property
    def tags_list(self) -> list:
        if not self.tags:
            return []
        return [t.strip() for t in self.tags.split(",") if t.strip()]

    def set_tags(self, tags: list) -> None:
        self.tags = ",".join(t.strip() for t in tags if t and t.strip())

    def __repr__(self) -> str:
        return f"<Contact {self.id} {self.phone}>"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "business_id": self.business_id,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "full_name": self.full_name,
            "phone": self.phone,
            "email": self.email,
            "company": self.company,
            "tags": self.tags_list,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }