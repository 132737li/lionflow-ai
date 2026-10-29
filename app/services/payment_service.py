"""
Service d'intégration avec l'API UltraNer.
"""
import requests
from datetime import datetime, timezone
from flask import current_app
from app.extensions import db
from app.models.subscription import Subscription


class UltranerProvider:
    def __init__(self, api_key):
        self.api_key = api_key
        self.name = "ultraner"

    def create_payment(self, business, plan_key, plan, success_url, cancel_url, notify_url):
        class Result:
            def __init__(self, success, payment_url=None, error=None):
                self.success = success
                self.payment_url = payment_url
                self.error = error

        try:
            amount_bif = plan.get("price_bif", plan.get("price_eur", 0) * 3000)
            
            url = "https://api.ultraner.com/v0-sandbox/checkout/sessions"
            
            headers = {
                "X-API-Key": self.api_key,
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            payload = {
                "amount": amount_bif,
                "currency": "BIF",
                "description": f"LionFlow AI - Plan {plan.get('label', plan_key)}",
                "customer_email": business.email or business.owner.email,
                "success_url": success_url,
                "cancel_url": cancel_url,
                "webhook_url": notify_url,
                "metadata": {"plan": plan_key, "business_id": str(business.id)}
            }

            session = requests.Session()
            session.trust_env = False
            
            resp = session.post(url, json=payload, headers=headers, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            
            checkout_url = data.get("data", {}).get("url") or data.get("url")
            
            if not checkout_url:
                return Result(False, error="Pas d'URL de paiement retournée.")
            
            return Result(True, payment_url=checkout_url)
            
        except Exception as e:
            return Result(False, error=str(e))


def is_payment_configured() -> bool:
    key = current_app.config.get("ULTRANER_API_KEY", "")
    return bool(key and len(key) > 5)

def get_provider_display_name() -> str:
    return "UltraNer" if is_payment_configured() else "Non configuré"

def get_provider():
    if not is_payment_configured():
        raise RuntimeError("Le paiement n'est pas configuré.")
    return UltranerProvider(current_app.config["ULTRANER_API_KEY"])


class PaymentService:

    @staticmethod
    def activate_subscription(business, plan_key: str):
        Subscription.query.filter_by(business_id=business.id, status="active").update({"status": "cancelled"})
        new_sub = Subscription(
            business_id=business.id,
            plan=plan_key,
            status="active",
            started_at=datetime.now(timezone.utc).replace(tzinfo=None)
        )
        if plan_key != "free":
            new_sub.extend(30)
        db.session.add(new_sub)
        db.session.commit()

    @staticmethod
    def create_checkout_session(plan_name: str, amount_bif: int, user_email: str, business_id: int):
        provider = get_provider()
        
        class FakeBusiness:
            email = user_email
            id = business_id
            owner = type('obj', (object,), {'email': user_email})()
            
        base_url = current_app.config.get("APP_BASE_URL", "http://localhost:5000")
        
        # ✅ NOUVEAU : On passe le business_id et le plan dans l'URL de succès
        success_url = f"{base_url}/payments/checkout/success?business_id={business_id}&plan={plan_name.lower()}"
        
        result = provider.create_payment(
            business=FakeBusiness(),
            plan_key=plan_name.lower(),
            plan={"label": plan_name, "price_bif": amount_bif},
            success_url=success_url,
            cancel_url=f"{base_url}/subscriptions/?canceled=true",
            notify_url=f"{base_url}/payments/webhook"
        )
        
        if not result.success:
            raise Exception(result.error)
            
        return result.payment_url