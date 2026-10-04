"""
Service de notifications push PWA.
Utilise pywebpush pour envoyer des notifications natives.
"""
import json

from flask import current_app

from app.extensions import db
from app.models.push_subscription import PushSubscription


class PushService:

    # ==================================================
    # ENVOI À UN UTILISATEUR
    # ==================================================
    @staticmethod
    def send_to_user(user_id: int, title: str, body: str,
                     url: str = "/", icon: str = "/static/images/icon-192x192.png") -> int:
        """Envoie une notification à tous les appareils d'un utilisateur."""
        subscriptions = PushSubscription.query.filter_by(
            user_id=user_id, is_active=True
        ).all()

        if not subscriptions:
            return 0

        payload = {
            "title": title,
            "body": body,
            "url": url,
            "icon": icon,
            "badge": "/static/images/icon-96x96.png",
        }

        sent = 0
        for sub in subscriptions:
            if PushService._send_one(sub, payload):
                sent += 1

        return sent

    # ==================================================
    # ENVOI À UN APPAREIL
    # ==================================================
    @staticmethod
    def _send_one(subscription: PushSubscription, payload: dict) -> bool:
        """Envoie une notification à un appareil spécifique."""
        try:
            from pywebpush import webpush, WebPushException
        except ImportError:
            current_app.logger.warning("[Push] pywebpush non installé")
            return False

        vapid_private = current_app.config.get("VAPID_PRIVATE_KEY")
        vapid_email = current_app.config.get("VAPID_CLAIMS_EMAIL", "mailto:admin@lionflow.ai")

        if not vapid_private:
            current_app.logger.warning("[Push] VAPID_PRIVATE_KEY non configuré")
            return False

        sub_info = {
            "endpoint": subscription.endpoint,
            "keys": {
                "p256dh": subscription.p256dh,
                "auth": subscription.auth,
            },
        }

        try:
            webpush(
                subscription_info=sub_info,
                data=json.dumps(payload),
                vapid_private_key=vapid_private,
                vapid_claims={"sub": vapid_email},
            )
            subscription.last_used_at = __import__(
                "datetime"
            ).datetime.now(__import__("datetime").timezone.utc).replace(tzinfo=None)
            db.session.commit()
            return True

        except WebPushException as e:
            # Si l'abonnement est expiré (410, 404), on le désactive
            status = getattr(e.response, "status_code", None)
            if status in (404, 410):
                subscription.is_active = False
                db.session.commit()
                current_app.logger.info(
                    f"[Push] Abonnement expiré désactivé (user={subscription.user_id})"
                )
            else:
                current_app.logger.warning(f"[Push] Erreur d'envoi : {e}")
            return False

        except Exception as e:
            current_app.logger.exception(f"[Push] Erreur inattendue : {e}")
            return False

    # ==================================================
    # ABONNEMENT
    # ==================================================
    @staticmethod
    def subscribe(user_id: int, subscription_data: dict, user_agent: str = "") -> PushSubscription:
        """Crée ou met à jour un abonnement push."""
        endpoint = subscription_data.get("endpoint")
        keys = subscription_data.get("keys", {})
        p256dh = keys.get("p256dh")
        auth = keys.get("auth")

        if not all([endpoint, p256dh, auth]):
            raise ValueError("Données d'abonnement incomplètes.")

        # Chercher un abonnement existant avec le même endpoint
        existing = PushSubscription.query.filter_by(endpoint=endpoint).first()
        if existing:
            existing.user_id = user_id
            existing.p256dh = p256dh
            existing.auth = auth
            existing.user_agent = (user_agent or "")[:255]
            existing.is_active = True
            db.session.commit()
            return existing

        sub = PushSubscription(
            user_id=user_id,
            endpoint=endpoint,
            p256dh=p256dh,
            auth=auth,
            user_agent=(user_agent or "")[:255],
            is_active=True,
        )
        db.session.add(sub)
        db.session.commit()
        return sub

    @staticmethod
    def unsubscribe(user_id: int, endpoint: str) -> bool:
        """Désabonne un appareil."""
        sub = PushSubscription.query.filter_by(
            user_id=user_id, endpoint=endpoint
        ).first()
        if not sub:
            return False
        db.session.delete(sub)
        db.session.commit()
        return True