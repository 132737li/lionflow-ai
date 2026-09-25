"""
Modèle WhatsAppAccount — compte WhatsApp Cloud API d'une entreprise.
Le token d'accès est chiffré avec Fernet (clé dérivée de SECRET_KEY).
"""
from datetime import datetime, timezone
from app.extensions import db
from app.utils.crypto import encrypt_token, decrypt_token


def _utcnow():
    """Heure UTC naïve (compatible MySQL DATETIME)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class WhatsAppAccount(db.Model):
    __tablename__ = "whatsapp_accounts"

    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(
        db.Integer,
        db.ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = db.Column(db.String(150), nullable=False)
    phone_number = db.Column(db.String(30), nullable=False)
    phone_number_id = db.Column(db.String(80))
    business_account_id = db.Column(db.String(80))
    access_token_encrypted = db.Column(db.Text)
    status = db.Column(
        db.Enum("disconnected", "connected", "error", name="waba_status"),
        nullable=False,
        default="disconnected",
    )
    connected_at = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    # ----- Relations -----
    business = db.relationship("Business", back_populates="whatsapp_accounts")
    campaigns = db.relationship(
        "Campaign",
        back_populates="whatsapp_account",
        passive_deletes=True,
        lazy="dynamic",
    )
    messages = db.relationship(
        "Message",
        back_populates="whatsapp_account",
        passive_deletes=True,
        lazy="dynamic",
    )

    # ----- Token -----
    def set_access_token(self, raw_token: str) -> None:
        self.access_token_encrypted = encrypt_token(raw_token) if raw_token else None

    def get_access_token(self) -> str | None:
        if not self.access_token_encrypted:
            return None
        return decrypt_token(self.access_token_encrypted)

    @property
    def has_token(self) -> bool:
        return bool(self.access_token_encrypted)

    @property
    def is_connected(self) -> bool:
        return self.status == "connected" and self.has_token

    def __repr__(self) -> str:
        return f"<WhatsAppAccount {self.id} {self.name} ({self.status})>"

    def to_dict(self, include_token: bool = False) -> dict:
        data = {
            "id": self.id,
            "business_id": self.business_id,
            "name": self.name,
            "phone_number": self.phone_number,
            "phone_number_id": self.phone_number_id,
            "business_account_id": self.business_account_id,
            "status": self.status,
            "has_token": self.has_token,
            "connected_at": self.connected_at.isoformat() if self.connected_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_token:
            data["_access_token"] = self.get_access_token()
        return data