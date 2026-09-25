"""
Chiffrement symétrique des tokens sensibles (WhatsApp access tokens).
Utilise Fernet (AES-128-CBC + HMAC-SHA256).
La clé est dérivée de SECRET_KEY via PBKDF2-HMAC-SHA256 + sel fixe applicatif.
"""
import base64
import hashlib
import os
from cryptography.fernet import Fernet, InvalidToken

# Sel fixe applicatif : ne change pas entre redémarrages.
# Peut être surchargé via env TOKEN_ENCRYPTION_SALT si besoin.
_SALT = os.getenv("TOKEN_ENCRYPTION_SALT", "lionflow-ai-token-salt-v1").encode()
_ITERATIONS = 100_000


def _derive_key() -> bytes:
    """
    Dérive une clé Fernet (32 octets URL-safe base64) depuis SECRET_KEY.
    """
    from flask import current_app
    secret = (
        current_app.config.get("SECRET_KEY")
        if current_app
        else os.getenv("SECRET_KEY", "dev-secret-change-me")
    )
    if not secret:
        secret = "dev-secret-change-me"
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        secret.encode(),
        _SALT,
        _ITERATIONS,
        dklen=32,
    )
    return base64.urlsafe_b64encode(derived)


def encrypt_token(raw: str) -> str:
    """Chiffre un token en clair et retourne une chaîne base64-safe."""
    if not raw:
        return ""
    f = Fernet(_derive_key())
    return f.encrypt(raw.encode()).decode()


def decrypt_token(encrypted: str) -> str | None:
    """Déchiffre un token. Retourne None si invalide."""
    if not encrypted:
        return None
    try:
        f = Fernet(_derive_key())
        return f.decrypt(encrypted.encode()).decode()
    except (InvalidToken, Exception):
        return None