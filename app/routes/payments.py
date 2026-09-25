"""Routes paiements — stub (à compléter en PARTIE 9)."""
from flask import Blueprint, render_template
from flask_login import login_required


payments_bp = Blueprint("payments", __name__, template_folder="../templates/payments")


@payments_bp.route("/")
@login_required
def list_payments():
    return render_template("_placeholder.html", title="Paiements", icon="cash-coin")

"""
Pages paiements : historique + succès checkout + webhook + simulateur dev.
"""
from flask import (
    Blueprint, render_template, redirect, url_for, flash,
    request, current_app, jsonify,
)
from flask_login import login_required

from app.extensions import db, csrf
from app.models.payment import Payment
from app.services.payment_service import (
    get_provider, PaymentService, DevPaymentProvider,
)
from app.utils.decorators import require_business, get_current_business
from app.utils.security import log_activity


payments_bp = Blueprint("payments", __name__, template_folder="../templates/payments")


# ==================================================
# HISTORIQUE
# ==================================================
@payments_bp.route("/")
@login_required
@require_business
def list_payments():
    business = get_current_business()
    payments = (
        Payment.query
        .filter_by(business_id=business.id)
        .order_by(Payment.created_at.desc())
        .limit(100)
        .all()
    )
    return render_template(
        "payments/list.html",
        business=business,
        payments=payments,
    )


# ==================================================
# SUCCÈS CHECKOUT (Stripe renvoie ici)
# ==================================================
@payments_bp.route("/success")
@login_required
@require_business
def checkout_success():
    business = get_current_business()
    session_id = request.args.get("session_id")
    plan_key = request.args.get("plan")  # en dev

    if session_id:
        payment = Payment.query.filter_by(external_id=session_id).first()
        if payment:
            # En prod, la confirmation réelle vient du webhook.
            # Ici on active pour ne pas bloquer l'UX.
            plan = _plan_from_payment(payment, business)
            PaymentService.activate_subscription(business, plan, payment.id)
            log_activity(
                action="payment_success",
                description=f"Paiement confirmé ({plan})",
            )
            flash("Paiement confirmé. Merci !", "success")
            return redirect(url_for("subscriptions.current"))

    flash("Paiement en cours de traitement…", "info")
    return redirect(url_for("subscriptions.current"))


# ==================================================
# SIMULATEUR DEV
# ==================================================
@payments_bp.route("/dev-simulate/<int:payment_id>")
@login_required
@require_business
def dev_simulate(payment_id: int):
    """Simule un paiement réussi en mode dev."""
    business = get_current_business()
    plan_key = request.args.get("plan", "pro")

    payment = Payment.query.filter_by(
        id=payment_id, business_id=business.id
    ).first_or_404()

    if not current_app.config.get("DEBUG"):
        flash("Cette route n'est disponible qu'en mode développement.", "warning")
        return redirect(url_for("subscriptions.plans"))

    PaymentService.activate_subscription(business, plan_key, payment.id)
    log_activity(
        action="payment_dev_simulate",
        description=f"Paiement simulé (dev) pour plan {plan_key}",
    )
    flash(
        f"[DEV] Paiement simulé avec succès. Plan {plan_key} activé.",
        "success",
    )
    return redirect(url_for("subscriptions.current"))


# ==================================================
# WEBHOOK STRIPE
# ==================================================
@payments_bp.route("/webhook", methods=["POST"])
@csrf.exempt
def webhook():
    """
    Réception des événements Stripe.
    Vérifie la signature, puis met à jour paiement + abonnement.
    """
    payload = request.get_data()
    signature = request.headers.get("Stripe-Signature", "")

    try:
        provider = get_provider()
        if not isinstance(provider, type(None)) and hasattr(provider, "verify_webhook"):
            event = provider.verify_webhook(payload, signature)
        else:
            return jsonify(success=False), 400
    except Exception as e:
        current_app.logger.warning(f"[Stripe] Webhook rejeté : {e}")
        return jsonify(success=False, error=str(e)), 400

    event_type = event.get("type") if isinstance(event, dict) else None
    data = event.get("data", {}).get("object", {}) if isinstance(event, dict) else {}

    current_app.logger.info(f"[Stripe] Événement reçu : {event_type}")

    if event_type in ("checkout.session.completed", "invoice.paid"):
        business_id = int((data.get("metadata") or {}).get("business_id", 0))
        plan_key = (data.get("metadata") or {}).get("plan", "pro")
        external_id = data.get("id")

        if business_id:
            from app.models.business import Business
            business = db.session.get(Business, business_id)
            if business:
                payment = Payment.query.filter_by(external_id=external_id).first()
                PaymentService.activate_subscription(
                    business, plan_key,
                    payment.id if payment else None,
                )

    elif event_type in ("invoice.payment_failed", "charge.failed"):
        business_id = int((data.get("metadata") or {}).get("business_id", 0))
        if business_id:
            from app.models.business import Business
            business = db.session.get(Business, business_id)
            if business:
                sub = business.subscription
                if sub:
                    sub.status = "past_due"
                    db.session.commit()

    return jsonify(success=True), 200


# ==================================================
# HELPER
# ==================================================
def _plan_from_payment(payment: Payment, business) -> str:
    """Détermine le plan à partir du montant du paiement."""
    plans = current_app.config.get("PLANS", {})
    for key, cfg in plans.items():
        if int(cfg["price_eur"] * 100) == payment.amount_cents:
            return key
    return "pro"