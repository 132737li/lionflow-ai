"""
Utilitaires de sécurité : API keys, logs d'activité.
"""
import secrets
import hashlib
from flask import request
from flask_login import current_user

from app.extensions import db


def generate_api_key() -> tuple[str, str]:
    """
    Retourne (clé_claire, hash_sha256).
    On ne stocke QUE le hash.
    """
    raw = "lf_" + secrets.token_urlsafe(32)
    h = hashlib.sha256(raw.encode()).hexdigest()
    return raw, h


def hash_api_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def log_activity(action: str, description: str = "", user_id: int | None = None):
    """
    Enregistre une activité dans la table logs.
    Import local pour éviter les cycles.
    """
    from app.models.log import Log
    uid = user_id
    if uid is None and current_user.is_authenticated:
        uid = current_user.id
    ip = request.remote_addr if request else None
    ua = request.headers.get("User-Agent", "")[:255] if request else ""
    log = Log(
        user_id=uid,
        action=action,
        description=description,
        ip_address=ip,
        user_agent=ua,
    )
    db.session.add(log)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()