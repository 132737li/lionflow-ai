"""
Pages paiements : historique + retour paiement + webhook générique.
"""
from flask import (
    Blueprint, render_template, redirect, url_for, flash,
    request, current_app, jsonify,
)
from flask_login import login_required

from app.extensions import db, csrf
from app.models.payment import Payment
from app.services.payment_service import (
    get_provider, PaymentService, is_payment_configured,
)
from app.utils.decorators import require_business, get_current_business
from app.utils.security import log_activity


payments_bp = Blueprint("payments", __name__, template_folder="../templates/payments")


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
        payment_configured=is_payment_configured(),
    )


@payments_bp.route("/success")
@login_required
@require_business
def checkout_success():
    """
    Retour de l'utilisateur après paiement.
    Le plan est activé par le webhook (asynchrone).
    """
    business = get_current_business()
    reference = request.args.get("reference") or request.args.get("session_id")

    log_activity(
        action="payment_success_page",
        description=f"Retour du paiement (référence={reference})",
    )

    flash(
        "Paiement reçu ! Votre abonnement sera activé dans quelques secondes.",
        "success",
    )
    return redirect(url_for("subscriptions.current"))


@payments_bp.route("/failed")
@login_required
@require_business
def checkout_failed():
    """Retour en cas d'échec du paiement."""
    flash(
        "Le paiement a échoué ou a été annulé. "
        "Vous pouvez réessayer depuis la page des plans.",
        "warning",
    )
    return redirect(url_for("subscriptions.plans"))


# ==================================================
# WEBHOOK GÉNÉRIQUE
# ==================================================
@payments_bp.route("/webhook", methods=["POST"])
@csrf.exempt
def webhook():
    """
    Webhook universel : reçoit la confirmation de paiement du provider.
    Vérifie la signature, puis active l'abonnement.
    """
    if not is_payment_configured():
        return jsonify(success=False, error="Paiement non configuré"), 400

    payload = request.get_data()
    signature = (
        request.headers.get("X-Signature")
        or request.headers.get("X-Webhook-Signature")
        or request.headers.get("Stripe-Signature")
        or ""
    )
    headers = dict(request.headers)

    try:
        provider = get_provider()
        event = provider.verify_webhook(payload, signature, headers)
    except Exception as e:
        current_app.logger.warning(f"[Webhook] Rejeté : {e}")
        return jsonify(success=False, error=str(e)), 400

    # Extraire les données utiles
    try:
        data = provider.extract_webhook_data(event)
    except Exception:
        current_app.logger.exception("[Webhook] Impossible d'extraire les données")
        return jsonify(success=False, error="Format invalide"), 400

    current_app.logger.info(f"[Webhook] Événement reçu : {data}")

    external_id = data.get("external_id")
    status = data.get("status")
    business_id = data.get("business_id")
    plan_key = data.get("plan_key")

    if not external_id:
        return jsonify(success=False, error="external_id manquant"), 400

    payment = Payment.query.filter_by(external_id=external_id).first()
    if not payment:
        current_app.logger.warning(f"[Webhook] Paiement introuvable : {external_id}")
        return jsonify(success=False, error="Paiement introuvable"), 404

    if status == "success":
        # Déterminer le business et le plan
        business = None
        if business_id:
            from app.models.business import Business
            business = db.session.get(Business, business_id)
        if not business:
            business = payment.business

        if not plan_key:
            # Déduire le plan depuis le montant
            plans = current_app.config.get("PLANS", {})
            for key, cfg in plans.items():
                if int(cfg["price_eur"] * 100) == payment.amount_cents:
                    plan_key = key
                    break

        if business and plan_key:
            PaymentService.activate_subscription(business, plan_key, payment.id)
            log_activity(
                action="payment_webhook_success",
                description=f"Paiement confirmé (plan={plan_key})",
                user_id=business.owner_id,
            )
        else:
            current_app.logger.warning(
                "[Webhook] Business ou plan_key manquant"
            )

    elif status == "failed":
        PaymentService.mark_payment_failed(external_id)
        log_activity(
            action="payment_webhook_failed",
            description=f"Paiement échoué (référence={external_id})",
        )

    return jsonify(success=True), 200