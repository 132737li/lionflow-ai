"""API campagnes — stub (à compléter en PARTIE 8)."""
from flask import Blueprint


api_campaigns_bp = Blueprint("api_campaigns", __name__)

"""
API REST Campagnes — CRUD + actions.
"""
from datetime import datetime, timezone
from flask import Blueprint, request, g

from app.extensions import db
from app.models.campaign import Campaign, campaign_contacts
from app.models.template import Template
from app.models.whatsapp_account import WhatsAppAccount
from app.models.contact import Contact
from app.services.campaign_service import CampaignService
from app.utils.security import log_activity
from app.utils.timezones import to_utc
from app.utils.validators import validate_required
from app.api._helpers import (
    ok, err, paginate, jwt_user_required, business_required,
)


api_campaigns_bp = Blueprint("api_campaigns", __name__)


# ==================================================
# LIST
# ==================================================
@api_campaigns_bp.route("", methods=["GET"])
@jwt_user_required
@business_required
def list_campaigns():
    query = Campaign.query.filter_by(business_id=g.api_business.id)

    status = (request.args.get("status") or "").strip()
    if status in ("draft", "scheduled", "running", "paused", "completed", "cancelled"):
        query = query.filter(Campaign.status == status)

    q = (request.args.get("q") or "").strip()
    if q:
        query = query.filter(Campaign.name.ilike(f"%{q}%"))

    query = query.order_by(Campaign.created_at.desc())
    page = paginate(query)
    return ok(
        {"items": [c.to_dict() for c in page["items"]], "meta": page["meta"]},
        "OK",
        200,
    )


# ==================================================
# CREATE
# ==================================================
@api_campaigns_bp.route("", methods=["POST"])
@jwt_user_required
@business_required
def create_campaign():
    biz = g.api_business
    data = request.get_json(silent=True) or {}

    missing = validate_required(data, ["name"])
    if missing:
        return err("Champs manquants.", missing, 422)

    # Template (optionnel)
    template_id = data.get("template_id")
    template = None
    if template_id:
        template = Template.query.filter_by(
            id=template_id, business_id=biz.id
        ).first()
        if not template:
            return err("Modèle introuvable.", None, 404)

    # WhatsApp account (optionnel)
    waba_id = data.get("whatsapp_account_id")
    waba = None
    if waba_id:
        waba = WhatsAppAccount.query.filter_by(
            id=waba_id, business_id=biz.id
        ).first()
        if not waba:
            return err("Compte WhatsApp introuvable.", None, 404)

    # Programmation
    scheduled_at_utc = None
    if data.get("scheduled_at"):
        try:
            local_dt = datetime.fromisoformat(data["scheduled_at"])
        except (ValueError, TypeError):
            return err("Format scheduled_at invalide (ISO 8601 attendu).", None, 422)
        scheduled_at_utc = to_utc(local_dt, data.get("timezone", "UTC"))

    # Contacts
    contact_ids = data.get("contact_ids") or []
    if not isinstance(contact_ids, list):
        return err("contact_ids doit être une liste d'identifiants.", None, 422)
    contacts = []
    if contact_ids:
        contacts = Contact.query.filter(
            Contact.business_id == biz.id,
            Contact.id.in_([int(i) for i in contact_ids if str(i).isdigit()]),
        ).all()

    status = "scheduled" if scheduled_at_utc else "draft"

    campaign = Campaign(
        business_id=biz.id,
        template_id=template.id if template else None,
        whatsapp_account_id=waba.id if waba else None,
        name=data["name"].strip(),
        message=(data.get("message") or "").strip() or None,
        status=status,
        scheduled_at=scheduled_at_utc,
        timezone=data.get("timezone", "UTC"),
        total_contacts=len(contacts),
    )
    db.session.add(campaign)
    db.session.flush()

    for c in contacts:
        db.session.execute(
            campaign_contacts.insert().values(campaign_id=campaign.id, contact_id=c.id)
        )
    db.session.commit()

    log_activity(
        action="api_campaign_create",
        description=f"Campagne créée via API : {campaign.name}",
        user_id=g.api_user.id,
    )
    return ok(campaign.to_dict(), "Campagne créée.", 201)


# ==================================================
# GET ONE
# ==================================================
@api_campaigns_bp.route("/<int:campaign_id>", methods=["GET"])
@jwt_user_required
@business_required
def get_campaign(campaign_id: int):
    campaign = Campaign.query.filter_by(
        id=campaign_id, business_id=g.api_business.id
    ).first()
    if not campaign:
        return err("Campagne introuvable.", None, 404)

    campaign.recalc_counters()
    db.session.commit()

    data = campaign.to_dict()
    data["template"] = campaign.template.to_dict() if campaign.template else None
    data["whatsapp_account"] = (
        campaign.whatsapp_account.to_dict() if campaign.whatsapp_account else None
    )
    return ok(data, "OK", 200)


# ==================================================
# UPDATE
# ==================================================
@api_campaigns_bp.route("/<int:campaign_id>", methods=["PUT", "PATCH"])
@jwt_user_required
@business_required
def update_campaign(campaign_id: int):
    biz = g.api_business
    campaign = Campaign.query.filter_by(
        id=campaign_id, business_id=biz.id
    ).first()
    if not campaign:
        return err("Campagne introuvable.", None, 404)
    if campaign.status in ("running", "completed", "cancelled"):
        return err("Cette campagne ne peut plus être modifiée.", None, 409)

    data = request.get_json(silent=True) or {}

    if "name" in data and data["name"]:
        campaign.name = data["name"].strip()

    if "message" in data:
        campaign.message = (data["message"] or "").strip() or None

    if "template_id" in data:
        tid = data["template_id"]
        if tid:
            tpl = Template.query.filter_by(id=tid, business_id=biz.id).first()
            if not tpl:
                return err("Modèle introuvable.", None, 404)
            campaign.template_id = tpl.id
        else:
            campaign.template_id = None

    if "whatsapp_account_id" in data:
        wid = data["whatsapp_account_id"]
        if wid:
            waba = WhatsAppAccount.query.filter_by(id=wid, business_id=biz.id).first()
            if not waba:
                return err("Compte WhatsApp introuvable.", None, 404)
            campaign.whatsapp_account_id = waba.id
        else:
            campaign.whatsapp_account_id = None

    if "timezone" in data:
        campaign.timezone = data["timezone"] or "UTC"

    if "scheduled_at" in data:
        if data["scheduled_at"]:
            try:
                local_dt = datetime.fromisoformat(data["scheduled_at"])
            except (ValueError, TypeError):
                return err("Format scheduled_at invalide.", None, 422)
            campaign.scheduled_at = to_utc(local_dt, campaign.timezone or "UTC")
        else:
            campaign.scheduled_at = None

    if campaign.status in ("draft", "scheduled"):
        campaign.status = "scheduled" if campaign.scheduled_at else "draft"

    # Contacts ciblés
    if "contact_ids" in data:
        ids = data["contact_ids"] or []
        if not isinstance(ids, list):
            return err("contact_ids doit être une liste.", None, 422)
        contacts = Contact.query.filter(
            Contact.business_id == biz.id,
            Contact.id.in_([int(i) for i in ids if str(i).isdigit()]),
        ).all() if ids else []
        db.session.execute(
            campaign_contacts.delete().where(
                campaign_contacts.c.campaign_id == campaign.id
            )
        )
        for c in contacts:
            db.session.execute(
                campaign_contacts.insert().values(campaign_id=campaign.id, contact_id=c.id)
            )
        campaign.total_contacts = len(contacts)

    db.session.commit()
    log_activity(
        action="api_campaign_update",
        description=f"Campagne modifiée via API : {campaign.name}",
        user_id=g.api_user.id,
    )
    return ok(campaign.to_dict(), "Campagne mise à jour.", 200)


# ==================================================
# DELETE
# ==================================================
@api_campaigns_bp.route("/<int:campaign_id>", methods=["DELETE"])
@jwt_user_required
@business_required
def delete_campaign(campaign_id: int):
    campaign = Campaign.query.filter_by(
        id=campaign_id, business_id=g.api_business.id
    ).first()
    if not campaign:
        return err("Campagne introuvable.", None, 404)
    if campaign.status == "running":
        return err("Impossible de supprimer une campagne en cours.", None, 409)

    name = campaign.name
    db.session.delete(campaign)
    db.session.commit()
    log_activity(
        action="api_campaign_delete",
        description=f"Campagne supprimée via API : {name}",
        user_id=g.api_user.id,
    )
    return ok(None, "Campagne supprimée.", 200)


# ==================================================
# ACTIONS
# ==================================================
@api_campaigns_bp.route("/<int:campaign_id>/start", methods=["POST"])
@jwt_user_required
@business_required
def start_campaign(campaign_id: int):
    campaign = Campaign.query.filter_by(
        id=campaign_id, business_id=g.api_business.id
    ).first()
    if not campaign:
        return err("Campagne introuvable.", None, 404)

    try:
        CampaignService.start(campaign)
        return ok(campaign.to_dict(), "Campagne lancée.", 200)
    except ValueError as e:
        return err(str(e), None, 400)


@api_campaigns_bp.route("/<int:campaign_id>/pause", methods=["POST"])
@jwt_user_required
@business_required
def pause_campaign(campaign_id: int):
    campaign = Campaign.query.filter_by(
        id=campaign_id, business_id=g.api_business.id
    ).first()
    if not campaign:
        return err("Campagne introuvable.", None, 404)
    try:
        CampaignService.pause(campaign)
        return ok(campaign.to_dict(), "Campagne mise en pause.", 200)
    except ValueError as e:
        return err(str(e), None, 400)


@api_campaigns_bp.route("/<int:campaign_id>/resume", methods=["POST"])
@jwt_user_required
@business_required
def resume_campaign(campaign_id: int):
    campaign = Campaign.query.filter_by(
        id=campaign_id, business_id=g.api_business.id
    ).first()
    if not campaign:
        return err("Campagne introuvable.", None, 404)
    try:
        CampaignService.resume(campaign)
        return ok(campaign.to_dict(), "Campagne reprise.", 200)
    except ValueError as e:
        return err(str(e), None, 400)


@api_campaigns_bp.route("/<int:campaign_id>/cancel", methods=["POST"])
@jwt_user_required
@business_required
def cancel_campaign(campaign_id: int):
    campaign = Campaign.query.filter_by(
        id=campaign_id, business_id=g.api_business.id
    ).first()
    if not campaign:
        return err("Campagne introuvable.", None, 404)
    try:
        CampaignService.cancel(campaign)
        return ok(campaign.to_dict(), "Campagne annulée.", 200)
    except ValueError as e:
        return err(str(e), None, 400)