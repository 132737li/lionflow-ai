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
        attachments: list = None,
    ) -> bool:
        """Envoie un email. Retourne True si succès, False sinon."""
        if not to:
            current_app.logger.warning("[Email] Destinataire vide")
            return False

        if not current_app.config.get("MAIL_USERNAME"):
            current_app.logger.warning(
                "[Email] MAIL_USERNAME non configure - email non envoye"
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
            
            # Gestion des pièces jointes
            if attachments:
                for att in attachments:
                    msg.attach(
                        filename=att.get("filename", "document.pdf"),
                        content_type=att.get("content_type", "application/pdf"),
                        data=att.get("data", b""),
                    )

            mail.send(msg)
            # Log sans emoji pour eviter les crashs cp1252 sur Windows
            current_app.logger.info(f"[Email] Envoye a {to} : {subject}")
            return True
        except Exception as e:
            current_app.logger.exception(f"[Email] Erreur d'envoi a {to} : {e}")
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
        def send_verification_email(user, token: str) -> bool:
            """Envoie le lien de vérification d'adresse email."""
            subject = "🦁 Confirmez votre adresse email — LionFlow AI"
            verify_url = f"{current_app.config.get('APP_BASE_URL', 'http://localhost:5000')}/auth/verify-email/{token}"
            
            html = render_template(
                "emails/verify_email.html",
                user=user,
                verify_url=verify_url,
                app_name=current_app.config.get("APP_NAME", "LionFlow AI"),
            )
            text = f"""
    Bonjour {user.full_name},

    Merci de vous être inscrit sur LionFlow AI !

    Pour activer votre compte et commencer à utiliser la plateforme, veuillez cliquer sur le lien ci-dessous :
    {verify_url}

    Ce lien est valable pendant 24 heures.

    —
    L'équipe LionFlow AI
    """
            return EmailService.send_email(to=user.email, subject=subject, html_body=html, text_body=text)

    @staticmethod
    def send_welcome(user) -> bool:
        """Envoie un email de bienvenue après inscription."""
        if not getattr(user, "email_notifications_enabled", True):
            return False

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

    # ==================================================
    # CAMPAGNES & QUOTAS
    # ==================================================
    @staticmethod
    def send_campaign_completed(campaign, pdf_bytes: bytes = None) -> bool:
        """Envoie un rapport de fin de campagne avec PDF optionnel."""
        owner = getattr(campaign.business, "owner", None)
        if not owner or not getattr(owner, "email_notifications_enabled", True):
            return False

        subject = f"✅ Campagne terminée : {campaign.name}"
        html = render_template(
            "emails/campaign_completed.html",
            campaign=campaign,
            business=campaign.business,
            user=owner,
            app_name=current_app.config.get("APP_NAME", "LionFlow AI"),
            dashboard_url=current_app.config.get("APP_BASE_URL", "http://localhost:5000") + f"/campaigns/{campaign.id}",
        )
        
        attachments = []
        if pdf_bytes:
            attachments.append({
                "filename": f"campagne_{campaign.id}.pdf",
                "content_type": "application/pdf",
                "data": pdf_bytes,
            })

        text = f"""
Bonjour {owner.full_name},

La campagne « {campaign.name} » vient de se terminer.

Bilan :
- Envoyés : {campaign.sent_count}
- Livrés : {campaign.delivered_count}
- Lus : {campaign.read_count}
- Échecs : {campaign.failed_count}

Consultez le rapport sur : {current_app.config.get('APP_BASE_URL', 'http://localhost:5000')}/campaigns/{campaign.id}
"""
        return EmailService.send_email(
            to=owner.email, subject=subject, html_body=html, text_body=text,
            attachments=attachments
        )

    @staticmethod
    def send_quota_warning(business, used: int, limit: int) -> bool:
        """Alerte le propriétaire quand le quota de contacts approche de la limite."""
        owner = getattr(business, "owner", None)
        if not owner or not getattr(owner, "email_notifications_enabled", True):
            return False

        pct = round((used / limit) * 100) if limit > 0 else 100
        subject = f"⚠️ Quota de contacts à {pct}% — {business.name}"
        
        html = render_template(
            "emails/quota_warning.html",
            business=business,
            user=owner,
            used=used,
            limit=limit,
            pct=pct,
            app_name=current_app.config.get("APP_NAME", "LionFlow AI"),
            upgrade_url=current_app.config.get("APP_BASE_URL", "http://localhost:5000") + "/subscriptions/current",
        )
        text = f"""
Bonjour {owner.full_name},

Votre entreprise {business.name} a utilisé {used} contacts sur les {limit} autorisés par votre plan.

Pensez à passer à un plan supérieur pour continuer à ajouter des contacts :
{current_app.config.get('APP_BASE_URL', 'http://localhost:5000')}/subscriptions/current
"""
        return EmailService.send_email(to=owner.email, subject=subject, html_body=html, text_body=text)

    # ==================================================
    # MISES À JOUR
    # ==================================================
    @staticmethod
    def send_update_notification(
        user, 
        title: str, 
        message: str, 
        cta_text: str = "Découvrir", 
        cta_url: str = None
    ) -> bool:
        """Envoie un email d'annonce de mise à jour / nouveauté."""
        if not getattr(user, "email_notifications_enabled", True):
            return False

        subject = f"🚀 Nouveauté sur LionFlow AI : {title}"
        
        if not cta_url:
            cta_url = current_app.config.get('APP_BASE_URL', 'http://localhost:5000')

        html = render_template(
            "emails/update_notification.html",
            user=user,
            title=title,
            message=message,
            cta_text=cta_text,
            cta_url=cta_url,
            app_name=current_app.config.get("APP_NAME", "LionFlow AI"),
        )
        
        text = f"""
Bonjour {user.full_name},

Nouveauté sur LionFlow AI : {title}

{message}

Découvrez-la ici : {cta_url}

—
L'équipe LionFlow AI
"""
        return EmailService.send_email(to=user.email, subject=subject, html_body=html, text_body=text)