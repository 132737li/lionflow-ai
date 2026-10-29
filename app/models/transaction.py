"""
Modèle Transaction — enregistre chaque tentative de paiement.
"""
from datetime import datetime, timezone
from app.extensions import db

def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)

class Transaction(db.Model):
    __tablename__ = "transactions"

    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))

    # Référence interne unique (générée par nous) et référence Dusupay
    reference = db.Column(db.String(100), unique=True, nullable=False, index=True)
    provider_reference = db.Column(db.String(200)) # internal_reference de Dusupay

    plan = db.Column(db.String(50), nullable=False)
    amount = db.Column(db.Integer, nullable=False) # Montant en centimes ou en devise locale
    currency = db.Column(db.String(3), default="BIF") # Franc Burundais

    status = db.Column(
        db.Enum("pending", "success", "failed", "cancelled", name="tx_status"),
        default="pending", index=True
    )
    payment_method = db.Column(db.String(50)) # "MOBILE_MONEY", "CARD"
    provider = db.Column(db.String(50)) # "dusupay"

    created_at = db.Column(db.DateTime, default=_utcnow)
    completed_at = db.Column(db.DateTime)

    business = db.relationship("Business", backref="transactions")
    user = db.relationship("User", backref="transactions")

    def __repr__(self):
        return f"<Transaction {self.reference} {self.status}>"