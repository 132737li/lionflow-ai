"""
Validateurs réutilisables : email, téléphone, uploads, etc.
Pays par défaut : Burundi (+257). Tous les pays sont acceptés.
"""
import os
import re
import phonenumbers
from werkzeug.utils import secure_filename

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$")

# 🌍 Région par défaut pour la validation des numéros (Burundi)
DEFAULT_PHONE_REGION = "BI"  # Burundi


def is_valid_email(email: str) -> bool:
    return bool(email and EMAIL_RE.match(email.strip()))


def normalize_phone(phone: str, default_region: str = DEFAULT_PHONE_REGION) -> str | None:
    """
    Normalise un numéro au format E.164 (ex: +257XXXXXXXX).
    - Si le numéro contient un indicatif international (+XX), il est respecté.
    - Sinon, il est interprété selon `default_region` (Burundi par défaut).
    Retourne None si invalide.
    """
    if not phone:
        return None
    try:
        parsed = phonenumbers.parse(str(phone).strip(), default_region)
        if not phonenumbers.is_valid_number(parsed):
            return None
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        return None


def allowed_file(filename: str, allowed_exts: set[str]) -> bool:
    if "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in allowed_exts


def safe_filename(filename: str) -> str:
    return secure_filename(filename or "file")


def validate_required(data: dict, fields: list[str]) -> list[str]:
    """Retourne la liste des champs manquants/vides."""
    errors = []
    for f in fields:
        v = data.get(f)
        if v is None or (isinstance(v, str) and not v.strip()):
            errors.append(f"Le champ '{f}' est obligatoire.")
    return errors


def validate_password_strength(password: str) -> list[str]:
    """Règles minimales : >=8 caractères, une lettre, un chiffre."""
    errors = []
    if not password or len(password) < 8:
        errors.append("Le mot de passe doit contenir au moins 8 caractères.")
    if password and not re.search(r"[A-Za-z]", password):
        errors.append("Le mot de passe doit contenir au moins une lettre.")
    if password and not re.search(r"\d", password):
        errors.append("Le mot de passe doit contenir au moins un chiffre.")
    return errors