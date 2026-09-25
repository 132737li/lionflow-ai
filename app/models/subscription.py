"""
Modèle Subscription — abonnement SaaS d'une entreprise.
Plans : free, pro, business.
"""
from datetime import datetime, timezone, timedelta
from app.extensions import db


def _utcnow():
    """Heure UTC naïve (compatible MySQL DATETIME)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Subscription(db.Model):
    __tablename__ = "subscriptions"

    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(
        db.Integer,
        db.ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    plan = db.Column(
        db.Enum("free", "pro", "business", name="sub_plan"),
        nullable=False,
        default="free",
    )
    status = db.Column(
        db.Enum(
            "active", "past_due", "cancelled", "expired",
            name="sub_status",
        ),
        nullable=False,
        default="active",
        index=True,
    )
    started_at = db.Column(db.DateTime, nullable=False, default=_utcnow)
    expires_at = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    # ----- Relations -----
    business = db.relationship("Business", back_populates="subscriptions")
    payments = db.relationship(
        "Payment",
        back_populates="subscription",
        passive_deletes=True,
        lazy="dynamic",
    )

    # ----- Propriétés -----
    @property
    def is_active_now(self) -> bool:
        if self.status != "active":
            return False
        if self.expires_at and self.expires_at < _utcnow():
            return False
        return True

    @property
    def days_remaining(self):
        if not self.expires_at:
            return None
        delta = self.expires_at - _utcnow()
        return max(delta.days, 0)

    def extend(self, days: int = 30) -> None:
        base = self.expires_at or _utcnow()
        self.expires_at = base + timedelta(days=days)

    def __repr__(self) -> str:
        return f"<Subscription {self.id} business={self.business_id} {self.plan} [{self.status}]>"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "business_id": self.business_id,
            "plan": self.plan,
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "days_remaining": self.days_remaining,
            "is_active_now": self.is_active_now,
        }