"""
Service 2FA (TOTP — Time-based One-Time Password).
Compatible Google Authenticator, Authy, Microsoft Authenticator, etc.
"""
import json
import secrets
from datetime import datetime, timezone

import pyotp
import qrcode
from io import BytesIO
import base64

from app.extensions import db
from app.utils.security import log_activity


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class TotpService:

    APP_NAME = "LionFlow AI"

    # ==================================================
    # GÉNÉRATION DU SECRET
    # ==================================================
    @staticmethod
    def generate_secret() -> str:
        """Génère un secret TOTP (base32)."""
        return pyotp.random_base32()

    # ==================================================
    # GÉNÉRATION DU QR CODE
    # ==================================================
    @staticmethod
    def generate_qr_code(user, secret: str) -> str:
        """
        Génère un QR code pour configurer l'app mobile.
        Retourne une image encodée en base64 (data URI).
        """
        uri = pyotp.totp.TOTP(secret).provisioning_uri(
            name=user.email,
            issuer_name=TotpService.APP_NAME,
        )

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=8,
            border=2,
        )
        qr.add_data(uri)
        qr.make(fit=True)

        img = qr.make_image(fill_color="#065f46", back_color="white")
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)

        img_b64 = base64.b64encode(buffer.getvalue()).decode()
        return f"data:image/png;base64,{img_b64}"

    # ==================================================
    # VÉRIFICATION D'UN CODE
    # ==================================================
    @staticmethod
    def verify_code(secret: str, code: str, valid_window: int = 1) -> bool:
        """
        Vérifie un code TOTP à 6 chiffres.
        valid_window=1 → tolère ±30 secondes de décalage.
        """
        if not secret or not code:
            return False
        code = str(code).strip().replace(" ", "")
        if len(code) != 6 or not code.isdigit():
            return False

        try:
            totp = pyotp.TOTP(secret)
            return totp.verify(code, valid_window=valid_window)
        except Exception:
            return False

    # ==================================================
    # ACTIVATION / DÉSACTIVATION
    # ==================================================
    @staticmethod
    def enable_for_user(user, secret: str, verification_code: str) -> tuple[bool, list, str]:
        """
        Active la 2FA pour un utilisateur.
        Retourne (success, backup_codes, error).
        """
        # Vérifier le code une dernière fois avant activation
        if not TotpService.verify_code(secret, verification_code):
            return False, [], "Code incorrect. Réessayez."

        # Générer les codes de secours (10 codes)
        backup_codes = [secrets.token_hex(4).upper() for _ in range(10)]
        hashed_codes = [
            __import__("hashlib").sha256(c.encode()).hexdigest()
            for c in backup_codes
        ]

        user.totp_secret = secret
        user.totp_enabled = True
        user.totp_backup_codes = json.dumps(hashed_codes)
        user.totp_confirmed_at = _utcnow()
        db.session.commit()

        log_activity(
            action="2fa_enabled",
            description=f"2FA activée pour {user.email}",
            user_id=user.id,
        )

        return True, backup_codes, ""

    @staticmethod
    def disable_for_user(user, password: str) -> tuple[bool, str]:
        """Désactive la 2FA (nécessite le mot de passe)."""
        if not user.check_password(password):
            return False, "Mot de passe incorrect."

        user.totp_secret = None
        user.totp_enabled = False
        user.totp_backup_codes = None
        user.totp_confirmed_at = None
        db.session.commit()

        log_activity(
            action="2fa_disabled",
            description=f"2FA désactivée pour {user.email}",
            user_id=user.id,
        )
        return True, ""

    # ==================================================
    # CODES DE SECOURS
    # ==================================================
    @staticmethod
    def verify_backup_code(user, code: str) -> bool:
        """
        Vérifie un code de secours.
        Si valide, le consomme (utilisable une seule fois).
        """
        if not user.totp_backup_codes or not code:
            return False

        code = str(code).strip().upper()
        try:
            hashed_codes = json.loads(user.totp_backup_codes)
        except Exception:
            return False

        hashed_input = __import__("hashlib").sha256(code.encode()).hexdigest()

        if hashed_input in hashed_codes:
            hashed_codes.remove(hashed_input)
            user.totp_backup_codes = json.dumps(hashed_codes)
            db.session.commit()

            log_activity(
                action="2fa_backup_used",
                description=f"Code de secours utilisé par {user.email}",
                user_id=user.id,
            )
            return True
        return False

    @staticmethod
    def regenerate_backup_codes(user) -> list:
        """Regénère les codes de secours."""
        if not user.totp_enabled:
            return []

        backup_codes = [secrets.token_hex(4).upper() for _ in range(10)]
        hashed_codes = [
            __import__("hashlib").sha256(c.encode()).hexdigest()
            for c in backup_codes
        ]
        user.totp_backup_codes = json.dumps(hashed_codes)
        db.session.commit()

        log_activity(
            action="2fa_backup_regenerated",
            description=f"Codes de secours regénérés pour {user.email}",
            user_id=user.id,
        )
        return backup_codes

    @staticmethod
    def remaining_backup_codes(user) -> int:
        """Retourne le nombre de codes de secours restants."""
        if not user.totp_backup_codes:
            return 0
        try:
            return len(json.loads(user.totp_backup_codes))
        except Exception:
            return 0