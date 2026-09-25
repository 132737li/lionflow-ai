"""
CRUD des comptes WhatsApp + test de connexion + webhook Meta.
Multi-tenant : filtré par business_id.
Pays par défaut : Burundi (+257). Tous les pays acceptés.
"""
import json
import hmac
import hashlib
from datetime import datetime, timezone

from flask import (
    Blueprint, render_template, redirect, url_for, flash, request,
    current_app, jsonify, abort,
)
from flask_login import login_required, current_user

from app.extensions import db, csrf
from app.forms.whatsapp_forms import WhatsAppAccountForm
from app.models.whatsapp_account import WhatsAppAccount
from app.models.message import Message
from app.services.whatsapp_service import WhatsAppService
from app.services.notification_service import NotificationService
from app.utils.decorators import require_business, get_current_business
from app.utils.security import log_activity
from app.utils.validators import normalize_phone


whatsapp_bp = Blueprint("whatsapp", __name__, template_folder="../templates/whatsapp")


def _utcnow():
    """Heure UTC naïve (compatible MySQL DATETIME)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _merge_country_and_phone(country_code: str, raw_phone: str) -> str | None:
    """Fusionne indicatif pays + numéro (même logique que contacts)."""
    if not raw_phone:
        return None
    raw = str(raw_phone).strip()
    if raw.startswith("+"):
        return normalize_phone(raw, default_region="BI")
    region = country_code or "BI"
    if region == "OTHER":
        region = "BI"
    return normalize_phone(raw, default_region=region)


# ==================================================
# LISTE
# ==================================================
@whatsapp_bp.route("/")
@login_required
@require_business
def list_accounts():
    business = get_current_business()
    accounts = (
        WhatsAppAccount.query
        .filter_by(business_id=business.id)
        .order_by(WhatsAppAccount.created_at.desc())
        .all()
    )
    return render_template(
        "whatsapp/list.html",
        accounts=accounts,
        business=business,
    )


# ==================================================
# CRÉATION
# ==================================================
@whatsapp_bp.route("/new", methods=["GET", "POST"])
@login_required
@require_business
def create_account():
    business = get_current_business()

    if not business.can_add_whatsapp_account():
        flash(
            f"Quota de comptes WhatsApp atteint pour le plan '{business.plan}'. "
            "Passez à un plan supérieur.",
            "warning",
        )
        return redirect(url_for("subscriptions.current"))

    form = WhatsAppAccountForm()
    if form.validate_on_submit():
        final_phone = _merge_country_and_phone(
            form.country_code.data, form.phone_number.data
        )
        if not final_phone:
            flash("Numéro WhatsApp invalide.", "danger")
            return render_template(
                "whatsapp/form.html", form=form, account=None, business=business
            )

        account = WhatsAppAccount(
            business_id=business.id,
            name=form.name.data.strip(),
            phone_number=final_phone,
            phone_number_id=(form.phone_number_id.data or "").strip() or None,
            business_account_id=(form.business_account_id.data or "").strip() or None,
            status=form.status.data or "disconnected",
        )
        if form.access_token.data:
            account.set_access_token(form.access_token.data)
            account.connected_at = _utcnow()

        db.session.add(account)
        db.session.commit()

        log_activity(
            action="waba_create",
            description=f"Compte WhatsApp créé : {account.name} ({account.phone_number})",
        )
        flash("Compte WhatsApp créé.", "success")
        return redirect(url_for("whatsapp.list_accounts"))

    return render_template(
        "whatsapp/form.html",
        form=form,
        account=None,
        business=business,
    )


# ==================================================
# MODIFICATION
# ==================================================
@whatsapp_bp.route("/<int:account_id>/edit", methods=["GET", "POST"])
@login_required
@require_business
def edit_account(account_id: int):
    business = get_current_business()
    account = WhatsAppAccount.query.filter_by(
        id=account_id, business_id=business.id
    ).first_or_404()

    form = WhatsAppAccountForm(obj=account)
    if request.method == "GET":
        form.country_code.data = "BI"
        form.phone_number.data = account.phone_number

    if form.validate_on_submit():
        final_phone = _merge_country_and_phone(
            form.country_code.data, form.phone_number.data
        )
        if not final_phone:
            flash("Numéro WhatsApp invalide.", "danger")
            return render_template(
                "whatsapp/form.html", form=form, account=account, business=business
            )

        account.name = form.name.data.strip()
        account.phone_number = final_phone
        account.phone_number_id = (form.phone_number_id.data or "").strip() or None
        account.business_account_id = (form.business_account_id.data or "").strip() or None
        account.status = form.status.data or "disconnected"

        if form.access_token.data:
            account.set_access_token(form.access_token.data)
            account.connected_at = _utcnow()

        db.session.commit()

        log_activity(
            action="waba_update",
            description=f"Compte WhatsApp modifié : {account.name}",
        )
        flash("Compte WhatsApp mis à jour.", "success")
        return redirect(url_for("whatsapp.list_accounts"))

    return render_template(
        "whatsapp/form.html",
        form=form,
        account=account,
        business=business,
    )


# ==================================================
# SUPPRESSION
# ==================================================
@whatsapp_bp.route("/<int:account_id>/delete", methods=["POST"])
@login_required
@require_business
def delete_account(account_id: int):
    business = get_current_business()
    account = WhatsAppAccount.query.filter_by(
        id=account_id, business_id=business.id
    ).first_or_404()

    name = account.name
    db.session.delete(account)
    db.session.commit()

    log_activity(
        action="waba_delete",
        description=f"Compte WhatsApp supprimé : {name}",
    )
    flash(f"Compte « {name} » supprimé.", "info")
    return redirect(url_for("whatsapp.list_accounts"))


# ==================================================
# TEST DE CONNEXION
# ==================================================
@whatsapp_bp.route("/<int:account_id>/test", methods=["POST"])
@login_required
@require_business
def test_connection(account_id: int):
    business = get_current_business()
    account = WhatsAppAccount.query.filter_by(
        id=account_id, business_id=business.id
    ).first_or_404()

    result = WhatsAppService.test_connection(account)
    if result["success"]:
        account.status = "connected"
        account.connected_at = _utcnow()
        db.session.commit()
        flash(f"Connexion réussie : {result['message']}", "success")
        log_activity(
            action="waba_test_success",
            description=f"Test de connexion réussi : {account.name}",
        )
    else:
        account.status = "error"
        db.session.commit()
        flash(f"Échec de connexion : {result['error']}", "danger")
        log_activity(
            action="waba_test_failed",
            description=f"Test de connexion échoué : {account.name} — {result['error']}",
        )
    return redirect(url_for("whatsapp.list_accounts"))


# ==================================================
# WEBHOOK META — VÉRIFICATION (GET)
# ==================================================
@whatsapp_bp.route("/webhook", methods=["GET"])
@csrf.exempt
def webhook_verify():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge", "")

    ok, chal = WhatsAppService.verify_webhook(mode, token, challenge)
    if ok:
        current_app.logger.info("[WA-Webhook] Vérification réussie.")
        return chal, 200
    current_app.logger.warning("[WA-Webhook] Vérification échouée.")
    return "Forbidden", 403


# ==================================================
# WEBHOOK META — RÉCEPTION (POST)
# ==================================================
@whatsapp_bp.route("/webhook", methods=["POST"])
@csrf.exempt
def webhook_receive():
    _verify_signature_if_configured()

    payload = request.get_json(silent=True) or {}
    current_app.logger.info(f"[WA-Webhook] Payload reçu : {json.dumps(payload)[:500]}")

    try:
        entries = payload.get("entry", [])
        for entry in entries:
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for status in value.get("statuses", []):
                    _handle_status_update(status)
                for msg in value.get("messages", []):
                    _handle_incoming_message(msg, value)
    except Exception:
        current_app.logger.exception("[WA-Webhook] Erreur traitement payload")

    return jsonify(success=True), 200


# ==================================================
# HANDLERS INTERNES
# ==================================================
def _handle_status_update(status: dict) -> None:
    external_id = status.get("id")
    new_status = status.get("status")
    if not external_id or not new_status:
        return

    message = Message.query.filter_by(external_id=external_id).first()
    if not message:
        return

    if new_status == "delivered":
        message.mark_delivered()
    elif new_status == "read":
        message.mark_read()
    elif new_status == "failed":
        errs = status.get("errors") or []
        err_msg = errs[0].get("title") if errs else "Échec côté Meta"
        message.mark_failed(err_msg)

    db.session.commit()

    if message.campaign:
        message.campaign.recalc_counters()
        db.session.commit()

    if new_status == "failed" and message.campaign:
        NotificationService.notify(
            user_id=message.campaign.business.owner_id,
            title="Message échoué",
            message=(
                f"Le message vers {message.contact.phone} a échoué : "
                f"{message.error or 'raison inconnue'}"
            ),
            type="error",
            link=f"/campaigns/{message.campaign.id}",
        )


def _handle_incoming_message(msg: dict, value: dict) -> None:
    sender = msg.get("from")
    text = (msg.get("text") or {}).get("body", "")
    if not sender:
        return

    phone_number_id = (value.get("metadata") or {}).get("phone_number_id")
    account = None
    if phone_number_id:
        account = WhatsAppAccount.query.filter_by(phone_number_id=phone_number_id).first()

    contact = None
    if account:
        from app.models.contact import Contact
        normalized = f"+{sender}" if not sender.startswith("+") else sender
        contact = Contact.query.filter_by(
            business_id=account.business_id, phone=normalized
        ).first()

    log_activity(
        action="waba_incoming",
        description=(
            f"Message entrant de {sender}"
            + (f" ({contact.full_name})" if contact else "")
            + f" : {text[:120]}"
        ),
        user_id=account.business.owner_id if account else None,
    )

    if account:
        NotificationService.notify(
            user_id=account.business.owner_id,
            title="Nouveau message WhatsApp",
            message=f"{contact.full_name if contact else sender} : {text[:120]}",
            type="info",
        )


def _verify_signature_if_configured() -> None:
    app_secret = current_app.config.get("WHATSAPP_APP_SECRET")
    if not app_secret:
        return

    signature = request.headers.get("X-Hub-Signature-256", "")
    if not signature.startswith("sha256="):
        abort(403)

    expected = hmac.new(
        app_secret.encode(),
        request.get_data(),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(f"sha256={expected}", signature):
        abort(403)