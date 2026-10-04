"""
Service de paiement — architecture multi-provider.

Chaque provider est une classe qui implémente :
  - create_payment_url() : génère une URL de paiement
  - verify_payment() : vérifie qu'un paiement est validé (via API ou webhook)

Le provider actif est déterminé par la variable PAYMENT_PROVIDER dans .env.
Providers disponibles :
  - "generic"   : provider générique (URL de paiement externe + webhook)
  - "bancobu"   : Bancobu eNoti / BurundiPay (à configurer)
  - "paydunya"  : PayDunya (à configurer)
  - "stripe"    : Stripe (utile pour tester à l'international)
"""
import uuid
import hmac
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone

from flask import current_app, url_for

from app.extensions import db
from app.models.payment import Payment
from app.models.subscription import Subscription
from app.services.notification_service import NotificationService


def _utcnow():
    """Heure UTC naïve."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ==================================================
# RÉSULTAT DE PAIEMENT
# ==================================================
@dataclass
class PaymentInitResult:
    """Résultat de l'initiation d'un paiement."""
    success: bool
    payment_url: str | None = None       # URL de paiement à ouvrir
    external_id: str | None = None       # ID chez le provider
    instructions: str | None = None      # Instructions texte (ex: "Composez *161#")
    error: str | None = None


# ==================================================
# INTERFACE DE BASE
# ==================================================
class PaymentProvider:
    """Interface que tout provider doit implémenter."""

    name = "base"
    display_name = "Paiement"

    def create_payment(
        self, business, plan_key: str, plan: dict,
        success_url: str, cancel_url: str, notify_url: str,
    ) -> PaymentInitResult:
        """Initie un paiement et retourne une URL ou des instructions."""
        raise NotImplementedError

    def verify_webhook(self, payload: bytes, signature: str, headers: dict) -> dict:
        """Vérifie la signature d'un webhook et retourne l'événement."""
        raise NotImplementedError

    def extract_webhook_data(self, event: dict) -> dict:
        """
        Extrait les données utiles d'un webhook :
        {
            "external_id": str,     # ID du paiement chez le provider
            "status": str,          # "success" | "failed" | "pending"
            "business_id": int,     # optionnel
            "plan_key": str,        # optionnel
        }
        """
        raise NotImplementedError


# ==================================================
# PROVIDER GÉNÉRIQUE (Bancobu, PayDunya, Lumicash, etc.)
# ==================================================
class GenericPaymentProvider(PaymentProvider):
    """
    Provider générique qui fonctionne avec n'importe quelle API de paiement
    exposant une URL de paiement et un webhook de confirmation.

    Configuration dans .env :
        PAYMENT_API_URL=https://api.mon-provider.bi/pay
        PAYMENT_API_KEY=ma_cle_secrete
        PAYMENT_WEBHOOK_SECRET=mon_secret_webhook
        PAYMENT_SUCCESS_URL=https://mon-provider.bi/pay/{payment_id}
    """

    name = "generic"
    display_name = "Paiement Mobile"

    def __init__(self):
        self.api_url = current_app.config.get("PAYMENT_API_URL")
        self.api_key = current_app.config.get("PAYMENT_API_KEY")
        self.webhook_secret = current_app.config.get("PAYMENT_WEBHOOK_SECRET")
        self.payment_url_template = current_app.config.get("PAYMENT_SUCCESS_URL")

    def create_payment(
        self, business, plan_key: str, plan: dict,
        success_url: str, cancel_url: str, notify_url: str,
    ) -> PaymentInitResult:
        """Crée un paiement côté provider via son API."""
        import requests

        if not self.api_url or not self.api_key:
            return PaymentInitResult(
                success=False,
                error=(
                    "Le paiement n'est pas encore configuré. "
                    "Contactez l'administrateur de LionFlow AI."
                ),
            )

        # Créer un Payment en attente dans notre base
        reference = f"LF-{uuid.uuid4().hex[:16].upper()}"
        payment = Payment(
            business_id=business.id,
            provider=self.name,
            amount_cents=int(plan["price_eur"] * 100),
            currency="BIF",  # Franc burundais
            status="pending",
            external_id=reference,
        )
        db.session.add(payment)
        db.session.commit()

        # Appeler l'API du provider
        try:
            payload = {
                "amount": payment.amount_cents,
                "currency": payment.currency,
                "reference": reference,
                "description": f"Abonnement LionFlow AI — Plan {plan['label']}",
                "customer_email": business.email or "",
                "customer_name": business.name,
                "notify_url": notify_url,
                "return_url": success_url,
            }
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            resp = requests.post(
                self.api_url, json=payload, headers=headers, timeout=15,
            )

            if resp.status_code in (200, 201):
                data = resp.json()
                payment_url = (
                    data.get("payment_url")
                    or data.get("checkout_url")
                    or (self.payment_url_template or "").format(
                        reference=reference,
                        amount=payment.amount_cents,
                    )
                )
                return PaymentInitResult(
                    success=True,
                    payment_url=payment_url,
                    external_id=reference,
                )
            else:
                error = resp.text[:300] if resp.text else f"HTTP {resp.status_code}"
                return PaymentInitResult(success=False, error=error)

        except requests.RequestException as e:
            current_app.logger.exception("Erreur API paiement")
            return PaymentInitResult(success=False, error=str(e)[:300])

    def verify_webhook(self, payload: bytes, signature: str, headers: dict) -> dict:
        """Vérifie la signature HMAC SHA256 du webhook."""
        if not self.webhook_secret:
            raise RuntimeError("PAYMENT_WEBHOOK_SECRET non configuré.")

        expected = hmac.new(
            self.webhook_secret.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()

        # Le provider peut envoyer la signature dans différents formats
        provided = (
            signature
            or headers.get("X-Signature")
            or headers.get("X-Webhook-Signature")
            or ""
        )
        provided = provided.replace("sha256=", "")

        if not hmac.compare_digest(expected, provided):
            raise RuntimeError("Signature webhook invalide.")

        import json
        return json.loads(payload)

    def extract_webhook_data(self, event: dict) -> dict:
        """Extrait les données utiles (à adapter selon le format du provider)."""
        return {
            "external_id": (
                event.get("reference")
                or event.get("transaction_id")
                or event.get("id")
            ),
            "status": (
                "success"
                if event.get("status") in ("success", "paid", "completed", "SUCCESS")
                else "failed"
            ),
            "business_id": event.get("business_id"),
            "plan_key": event.get("plan"),
        }


# ==================================================
# PROVIDER STRIPE (test international)
# ==================================================
class StripePaymentProvider(PaymentProvider):
    """Stripe Checkout — utile pour tester ou vendre à l'international."""

    name = "stripe"
    display_name = "Carte bancaire (Stripe)"

    def __init__(self):
        import stripe
        stripe.api_key = current_app.config.get("STRIPE_SECRET_KEY")
        if not stripe.api_key:
            raise RuntimeError("STRIPE_SECRET_KEY non configuré.")
        self.stripe = stripe

    def create_payment(
        self, business, plan_key: str, plan: dict,
        success_url: str, cancel_url: str, notify_url: str,
    ) -> PaymentInitResult:
        if plan["price_eur"] <= 0:
            return PaymentInitResult(success=False, error="Plan gratuit.")

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

            return PaymentInitResult(
                success=True,
                payment_url=session.url,
                external_id=session.id,
            )
        except Exception as e:
            current_app.logger.exception("Erreur Stripe")
            return PaymentInitResult(success=False, error=str(e)[:300])

    def verify_webhook(self, payload: bytes, signature: str, headers: dict) -> dict:
        secret = current_app.config.get("STRIPE_WEBHOOK_SECRET")
        if not secret:
            raise RuntimeError("STRIPE_WEBHOOK_SECRET non configuré.")
        try:
            return self.stripe.Webhook.construct_event(payload, signature, secret)
        except Exception as e:
            raise RuntimeError(f"Signature Stripe invalide : {e}")

    def extract_webhook_data(self, event: dict) -> dict:
        data = event.get("data", {}).get("object", {})
        metadata = data.get("metadata") or {}
        return {
            "external_id": data.get("id"),
            "status": (
                "success"
                if event.get("type") in ("checkout.session.completed", "invoice.paid")
                else "failed"
            ),
            "business_id": int(metadata.get("business_id", 0)) or None,
            "plan_key": metadata.get("plan"),
        }


# ==================================================
# PROVIDER BANCOBU (à configurer quand tu auras l'API)
# ==================================================
class BancobuPaymentProvider(GenericPaymentProvider):
    """
    Provider Bancobu eNoti / BurundiPay.
    Étend le provider générique en attendant l'API officielle.

    À personnaliser quand tu auras la documentation de Bancobu.
    """

    name = "bancobu"
    display_name = "Bancobu (Mobile Money)"

    def create_payment(self, business, plan_key, plan, success_url, cancel_url, notify_url):
        # TODO : implémenter l'appel à l'API Bancobu quand disponible
        # Pour l'instant, on utilise le provider générique
        return super().create_payment(
            business, plan_key, plan, success_url, cancel_url, notify_url,
        )


# ==================================================
# FACTORY — Choisit le provider actif
# ==================================================
def get_provider() -> PaymentProvider:
    """
    Retourne le provider de paiement configuré dans PAYMENT_PROVIDER.
    Lève une erreur si le provider n'est pas configuré.
    """
    provider_name = (current_app.config.get("PAYMENT_PROVIDER") or "").lower()

    if not provider_name or provider_name == "none":
        raise RuntimeError(
            "Le paiement n'est pas encore configuré. "
            "Contactez l'administrateur de LionFlow AI."
        )

    providers = {
        "generic": GenericPaymentProvider,
        "bancobu": BancobuPaymentProvider,
        "paydunya": GenericPaymentProvider,   # à remplacer par PayDunyaProvider
        "stripe": StripePaymentProvider,
    }

    if provider_name not in providers:
        raise RuntimeError(f"Provider '{provider_name}' inconnu.")

    return providers[provider_name]()


def is_payment_configured() -> bool:
    """Vérifie si un provider de paiement est configuré."""
    provider_name = (current_app.config.get("PAYMENT_PROVIDER") or "").lower()
    if not provider_name or provider_name == "none":
        return False

    if provider_name == "stripe":
        return bool(current_app.config.get("STRIPE_SECRET_KEY"))
    return bool(current_app.config.get("PAYMENT_API_KEY"))


def get_provider_display_name() -> str:
    """Retourne le nom lisible du provider actif (pour les templates)."""
    try:
        return get_provider().display_name
    except Exception:
        return "Paiement"


# ==================================================
# SERVICE MÉTIER
# ==================================================
class PaymentService:

    @staticmethod
    def activate_subscription(
        business, plan_key: str, payment_id: int | None = None,
    ) -> Subscription:
        """Active un abonnement après confirmation du paiement."""
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

    @staticmethod
    def mark_payment_failed(external_id: str) -> None:
        """Marque un paiement comme échoué."""
        payment = Payment.query.filter_by(external_id=external_id).first()
        if payment:
            payment.status = "failed"
            db.session.commit()