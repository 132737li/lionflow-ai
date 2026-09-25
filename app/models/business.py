"""
Modèle Business — entreprise cliente (tenant logique).
Chaque utilisateur peut posséder une ou plusieurs entreprises.
"""
from datetime import datetime, timezone
from app.extensions import db


def _utcnow():
    """Heure UTC naïve (compatible MySQL DATETIME)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Business(db.Model):
    __tablename__ = "businesses"

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = db.Column(db.String(200), nullable=False, index=True)
    email = db.Column(db.String(255))
    phone = db.Column(db.String(30))
    address = db.Column(db.String(500))
    country = db.Column(db.String(100))
    logo_path = db.Column(db.String(500))

    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    # ----- Relations -----
    owner = db.relationship("User", back_populates="businesses")
    contacts = db.relationship(
        "Contact",
        back_populates="business",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
    campaigns = db.relationship(
        "Campaign",
        back_populates="business",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
    templates = db.relationship(
        "Template",
        back_populates="business",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
    whatsapp_accounts = db.relationship(
        "WhatsAppAccount",
        back_populates="business",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
    subscriptions = db.relationship(
        "Subscription",
        back_populates="business",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
    payments = db.relationship(
        "Payment",
        back_populates="business",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )

    # ----- Propriétés -----
    @property
    def subscription(self):
        """Retourne l'abonnement actif le plus récent, ou None."""
        return (
            self.subscriptions
            .filter_by(status="active")
            .order_by(db.desc("id"))
            .first()
        )

    @property
    def plan(self) -> str:
        sub = self.subscription
        return sub.plan if sub else "free"

    @property
    def plan_config(self) -> dict:
        from flask import current_app
        plans = current_app.config.get("PLANS", {})
        return plans.get(self.plan, plans.get("free", {}))

    def contact_count(self) -> int:
        return self.contacts.count()

    def can_add_contact(self) -> bool:
        limit = self.plan_config.get("max_contacts", 0)
        if limit == 0:
            return True
        return self.contact_count() < limit

    def can_add_whatsapp_account(self) -> bool:
        limit = self.plan_config.get("max_whatsapp_accounts", 0)
        if limit == 0:
            return True
        return self.whatsapp_accounts.count() < limit

    def __repr__(self) -> str:
        return f"<Business {self.id} {self.name}>"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "owner_id": self.owner_id,
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "address": self.address,
            "country": self.country,
            "logo_path": self.logo_path,
            "plan": self.plan,
            "contacts_count": self.contacts.count(),
            "campaigns_count": self.campaigns.count(),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }