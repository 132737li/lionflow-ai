"""
Modèle Payment — paiement d'un abonnement.
Aucune donnée bancaire sensible n'est stockée ici.
"""
from datetime import datetime, timezone
from app.extensions import db


def _utcnow():
    """Heure UTC naïve."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Payment(db.Model):
    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(
        db.Integer,
        db.ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    subscription_id = db.Column(
        db.Integer,
        db.ForeignKey("subscriptions.id", ondelete="SET NULL"),
    )
    provider = db.Column(db.String(50), default="generic")
    amount_cents = db.Column(db.Integer, nullable=False, default=0)
    currency = db.Column(db.String(10), default="BIF")
    status = db.Column(
        db.Enum(
            "pending", "succeeded", "failed", "refunded",
            name="payment_status",
        ),
        nullable=False,
        default="pending",
        index=True,
    )
    external_id = db.Column(db.String(120), index=True)
    payment_url = db.Column(db.String(500))       # URL de paiement du provider
    provider_response = db.Column(db.Text)         # Réponse brute du provider

    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    # ----- Relations -----
    business = db.relationship("Business", back_populates="payments")
    subscription = db.relationship("Subscription", back_populates="payments")

    @property
    def amount_euros(self) -> float:
        return round(self.amount_cents / 100, 2)

    def __repr__(self) -> str:
        return f"<Payment {self.id} {self.amount_euros}€ [{self.status}]>"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "business_id": self.business_id,
            "subscription_id": self.subscription_id,
            "provider": self.provider,
            "amount_cents": self.amount_cents,
            "amount_euros": self.amount_euros,
            "currency": self.currency,
            "status": self.status,
            "external_id": self.external_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }