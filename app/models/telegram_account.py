"""
Modèle TelegramAccount — Bot Telegram lié à une entreprise.
Le token est chiffré avec Fernet pour la sécurité.
"""
from datetime import datetime, timezone
from cryptography.fernet import Fernet
from flask import current_app
from app.extensions import db

def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)

class TelegramAccount(db.Model):
    __tablename__ = "telegram_accounts"

    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    bot_token_encrypted = db.Column(db.Text, nullable=False)
    bot_username = db.Column(db.String(100))
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    business = db.relationship("Business", backref="telegram_accounts")

    def set_bot_token(self, token: str):
        key = current_app.config.get("FERNET_KEY")
        if not key:
            raise ValueError("FERNET_KEY manquante dans la configuration.")
        f = Fernet(key.encode() if isinstance(key, str) else key)
        self.bot_token_encrypted = f.encrypt(token.encode()).decode()

    def get_bot_token(self) -> str | None:
        if not self.bot_token_encrypted:
            return None
        try:
            key = current_app.config.get("FERNET_KEY")
            f = Fernet(key.encode() if isinstance(key, str) else key)
            return f.decrypt(self.bot_token_encrypted.encode()).decode()
        except Exception:
            return None

    def __repr__(self):
        return f"<TelegramAccount {self.name} (@{self.bot_username})>"