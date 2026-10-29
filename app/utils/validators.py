"""
Validateurs et utilitaires de normalisation.
"""
import re
import phonenumbers
from phonenumbers import NumberParseException


# ==================================================
# VALIDATION DES NUMÉROS DE TÉLÉPHONE
# ==================================================
def normalize_phone(phone_number: str, default_region: str = "BI") -> str | None:
    """
    Normalise un numéro de téléphone au format E.164 (+257...).
    
    Règles :
    - Si le numéro commence par '+', il est considéré comme international.
      On le valide tel quel, quel que soit le pays sélectionné.
    - Si le numéro ne commence pas par '+', on utilise `default_region` (BI par défaut)
      pour lui ajouter l'indicatif.
    """
    if not phone_number:
        return None
        
    # Nettoie la chaîne (garde les chiffres et le +)
    phone_str = str(phone_number).strip()
    phone_str = re.sub(r'[^\d+]', '', phone_str)
    
    if not phone_str:
        return None

    try:
        if phone_str.startswith("+"):
            # --- CAS 1 : Numéro international explicite ---
            parsed = phonenumbers.parse(phone_str, None)
            
            # On accepte le numéro s'il est valide OU possible (tolérance pour les nouveaux préfixes)
            if phonenumbers.is_valid_number(parsed) or phonenumbers.is_possible_number(parsed):
                return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
            
            # Fallback ultime : si ça ressemble à un numéro international (8 à 15 chiffres)
            digits_only = phone_str[1:]
            if 8 <= len(digits_only) <= 15:
                return phone_str
                
            return None

        else:
            # --- CAS 2 : Numéro local (sans +) ---
            # On utilise le pays par défaut (ex: "BI" pour le Burundi)
            parsed = phonenumbers.parse(phone_str, default_region)
            
            if phonenumbers.is_possible_number(parsed):
                return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
            
            return None

    except NumberParseException:
        return None


# ==================================================
# VALIDATION EMAIL
# ==================================================
def is_valid_email(email: str) -> bool:
    """Validation basique d'email."""
    if not email:
        return False
    regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(regex, email) is not None


# ==================================================
# VALIDATION FICHIERS
# ==================================================
def allowed_file(filename: str, allowed_extensions: set) -> bool:
    """Vérifie si l'extension du fichier est autorisée."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions


# ==================================================
# AUTRES VALIDATEURS (API)
# ==================================================
def validate_required(data: dict, fields: list) -> list:
    """
    Vérifie que les champs requis sont présents et non vides.
    Retourne une liste d'erreurs (vide si tout est bon).
    """
    errors = []
    for field in fields:
        if field not in data or data[field] is None or str(data[field]).strip() == "":
            errors.append(f"Le champ '{field}' est requis.")
    return errors


def validate_password_strength(password: str) -> list:
    """
    Vérifie la force du mot de passe.
    Retourne une liste d'erreurs (vide si le mot de passe est fort).
    """
    errors = []
    if len(password) < 8:
        errors.append("Le mot de passe doit contenir au moins 8 caractères.")
    if not re.search(r"[A-Z]", password):
        errors.append("Le mot de passe doit contenir au moins une majuscule.")
    if not re.search(r"[a-z]", password):
        errors.append("Le mot de passe doit contenir au moins une minuscule.")
    if not re.search(r"\d", password):
        errors.append("Le mot de passe doit contenir au moins un chiffre.")
    return errors