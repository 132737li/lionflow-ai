"""
Modèle ApiKey — clés d'API programmatiques pour un utilisateur.
On ne stocke QUE le hash SHA-256 de la clé.
"""
from datetime import datetime, timezone
from app.extensions import db
from app.utils.security import generate_api_key


def _utcnow():
    """Heure UTC naïve (compatible MySQL DATETIME)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ApiKey(db.Model):
    __tablename__ = "api_keys"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = db.Column(db.String(150), nullable=False)
    key_hash = db.Column(db.String(128), nullable=False, unique=True)
    last_used_at = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)

    # ----- Relations -----
    user = db.relationship("User", back_populates="api_keys")

    @classmethod
    def create_for_user(cls, user, name: str):
        raw, hashed = generate_api_key()
        api_key = cls(user_id=user.id, name=name, key_hash=hashed)
        db.session.add(api_key)
        db.session.flush()
        return api_key, raw

    def touch(self) -> None:
        self.last_used_at = _utcnow()

    def __repr__(self) -> str:
        return f"<ApiKey {self.id} user={self.user_id} name={self.name}>"

    def to_dict(self, include_raw: str | None = None) -> dict:
        data = {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "is_active": self.is_active,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_raw:
            data["key"] = include_raw
        return data