"""
LionFlow AI — Routes de gestion des webhooks sortants.
"""
from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, abort,
)
from flask_login import login_required

from app.extensions import db
from app.models.webhook import Webhook, WebhookDelivery
from app.models.voice_session import VoiceSession, VoiceMessage
from app.services import webhook_service
from app.utils.decorators import require_business, get_current_business


webhooks_bp = Blueprint(
    "webhooks",
    __name__,
    template_folder="../templates/webhooks",
)


@webhooks_bp.route("/")
@login_required
@require_business
def list_webhooks():
    business = get_current_business()
    hooks = (
        Webhook.query
        .filter_by(business_id=business.id)
        .order_by(Webhook.created_at.desc())
        .all()
    )
    return render_template("webhooks/list.html", webhooks=hooks, business=business)


@webhooks_bp.route("/new", methods=["GET", "POST"])
@login_required
@require_business
def create_webhook():
    business = get_current_business()

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        url = (request.form.get("url") or "").strip()
        events = request.form.getlist("events")
        description = (request.form.get("description") or "").strip()

        if not name or not url:
            flash("Nom et URL obligatoires.", "danger")
            return redirect(url_for("webhooks.create_webhook"))
        if not webhook_service._is_valid_url(url):
            flash("URL invalide (http/https attendu).", "danger")
            return redirect(url_for("webhooks.create_webhook"))
        if not events:
            flash("Sélectionnez au moins un événement.", "danger")
            return redirect(url_for("webhooks.create_webhook"))

        webhook = Webhook(
            business_id=business.id,
            name=name,
            url=url,
            description=description,
        )
        webhook.set_events(events)
        db.session.add(webhook)
        db.session.commit()
        flash(
            "Webhook créé. Conservez le secret pour vérifier les signatures.",
            "success",
        )
        return redirect(url_for("webhooks.detail_webhook", webhook_id=webhook.id))

    return render_template(
        "webhooks/form.html",
        webhook=None,
        business=business,
        events=webhook_service.SUPPORTED_EVENTS,
        selected=[],
    )


@webhooks_bp.route("/<int:webhook_id>")
@login_required
@require_business
def detail_webhook(webhook_id):
    business = get_current_business()
    webhook = Webhook.query.filter_by(
        id=webhook_id, business_id=business.id
    ).first_or_404()
    deliveries = (
        webhook.deliveries
        .order_by(WebhookDelivery.created_at.desc())
        .limit(50)
        .all()
    )
    return render_template(
        "webhooks/detail.html",
        webhook=webhook,
        business=business,
        deliveries=deliveries,
    )


@webhooks_bp.route("/<int:webhook_id>/edit", methods=["GET", "POST"])
@login_required
@require_business
def edit_webhook(webhook_id):
    business = get_current_business()
    webhook = Webhook.query.filter_by(
        id=webhook_id, business_id=business.id
    ).first_or_404()

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        url = (request.form.get("url") or "").strip()
        events = request.form.getlist("events")
        description = (request.form.get("description") or "").strip()

        if not name or not url or not events:
            flash("Champs obligatoires manquants.", "danger")
            return redirect(url_for("webhooks.edit_webhook", webhook_id=webhook.id))
        if not webhook_service._is_valid_url(url):
            flash("URL invalide.", "danger")
            return redirect(url_for("webhooks.edit_webhook", webhook_id=webhook.id))

        webhook.name = name
        webhook.url = url
        webhook.description = description
        webhook.set_events(events)
        db.session.commit()
        flash("Webhook mis à jour.", "success")
        return redirect(url_for("webhooks.detail_webhook", webhook_id=webhook.id))

    return render_template(
        "webhooks/form.html",
        webhook=webhook,
        business=business,
        events=webhook_service.SUPPORTED_EVENTS,
        selected=webhook.get_events(),
    )


@webhooks_bp.route("/<int:webhook_id>/toggle", methods=["POST"])
@login_required
@require_business
def toggle_webhook(webhook_id):
    business = get_current_business()
    webhook = Webhook.query.filter_by(
        id=webhook_id, business_id=business.id
    ).first_or_404()
    webhook.is_active = not webhook.is_active
    db.session.commit()
    flash(
        f"Webhook {'activé' if webhook.is_active else 'désactivé'}.",
        "info",
    )
    return redirect(url_for("webhooks.detail_webhook", webhook_id=webhook.id))


@webhooks_bp.route("/<int:webhook_id>/delete", methods=["POST"])
@login_required
@require_business
def delete_webhook(webhook_id):
    business = get_current_business()
    webhook = Webhook.query.filter_by(
        id=webhook_id, business_id=business.id
    ).first_or_404()
    db.session.delete(webhook)
    db.session.commit()
    flash("Webhook supprimé.", "info")
    return redirect(url_for("webhooks.list_webhooks"))


@webhooks_bp.route("/<int:webhook_id>/test", methods=["POST"])
@login_required
@require_business
def test_webhook(webhook_id):
    business = get_current_business()
    webhook = Webhook.query.filter_by(
        id=webhook_id, business_id=business.id
    ).first_or_404()
    delivery = webhook_service.send_test(webhook)
    if delivery.status == "success":
        flash("Test envoyé avec succès.", "success")
    else:
        flash(
            f"Test échoué : {delivery.error or f'HTTP {delivery.response_status}'}",
            "warning",
        )
    return redirect(url_for("webhooks.detail_webhook", webhook_id=webhook.id))


@webhooks_bp.route("/<int:webhook_id>/regenerate-secret", methods=["POST"])
@login_required
@require_business
def regenerate_secret(webhook_id):
    business = get_current_business()
    webhook = Webhook.query.filter_by(
        id=webhook_id, business_id=business.id
    ).first_or_404()
    webhook.secret = _gen_secret()
    db.session.commit()
    flash("Secret régénéré. Mettez à jour votre intégration.", "warning")
    return redirect(url_for("webhooks.detail_webhook", webhook_id=webhook.id))