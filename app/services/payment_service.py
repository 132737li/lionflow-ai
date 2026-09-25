"""
Service de paiement — abstraction du fournisseur.

Fournit :
- Une interface PaymentProvider (create_checkout, verify_webhook)
- Une implémentation StripeProvider (mode test OK)
- Une implémentation DevProvider (simulateur local sans clé Stripe)
"""
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from flask import current_app, url_for

from app.extensions import db
from app.models.payment import Payment
from app.models.subscription import Subscription
from app.services.notification_service import NotificationService


def _utcnow():
    """Heure UTC naïve (compatible MySQL DATETIME)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass
class CheckoutResult:
    success: bool
    checkout_url: str | None = None
    external_id: str | None = None
    error: str | None = None


class PaymentProvider:
    """Interface de base pour tout fournisseur de paiement."""

    name = "base"

    def create_checkout(
        self, business, plan_key: str, success_url: str, cancel_url: str,
    ) -> CheckoutResult:
        raise NotImplementedError

    def verify_webhook(self, payload: bytes, signature: str) -> dict:
        raise NotImplementedError


class DevPaymentProvider(PaymentProvider):
    """Simulateur local : marque immédiatement le paiement comme réussi."""

    name = "dev"

    def create_checkout(
        self, business, plan_key: str, success_url: str, cancel_url: str,
    ) -> CheckoutResult:
        plan = current_app.config["PLANS"].get(plan_key)
        if not plan:
            return CheckoutResult(False, error="Plan inconnu.")

        payment = Payment(
            business_id=business.id,
            provider=self.name,
            amount_cents=int(plan["price_eur"] * 100),
            currency="EUR",
            status="pending",
            external_id=f"dev_{uuid.uuid4().hex[:16]}",
        )
        db.session.add(payment)
        db.session.commit()

        checkout_url = url_for(
            "payments.dev_simulate",
            payment_id=payment.id,
            plan=plan_key,
            _external=True,
        )
        return CheckoutResult(True, checkout_url=checkout_url,
                              external_id=payment.external_id)

    def verify_webhook(self, payload: bytes, signature: str) -> dict:
        return {"type": "noop"}


class StripePaymentProvider(PaymentProvider):
    """Intégration Stripe Checkout. Nécessite STRIPE_SECRET_KEY."""

    name = "stripe"

    def __init__(self):
        try:
            import stripe
        except ImportError:
            raise RuntimeError("Le paquet 'stripe' n'est pas installé.")
        self.stripe = stripe
        self.stripe.api_key = current_app.config.get("STRIPE_SECRET_KEY")
        if not self.stripe.api_key:
            raise RuntimeError("STRIPE_SECRET_KEY non configuré.")

    def create_checkout(
        self, business, plan_key: str, success_url: str, cancel_url: str,
    ) -> CheckoutResult:
        plan = current_app.config["PLANS"].get(plan_key)
        if not plan:
            return CheckoutResult(False, error="Plan inconnu.")
        if plan["price_eur"] <= 0:
            return CheckoutResult(False, error="Ce plan est gratuit.")

        try:
            session = self.stripe.checkout.Session.create(
                mode="subscription",
                line_items=[{
                    "price_data": {
                        "currency": "eur",
                        "unit_amount": int(plan["price_eur"] * 100),
                        "recurring": {"interval": "month"},
                        "product_data": {
                            "name": f"LionFlow AI — Plan {plan['label']}",
                            "description": "Abonnement mensuel LionFlow AI",
                        },
                    },
                    "quantity": 1,
                }],
                customer_email=business.email or None,
                success_url=success_url + "?session_id={CHECKOUT_SESSION_ID}",
                cancel_url=cancel_url,
                metadata={
                    "business_id": str(business.id),
                    "plan": plan_key,
                },
            )

            payment = Payment(
                business_id=business.id,
                provider=self.name,
                amount_cents=int(plan["price_eur"] * 100),
                currency="EUR",
                status="pending",
                external_id=session.id,
            )
            db.session.add(payment)
            db.session.commit()

            return CheckoutResult(True, checkout_url=session.url,
                                  external_id=session.id)
        except Exception as e:
            current_app.logger.exception("Erreur Stripe checkout")
            return CheckoutResult(False, error=str(e)[:500])

    def verify_webhook(self, payload: bytes, signature: str) -> dict:
        secret = current_app.config.get("STRIPE_WEBHOOK_SECRET")
        if not secret:
            raise RuntimeError("STRIPE_WEBHOOK_SECRET non configuré.")
        try:
            event = self.stripe.Webhook.construct_event(payload, signature, secret)
            return event
        except Exception as e:
            raise RuntimeError(f"Signature invalide : {e}")


def get_provider() -> PaymentProvider:
    """
    Retourne le provider approprié :
    - Stripe si STRIPE_SECRET_KEY est présent
    - Dev sinon
    """
    if current_app.config.get("STRIPE_SECRET_KEY"):
        try:
            return StripePaymentProvider()
        except Exception as e:
            current_app.logger.warning(
                f"Stripe indisponible ({e}), bascule sur Dev."
            )
    return DevPaymentProvider()


class PaymentService:

    @staticmethod
    def activate_subscription(business, plan_key: str, payment_id: int | None = None) -> Subscription:
        """
        Active un abonnement pour l'entreprise :
        - Annule l'abonnement actif
        - Crée un nouvel abonnement
        - Marque le paiement comme réussi
        - Envoie une notification
        """
        Subscription.query.filter_by(
            business_id=business.id, status="active"
        ).update({"status": "cancelled"})

        plan = current_app.config["PLANS"].get(plan_key, {})
        sub = Subscription(
            business_id=business.id,
            plan=plan_key,
            status="active",
            started_at=_utcnow(),
        )
        if plan_key != "free":
            sub.extend(30)
        db.session.add(sub)
        db.session.flush()

        if payment_id:
            p = db.session.get(Payment, payment_id)
            if p:
                p.status = "succeeded"
                p.subscription_id = sub.id

        db.session.commit()

        NotificationService.notify(
            user_id=business.owner_id,
            title=f"Abonnement {plan.get('label', plan_key)} activé",
            message=(
                f"Votre abonnement LionFlow AI est passé au plan "
                f"{plan.get('label', plan_key)}. Merci !"
            ),
            type="success",
            link="/subscriptions/",
        )
        return sub