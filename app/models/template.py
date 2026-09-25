"""
Modèle Template — modèle de message réutilisable.
Variables : {{prenom}}, {{nom}}, {{entreprise}}.
"""
from datetime import datetime, timezone
from app.extensions import db


def _utcnow():
    """Heure UTC naïve (compatible MySQL DATETIME)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Template(db.Model):
    __tablename__ = "templates"

    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(
        db.Integer,
        db.ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = db.Column(db.String(150), nullable=False, index=True)
    category = db.Column(db.String(80), default="general")
    content = db.Column(db.Text, nullable=False)
    language = db.Column(db.String(10), default="fr")

    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    # ----- Relations -----
    business = db.relationship("Business", back_populates="templates")
    campaigns = db.relationship(
        "Campaign",
        back_populates="template",
        passive_deletes=True,
        lazy="dynamic",
    )

    # ----- Rendu -----
    def render(self, contact) -> str:
        text = self.content or ""
        replacements = {
            "{{prenom}}": contact.first_name or "",
            "{{nom}}": contact.last_name or "",
            "{{entreprise}}": contact.company or (self.business.name if self.business else ""),
            "{{telephone}}": contact.phone or "",
            "{{email}}": contact.email or "",
        }
        for key, value in replacements.items():
            text = text.replace(key, value)
        return text

    def __repr__(self) -> str:
        return f"<Template {self.id} {self.name}>"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "business_id": self.business_id,
            "name": self.name,
            "category": self.category,
            "content": self.content,
            "language": self.language,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }