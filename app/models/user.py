"""
Modèle User — compte utilisateur LionFlow AI.
Rôles : 'admin' (super-admin plateforme) et 'user'.
"""
from datetime import datetime, timezone
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from app.extensions import db, bcrypt


def _utcnow():
    """Retourne l'heure UTC naïve (compatible MySQL DATETIME)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    first_name = db.Column(db.String(100))
    last_name = db.Column(db.String(100))
    role = db.Column(
        db.Enum("admin", "user", name="user_role"),
        nullable=False,
        default="user",
        index=True,
    )
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    is_verified = db.Column(db.Boolean, nullable=False, default=False)

    # 📸 Photo de profil
    avatar_path = db.Column(db.String(500))
    
    # 🌍 Langue préférée
    language = db.Column(db.String(5), nullable=False, default="fr")

    # 🔐 2FA (TOTP)
    totp_secret = db.Column(db.String(255))           # Secret chiffré
    totp_enabled = db.Column(db.Boolean, nullable=False, default=False, index=True)
    totp_backup_codes = db.Column(db.Text)            # JSON : liste de hash
    totp_confirmed_at = db.Column(db.DateTime)

    reset_token = db.Column(db.String(128), index=True)
    reset_token_exp = db.Column(db.DateTime)

    last_login_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    # ----- Relations -----
    businesses = db.relationship(
        "Business",
        back_populates="owner",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
    notifications = db.relationship(
        "Notification",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
    api_keys = db.relationship(
        "ApiKey",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
    logs = db.relationship(
        "Log",
        back_populates="user",
        passive_deletes=True,
        lazy="dynamic",
    )

    # ----- Méthodes -----
    def set_password(self, password: str) -> None:
        """Hash sécurisé avec bcrypt (fallback werkzeug si indisponible)."""
        try:
            self.password_hash = bcrypt.generate_password_hash(password).decode("utf-8")
        except Exception:
            self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        if not self.password_hash:
            return False
        try:
            return bcrypt.check_password_hash(self.password_hash, password)
        except Exception:
            return check_password_hash(self.password_hash, password)

    @property
    def full_name(self) -> str:
        parts = [self.first_name or "", self.last_name or ""]
        name = " ".join(p for p in parts if p).strip()
        return name or self.email

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def initials(self) -> str:
        """Retourne les initiales (pour affichage si pas d'avatar)."""
        first = (self.first_name or "")[:1].upper()
        last = (self.last_name or "")[:1].upper()
        return f"{first}{last}" or "?"

    def __repr__(self) -> str:
        return f"<User {self.id} {self.email} ({self.role})>"

    def to_dict(self, include_private: bool = False) -> dict:
        data = {
            "id": self.id,
            "email": self.email,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "full_name": self.full_name,
            "role": self.role,
            "is_active": self.is_active,
            "is_verified": self.is_verified,
            "avatar_path": self.avatar_path,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login_at": self.last_login_at.isoformat() if self.last_login_at else None,
        }
        if include_private:
            data["businesses_count"] = self.businesses.count()
        return data