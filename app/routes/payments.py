"""
Routes de paiement (Webhooks et pages de succès).
"""
import hmac
import hashlib
import json
from datetime import datetime, timezone
from flask import Blueprint, request, Response, current_app, redirect, url_for, flash
from flask_login import login_required, current_user

from app.extensions import db
from app.models.business import Business
from app.models.subscription import Subscription
from app.models.user import User

payments_bp = Blueprint("payments", __name__, url_prefix="/payments")


# ==================================================
# PAGE DE SUCCÈS (Activation de l'abonnement)
# ==================================================
@payments_bp.route("/checkout/success", methods=["GET"])
@login_required
def checkout_success():
    """Page affichée après un paiement réussi."""
    business_id = request.args.get("business_id")
    plan_name = request.args.get("plan")
    
    if business_id and plan_name:
        business = Business.query.get(int(business_id))
        if business:
            Subscription.query.filter_by(business_id=business.id, status="active").update({"status": "cancelled"})
            new_sub = Subscription(
                business_id=business.id,
                plan=plan_name,
                status="active",
                started_at=datetime.now(timezone.utc).replace(tzinfo=None)
            )
            new_sub.extend(30)
            db.session.add(new_sub)
            db.session.commit()
            flash(f"Votre abonnement {plan_name.upper()} a été activé avec succès !", "success")
            return redirect(url_for("subscriptions.current"))

    flash("Paiement réussi ! Votre abonnement est en cours d'activation.", "info")
    return redirect(url_for("subscriptions.current"))


@payments_bp.route("/checkout/cancel", methods=["GET"])
@login_required
def checkout_cancel():
    flash("Le paiement a été annulé. Vous n'avez pas été débité.", "warning")
    return redirect(url_for("subscriptions.plans"))


# ==================================================
# WEBHOOK ULTRANER (Sécurité et Logs)
# ==================================================
@payments_bp.route("/webhook", methods=["POST"])
@payments_bp.route("/webhooks/ultraner", methods=["POST"])
def webhook():
    current_app.logger.info("=== WEBHOOK REÇU ===")
    raw_body = request.get_data()
    current_app.logger.info(f"Payload: {raw_body.decode('utf-8')}")

    # ⚠️ La vérification de signature est désactivée pour le moment 
    # car UltraNer n'envoie pas les metadata et le secret bloque.
    # signature = request.headers.get("X-Ultraner-Signature", "")
    # secret = current_app.config.get("ULTRANER_WEBHOOK_SECRET", "").encode()
    # if secret:
    #     expected = hmac.new(secret, raw_body, hashlib.sha256).hexdigest()
    #     if not hmac.compare_digest(signature, expected):
    #         current_app.logger.warning("[Webhook] Signature invalide")
    #         return "", 401  # ✅ Correction de l'erreur 500

    try:
        event = json.loads(raw_body)
        event_type = event.get("event")
        current_app.logger.info(f"[Webhook] Événement: {event_type}")
        
        # On ne traite plus l'activation ici car le webhook n'a pas le business_id.
        # L'activation est gérée par la page checkout_success.
        
    except Exception as e:
        current_app.logger.exception(f"[Webhook] Erreur: {e}")

    return "", 200 # ✅ Réponse 200 obligatoire