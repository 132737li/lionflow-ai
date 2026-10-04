"""
Modèle AiConfig — configuration IA du chatbot pour une entreprise.
Chaque entreprise peut avoir sa propre config (provider, clé, modèle, ton).
La clé API est chiffrée avec Fernet (comme les tokens WhatsApp).
"""
from datetime import datetime, timezone
from app.extensions import db
from app.utils.crypto import encrypt_token, decrypt_token


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class AiConfig(db.Model):
    __tablename__ = "ai_configs"

    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(
        db.Integer,
        db.ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # --- Activation ---
    is_enabled = db.Column(db.Boolean, nullable=False, default=False, index=True)

    # --- Provider ---
    # 'openai' | 'anthropic' | 'groq' | 'custom'
    provider = db.Column(
        db.Enum("openai", "anthropic", "groq", "custom", name="ai_provider"),
        nullable=False,
        default="openai",
    )

    # --- API (clé chiffrée) ---
    api_key_encrypted = db.Column(db.Text)
    # Pour 'custom' : URL de base personnalisée
    api_base_url = db.Column(db.String(500))

    # --- Modèle ---
    # Ex: gpt-4o-mini, claude-3-5-haiku-20241022, llama-3.3-70b-versatile
    model_name = db.Column(db.String(100), default="gpt-4o-mini")

    # --- Prompt système ---
    system_prompt = db.Column(db.Text)
    # Contexte additionnel : infos entreprise, tarifs, horaires, etc.
    context = db.Column(db.Text)

    # --- Réglages ---
    temperature = db.Column(db.Float, default=0.7)
    max_tokens = db.Column(db.Integer, default=300)

    # --- Langue préférée pour les réponses ---
    # 'auto' = même langue que le client
    reply_language = db.Column(db.String(10), default="auto")

    # --- Quotas ---
    max_requests_per_month = db.Column(db.Integer, default=1000)
    requests_this_month = db.Column(db.Integer, nullable=False, default=0)
    reset_quota_at = db.Column(db.DateTime)

    # --- Statistiques ---
    total_requests = db.Column(db.Integer, nullable=False, default=0)
    total_tokens_used = db.Column(db.Integer, nullable=False, default=0)
    last_used_at = db.Column(db.DateTime)

    # --- Statut ---
    last_error = db.Column(db.String(500))

    # --- Timestamps ---
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    # --- Relations ---
    business = db.relationship(
        "Business",
        backref=db.backref("ai_config", uselist=False, cascade="all, delete-orphan"),
    )

    # ----- Clé API -----
    def set_api_key(self, raw_key: str) -> None:
        """Chiffre et stocke la clé API."""
        self.api_key_encrypted = encrypt_token(raw_key) if raw_key else None

    def get_api_key(self) -> str | None:
        """Déchiffre et retourne la clé API."""
        if not self.api_key_encrypted:
            return None
        return decrypt_token(self.api_key_encrypted)

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key_encrypted)

    # ----- Quota -----
    @property
    def quota_remaining(self) -> int:
        if not self.max_requests_per_month:
            return 999999
        return max(self.max_requests_per_month - self.requests_this_month, 0)

    @property
    def quota_exceeded(self) -> bool:
        if not self.max_requests_per_month:
            return False
        return self.requests_this_month >= self.max_requests_per_month

    # ----- Utilitaires -----
    def increment_usage(self, tokens: int = 0) -> None:
        """Incrémente les compteurs après un appel IA réussi."""
        self.requests_this_month += 1
        self.total_requests += 1
        self.total_tokens_used += tokens
        self.last_used_at = _utcnow()

    def reset_monthly_quota(self) -> None:
        """Remet à zéro le quota mensuel."""
        self.requests_this_month = 0
        self.reset_quota_at = _utcnow()

    @property
    def provider_display(self) -> str:
        return {
            "openai": "OpenAI",
            "anthropic": "Anthropic Claude",
            "groq": "Groq",
            "custom": "Custom",
        }.get(self.provider, self.provider)

    @property
    def status(self) -> str:
        """Statut calculé : 'active', 'disabled', 'quota_exceeded', 'error'."""
        if not self.is_enabled:
            return "disabled"
        if not self.has_api_key and self.provider != "custom":
            return "no_key"
        if self.quota_exceeded:
            return "quota_exceeded"
        if self.last_error:
            return "error"
        return "active"

    def __repr__(self) -> str:
        return f"<AiConfig business={self.business_id} provider={self.provider}>"

    def to_dict(self, include_secrets: bool = False) -> dict:
        data = {
            "id": self.id,
            "business_id": self.business_id,
            "is_enabled": self.is_enabled,
            "provider": self.provider,
            "provider_display": self.provider_display,
            "model_name": self.model_name,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "reply_language": self.reply_language,
            "has_api_key": self.has_api_key,
            "max_requests_per_month": self.max_requests_per_month,
            "requests_this_month": self.requests_this_month,
            "quota_remaining": self.quota_remaining,
            "total_requests": self.total_requests,
            "total_tokens_used": self.total_tokens_used,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "last_error": self.last_error,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_secrets:
            data["_api_key"] = self.get_api_key()
        return data