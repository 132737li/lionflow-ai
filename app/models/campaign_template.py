"""
Modèle CampaignTemplate — modèle de campagne pré-rempli.
Permet de créer une campagne en 1 clic avec un message, un média et des réglages pré-configurés.
"""
from datetime import datetime, timezone
from app.extensions import db


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class CampaignTemplate(db.Model):
    __tablename__ = "campaign_templates"

    id = db.Column(db.Integer, primary_key=True)

    # null = template global (fourni par LionFlow AI)
    # sinon = template privé de l'entreprise
    business_id = db.Column(
        db.Integer,
        db.ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # --- Identité ---
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.String(500))
    icon = db.Column(db.String(10), default="📢")   # emoji
    category = db.Column(
        db.Enum(
            "promotion", "bienvenue", "relance", "evenement",
            "anniversaire", "info", "autre",
            name="campaign_template_category",
        ),
        nullable=False,
        default="autre",
        index=True,
    )

    # --- Pré-configuration ---
    default_message = db.Column(db.Text)                    # Message par défaut
    default_template_id = db.Column(
        db.Integer,
        db.ForeignKey("templates.id", ondelete="SET NULL"),
    )
    default_media_file_id = db.Column(
        db.Integer,
        db.ForeignKey("media_files.id", ondelete="SET NULL"),
    )
    default_timezone = db.Column(db.String(64), default="UTC")

    # --- Visibilité ---
    is_public = db.Column(db.Boolean, nullable=False, default=False, index=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    # --- Statistiques ---
    usage_count = db.Column(db.Integer, nullable=False, default=0)
    last_used_at = db.Column(db.DateTime)

    # --- Timestamps ---
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    # --- Relations ---
    business = db.relationship("Business", backref=db.backref("campaign_templates", lazy="dynamic"))
    template = db.relationship("Template", foreign_keys=[default_template_id])
    media_file = db.relationship("MediaFile", foreign_keys=[default_media_file_id])

    # --- Utilitaires ---
    def increment_usage(self) -> None:
        self.usage_count += 1
        self.last_used_at = _utcnow()

    @property
    def icon_or_default(self) -> str:
        return self.icon or "📢"

    @property
    def is_global(self) -> bool:
        return self.business_id is None

    @property
    def category_label(self) -> str:
        return {
            "promotion": "Promotion",
            "bienvenue": "Bienvenue",
            "relance": "Relance",
            "evenement": "Événement",
            "anniversaire": "Anniversaire",
            "info": "Information",
            "autre": "Autre",
        }.get(self.category, self.category)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "business_id": self.business_id,
            "name": self.name,
            "description": self.description,
            "icon": self.icon_or_default,
            "category": self.category,
            "category_label": self.category_label,
            "default_message": self.default_message,
            "default_template_id": self.default_template_id,
            "default_media_file_id": self.default_media_file_id,
            "default_timezone": self.default_timezone,
            "is_public": self.is_public,
            "is_global": self.is_global,
            "is_active": self.is_active,
            "usage_count": self.usage_count,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:
        return f"<CampaignTemplate {self.id} {self.name} ({self.category})>"