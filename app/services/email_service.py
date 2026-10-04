"""
Service d'envoi d'emails.
Utilise Flask-Mail pour envoyer de vrais emails via Gmail SMTP.
"""
from flask import current_app, render_template
from flask_mail import Message

from app.extensions import mail


class EmailService:
    """Service d'envoi d'emails transactionnels."""

    @staticmethod
    def send_email(
        to: str,
        subject: str,
        html_body: str = None,
        text_body: str = None,
        reply_to: str = None,
    ) -> bool:
        """Envoie un email. Retourne True si succès, False sinon."""
        if not to:
            current_app.logger.warning("[Email] Destinataire vide")
            return False

        if not current_app.config.get("MAIL_USERNAME"):
            current_app.logger.warning(
                "[Email] MAIL_USERNAME non configuré — email non envoyé"
            )
            return False

        try:
            msg = Message(
                subject=subject,
                recipients=[to],
                html=html_body,
                body=text_body or (html_body[:500] if html_body else ""),
                reply_to=reply_to,
            )
            mail.send(msg)
            current_app.logger.info(f"[Email] ✅ Envoyé à {to} : {subject}")
            return True
        except Exception as e:
            current_app.logger.exception(f"[Email] ❌ Erreur d'envoi à {to} : {e}")
            return False

    # ==================================================
    # EMAILS PRÉDÉFINIS
    # ==================================================
    @staticmethod
    def send_password_reset(user, reset_url: str) -> bool:
        """Envoie le lien de réinitialisation de mot de passe."""
        subject = "🔐 Réinitialisation de votre mot de passe — LionFlow AI"
        html = render_template(
            "emails/password_reset.html",
            user=user,
            reset_url=reset_url,
            app_name=current_app.config.get("APP_NAME", "LionFlow AI"),
        )
        text = f"""
Bonjour {user.full_name},

Vous avez demandé à réinitialiser votre mot de passe sur LionFlow AI.

Cliquez sur ce lien pour définir un nouveau mot de passe :
{reset_url}

Ce lien est valable pendant 1 heure.

Si vous n'êtes pas à l'origine de cette demande, ignorez cet email.

—
L'équipe LionFlow AI
"""
        return EmailService.send_email(to=user.email, subject=subject,
                                       html_body=html, text_body=text)

    @staticmethod
    def send_welcome(user) -> bool:
        """Envoie un email de bienvenue après inscription."""
        subject = "🦁 Bienvenue sur LionFlow AI !"
        html = render_template(
            "emails/welcome.html",
            user=user,
            app_name=current_app.config.get("APP_NAME", "LionFlow AI"),
        )
        text = f"""
Bonjour {user.full_name},

Bienvenue sur LionFlow AI ! 🦁

Votre compte a été créé avec succès.

Pour commencer :
1. Créez votre entreprise
2. Importez vos contacts
3. Lancez votre première campagne WhatsApp

Connectez-vous : {current_app.config.get('APP_BASE_URL', 'http://localhost:5000')}/auth/login

—
L'équipe LionFlow AI
"""
        return EmailService.send_email(to=user.email, subject=subject,
                                       html_body=html, text_body=text)

    @staticmethod
    def send_subscription_activated(user, plan_label: str, amount: str) -> bool:
        """Notifie l'utilisateur de l'activation d'un abonnement."""
        subject = f"✅ Abonnement {plan_label} activé — LionFlow AI"
        html = render_template(
            "emails/subscription_activated.html",
            user=user,
            plan_label=plan_label,
            amount=amount,
            app_name=current_app.config.get("APP_NAME", "LionFlow AI"),
        )
        text = f"""
Bonjour {user.full_name},

Votre abonnement {plan_label} a été activé avec succès !

Montant : {amount}

Merci pour votre confiance.

—
L'équipe LionFlow AI
"""
        return EmailService.send_email(to=user.email, subject=subject,
                                       html_body=html, text_body=text)

    @staticmethod
    def send_payment_failed(user, plan_label: str) -> bool:
        """Notifie l'utilisateur d'un échec de paiement."""
        subject = "⚠️ Échec de paiement — LionFlow AI"
        text = f"""
Bonjour {user.full_name},

Nous n'avons pas pu traiter votre paiement pour l'abonnement {plan_label}.

Merci de vérifier vos informations de paiement et de réessayer.

—
L'équipe LionFlow AI
"""
        return EmailService.send_email(to=user.email, subject=subject,
                                       text_body=text)

    @staticmethod
    def test_connection() -> dict:
        """Teste la configuration SMTP."""
        if not current_app.config.get("MAIL_USERNAME"):
            return {"success": False, "error": "MAIL_USERNAME non configuré"}

        try:
            to = current_app.config.get("MAIL_USERNAME")
            msg = Message(
                subject="🧪 Test LionFlow AI",
                recipients=[to],
                body="Ceci est un test de configuration SMTP. Si vous recevez cet email, la configuration fonctionne !",
            )
            mail.send(msg)
            return {"success": True, "message": f"Email de test envoyé à {to}"}
        except Exception as e:
            return {"success": False, "error": str(e)}