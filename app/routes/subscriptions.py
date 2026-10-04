"""
Pages abonnement : plans, abonnement actuel, changement.
Paiement obligatoire pour les plans payants.
"""
from datetime import datetime, timezone

from flask import (
    Blueprint, render_template, redirect, url_for, flash, request,
    current_app,
)
from flask_login import login_required

from app.extensions import db
from app.models.subscription import Subscription
from app.services.payment_service import (
    get_provider, PaymentService, is_payment_configured,
    get_provider_display_name,
)
from app.utils.decorators import require_business, get_current_business
from app.utils.security import log_activity


subscriptions_bp = Blueprint(
    "subscriptions", __name__,
    template_folder="../templates/subscriptions",
)


@subscriptions_bp.route("/")
@login_required
@require_business
def current():
    business = get_current_business()
    sub = business.subscription
    plans = current_app.config.get("PLANS", {})

    history = (
        Subscription.query
        .filter_by(business_id=business.id)
        .order_by(Subscription.created_at.desc())
        .limit(10)
        .all()
    )

    usage = {
        "contacts": business.contact_count(),
        "campaigns": business.campaigns.count(),
        "whatsapp_accounts": business.whatsapp_accounts.count(),
        "messages_this_month": _count_messages_this_month(business),
    }

    return render_template(
        "subscriptions/current.html",
        business=business,
        subscription=sub,
        plans=plans,
        plan_config=business.plan_config,
        usage=usage,
        history=history,
        payment_configured=is_payment_configured(),
    )


@subscriptions_bp.route("/plans")
@login_required
@require_business
def plans():
    business = get_current_business()
    all_plans = current_app.config.get("PLANS", {})
    sub = business.subscription

    return render_template(
        "subscriptions/plans.html",
        business=business,
        plans=all_plans,
        subscription=sub,
        payment_configured=is_payment_configured(),
        payment_provider_name=get_provider_display_name(),
    )


@subscriptions_bp.route("/confirm/<plan_key>")
@login_required
@require_business
def confirm_plan(plan_key: str):
    business = get_current_business()
    all_plans = current_app.config.get("PLANS", {})

    if plan_key not in all_plans:
        flash("Plan inconnu.", "danger")
        return redirect(url_for("subscriptions.plans"))

    plan = all_plans[plan_key]

    if plan["price_eur"] <= 0:
        return redirect(url_for("subscriptions.change_plan", plan_key=plan_key))

    if not is_payment_configured():
        flash(
            "Le paiement n'est pas encore configuré. "
            "Contactez l'administrateur.",
            "danger",
        )
        return redirect(url_for("subscriptions.plans"))

    return render_template(
        "subscriptions/confirm.html",
        business=business,
        plan_key=plan_key,
        plan=plan,
        subscription=business.subscription,
        payment_provider_name=get_provider_display_name(),
    )


@subscriptions_bp.route("/change/<plan_key>", methods=["POST"])
@login_required
@require_business
def change_plan(plan_key: str):
    business = get_current_business()
    all_plans = current_app.config.get("PLANS", {})

    if plan_key not in all_plans:
        flash("Plan inconnu.", "danger")
        return redirect(url_for("subscriptions.plans"))

    plan = all_plans[plan_key]

    # Plan gratuit → activation immédiate
    if plan["price_eur"] <= 0:
        PaymentService.activate_subscription(business, plan_key)
        log_activity(
            action="subscription_free_activate",
            description=f"Plan gratuit activé : {plan_key}",
        )
        flash(f"Plan {plan['label']} activé.", "success")
        return redirect(url_for("subscriptions.current"))

    # Plan payant → paiement obligatoire
    if not is_payment_configured():
        flash(
            "Le paiement n'est pas encore configuré. "
            "Impossible d'activer un plan payant.",
            "danger",
        )
        log_activity(
            action="subscription_payment_blocked",
            description=f"Tentative activation plan {plan_key} sans paiement",
        )
        return redirect(url_for("subscriptions.plans"))

    # Initier le paiement
    try:
        provider = get_provider()
    except RuntimeError as e:
        flash(str(e), "danger")
        return redirect(url_for("subscriptions.plans"))

    success_url = url_for("payments.checkout_success", _external=True)
    cancel_url = url_for("subscriptions.plans", _external=True)
    notify_url = url_for("payments.webhook", _external=True)

    result = provider.create_payment(
        business, plan_key, plan,
        success_url=success_url,
        cancel_url=cancel_url,
        notify_url=notify_url,
    )

    if not result.success:
        flash(f"Erreur lors de l'initiation du paiement : {result.error}", "danger")
        return redirect(url_for("subscriptions.plans"))

    log_activity(
        action="subscription_checkout_started",
        description=f"Paiement {provider.name} initié pour plan {plan_key}",
    )

    # Redirection vers la page de paiement du provider
    return redirect(result.payment_url)


@subscriptions_bp.route("/cancel", methods=["POST"])
@login_required
@require_business
def cancel():
    business = get_current_business()
    sub = business.subscription
    if not sub or sub.plan == "free":
        flash("Aucun abonnement payant à annuler.", "info")
        return redirect(url_for("subscriptions.current"))

    sub.status = "cancelled"
    db.session.commit()

    PaymentService.activate_subscription(business, "free")

    log_activity(
        action="subscription_cancel",
        description=f"Abonnement annulé : {sub.plan}",
    )
    flash("Abonnement annulé. Vous êtes repassé au plan Free.", "info")
    return redirect(url_for("subscriptions.current"))


def _count_messages_this_month(business) -> int:
    from app.models.message import Message
    from app.models.campaign import Campaign
    from sqlalchemy import func, extract

    now = datetime.now(timezone.utc)
    return (
        db.session.query(func.count(Message.id))
        .join(Campaign, Message.campaign_id == Campaign.id)
        .filter(
            Campaign.business_id == business.id,
            extract("year", Message.created_at) == now.year,
            extract("month", Message.created_at) == now.month,
        )
        .scalar() or 0
    )