"""
Service d'authentification.
Centralise la logique métier : inscription, login, reset, change password.
Réutilisable par les routes UI et les routes API.
"""
import hashlib
import secrets
from datetime import datetime, timezone, timedelta

from flask import current_app
from app.extensions import db
from app.models.user import User
from app.models.notification import Notification
from app.utils.security import log_activity


def _utcnow():
    """Heure UTC naïve (compatible MySQL DATETIME)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class AuthError(Exception):
    """Erreur métier d'authentification."""
    def __init__(self, message: str, code: int = 400):
        super().__init__(message)
        self.message = message
        self.code = code


RESET_TOKEN_TTL_MINUTES = 60


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


class AuthService:

    # ==================================================
    # INSCRIPTION
    # ==================================================
    @staticmethod
    def register(data: dict, ip: str | None = None) -> User:
        email = (data.get("email") or "").strip().lower()
        if not email:
            raise AuthError("Email obligatoire.", 400)
        if User.query.filter_by(email=email).first():
            raise AuthError("Cet email est déjà utilisé.", 409)

        user = User(
            email=email,
            first_name=(data.get("first_name") or "").strip() or None,
            last_name=(data.get("last_name") or "").strip() or None,
            role="user",
            is_active=True,
            is_verified=False,
        )
        user.set_password(data.get("password") or "")
        db.session.add(user)
        db.session.flush()

        # Notification interne
        notif = Notification(
            user_id=user.id,
            title="Bienvenue sur LionFlow AI 🦁",
            message=(
                "Votre compte a été créé avec succès. "
                "Commencez par créer votre entreprise et importer vos contacts."
            ),
            type="success",
        )
        db.session.add(notif)
        db.session.commit()

        log_activity(
            action="register",
            description=f"Nouvel utilisateur inscrit : {user.email}",
            user_id=user.id,
        )

        # Email de bienvenue (non bloquant)
        try:
            from app.services.email_service import EmailService
            EmailService.send_welcome(user)
        except Exception:
            current_app.logger.exception("Erreur envoi email de bienvenue")

        return user

    # ==================================================
    # CONNEXION
    # ==================================================
    @staticmethod
    def authenticate(email: str, password: str) -> User:
        email = (email or "").strip().lower()
        user = User.query.filter_by(email=email).first()

        if not user or not user.check_password(password or ""):
            raise AuthError("Email ou mot de passe incorrect.", 401)

        if not user.is_active:
            raise AuthError("Votre compte est désactivé.", 403)

        user.last_login_at = _utcnow()
        db.session.commit()

        log_activity(
            action="login",
            description=f"Connexion réussie : {user.email}",
            user_id=user.id,
        )
        return user

    # ==================================================
    # DÉCONNEXION
    # ==================================================
    @staticmethod
    def log_logout(user: User | None) -> None:
        if user and getattr(user, "is_authenticated", False):
            log_activity(
                action="logout",
                description=f"Déconnexion : {user.email}",
                user_id=user.id,
            )

    # ==================================================
    # MOT DE PASSE OUBLIÉ
    # ==================================================
    @staticmethod
    def create_reset_token(email: str):
        email = (email or "").strip().lower()
        user = User.query.filter_by(email=email).first()
        if not user:
            return None, None

        raw = secrets.token_urlsafe(32)
        user.reset_token = _hash_token(raw)
        user.reset_token_exp = _utcnow() + timedelta(minutes=RESET_TOKEN_TTL_MINUTES)
        db.session.commit()

        log_activity(
            action="password_reset_request",
            description=f"Demande de reset MDP : {user.email}",
            user_id=user.id,
        )
        return user, raw

    @staticmethod
    def validate_reset_token(raw_token: str):
        if not raw_token:
            return None
        hashed = _hash_token(raw_token)
        user = User.query.filter_by(reset_token=hashed).first()
        if not user:
            return None
        if not user.reset_token_exp:
            return None
        if user.reset_token_exp < _utcnow():
            return None
        return user

    @staticmethod
    def reset_password(raw_token: str, new_password: str) -> User:
        user = AuthService.validate_reset_token(raw_token)
        if not user:
            raise AuthError("Lien invalide ou expiré.", 400)

        user.set_password(new_password)
        user.reset_token = None
        user.reset_token_exp = None
        db.session.commit()

        notif = Notification(
            user_id=user.id,
            title="Mot de passe réinitialisé",
            message="Votre mot de passe a été modifié avec succès.",
            type="success",
        )
        db.session.add(notif)
        db.session.commit()

        log_activity(
            action="password_reset_done",
            description=f"MDP réinitialisé : {user.email}",
            user_id=user.id,
        )
        return user

    # ==================================================
    # CHANGEMENT DE MOT DE PASSE (connecté)
    # ==================================================
    @staticmethod
    def change_password(user: User, current: str, new: str) -> None:
        if not user.check_password(current or ""):
            raise AuthError("Mot de passe actuel incorrect.", 400)
        if not new or len(new) < 8:
            raise AuthError("Le nouveau mot de passe doit contenir au moins 8 caractères.", 400)
        if user.check_password(new):
            raise AuthError("Le nouveau mot de passe doit être différent de l'ancien.", 400)

        user.set_password(new)
        db.session.commit()

        notif = Notification(
            user_id=user.id,
            title="Mot de passe modifié",
            message="Votre mot de passe a été modifié avec succès.",
            type="success",
        )
        db.session.add(notif)
        db.session.commit()

        log_activity(
            action="password_change",
            description=f"MDP modifié : {user.email}",
            user_id=user.id,
        )

    # ==================================================
    # ENVOI D'EMAIL DE RESET
    # ==================================================
    @staticmethod
    def send_reset_email(user: User, raw_token: str) -> str:
        """
        Envoie le lien de reset par email.
        Utilise APP_BASE_URL pour construire l'URL publique
        (fonctionne avec ngrok, domaine de production, etc.).
        """
        from app.services.email_service import EmailService

        # ✅ Utiliser APP_BASE_URL au lieu du host de la requête
        base_url = current_app.config.get(
            "APP_BASE_URL", "http://localhost:5000"
        ).rstrip("/")
        reset_url = f"{base_url}/auth/reset-password/{raw_token}"

        # Envoyer par email
        sent = EmailService.send_password_reset(user, reset_url)

        if sent:
            current_app.logger.info(
                f"[LionFlow] Email de reset envoye a {user.email} — {reset_url}"
            )
        else:
            current_app.logger.warning(
                f"[LionFlow] Echec envoi a {user.email}. "
                f"URL de fallback : {reset_url}"
            )

        return reset_url