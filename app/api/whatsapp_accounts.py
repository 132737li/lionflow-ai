"""
API REST Comptes WhatsApp.
Les tokens ne sont jamais exposés (uniquement `has_token`).
"""
from datetime import datetime, timezone
from flask import Blueprint, request, g

from app.extensions import db
from app.models.whatsapp_account import WhatsAppAccount
from app.services.whatsapp_service import WhatsAppService
from app.utils.security import log_activity
from app.utils.validators import normalize_phone, validate_required
from app.api._helpers import (
    ok, err, paginate, jwt_user_required, business_required,
)


api_waba_bp = Blueprint("api_waba", __name__)


@api_waba_bp.route("", methods=["GET"])
@jwt_user_required
@business_required
def list_accounts():
    query = WhatsAppAccount.query.filter_by(
        business_id=g.api_business.id
    ).order_by(WhatsAppAccount.created_at.desc())
    page = paginate(query)
    return ok(
        {"items": [a.to_dict() for a in page["items"]], "meta": page["meta"]},
        "OK",
        200,
    )


@api_waba_bp.route("", methods=["POST"])
@jwt_user_required
@business_required
def create_account():
    biz = g.api_business
    data = request.get_json(silent=True) or {}

    missing = validate_required(data, ["name", "phone_number"])
    if missing:
        return err("Champs manquants.", missing, 422)

    if not biz.can_add_whatsapp_account():
        return err(
            f"Quota de comptes WhatsApp atteint pour le plan '{biz.plan}'.",
            None, 403,
        )

    phone = normalize_phone(data["phone_number"])
    if not phone:
        return err("Numéro invalide.", ["Format E.164 requis."], 422)

    account = WhatsAppAccount(
        business_id=biz.id,
        name=data["name"].strip(),
        phone_number=phone,
        phone_number_id=(data.get("phone_number_id") or "").strip() or None,
        business_account_id=(data.get("business_account_id") or "").strip() or None,
        status=data.get("status") or "disconnected",
    )
    if data.get("access_token"):
        account.set_access_token(data["access_token"])
        account.connected_at = datetime.now(timezone.utc)

    db.session.add(account)
    db.session.commit()

    log_activity(
        action="api_waba_create",
        description=f"Compte WhatsApp créé via API : {account.name}",
        user_id=g.api_user.id,
    )
    return ok(account.to_dict(), "Compte WhatsApp créé.", 201)


@api_waba_bp.route("/<int:account_id>", methods=["GET"])
@jwt_user_required
@business_required
def get_account(account_id: int):
    account = WhatsAppAccount.query.filter_by(
        id=account_id, business_id=g.api_business.id
    ).first()
    if not account:
        return err("Compte introuvable.", None, 404)
    return ok(account.to_dict(), "OK", 200)


@api_waba_bp.route("/<int:account_id>", methods=["PUT", "PATCH"])
@jwt_user_required
@business_required
def update_account(account_id: int):
    account = WhatsAppAccount.query.filter_by(
        id=account_id, business_id=g.api_business.id
    ).first()
    if not account:
        return err("Compte introuvable.", None, 404)

    data = request.get_json(silent=True) or {}

    if "name" in data and data["name"]:
        account.name = data["name"].strip()
    if "phone_number" in data and data["phone_number"]:
        phone = normalize_phone(data["phone_number"])
        if not phone:
            return err("Numéro invalide.", None, 422)
        account.phone_number = phone
    if "phone_number_id" in data:
        account.phone_number_id = (data["phone_number_id"] or "").strip() or None
    if "business_account_id" in data:
        account.business_account_id = (data["business_account_id"] or "").strip() or None
    if "status" in data:
        status = data["status"]
        if status in ("disconnected", "connected", "error"):
            account.status = status
    if data.get("access_token"):
        account.set_access_token(data["access_token"])
        account.connected_at = datetime.now(timezone.utc)

    db.session.commit()
    log_activity(
        action="api_waba_update",
        description=f"Compte WhatsApp modifié via API : {account.name}",
        user_id=g.api_user.id,
    )
    return ok(account.to_dict(), "Compte mis à jour.", 200)


@api_waba_bp.route("/<int:account_id>", methods=["DELETE"])
@jwt_user_required
@business_required
def delete_account(account_id: int):
    account = WhatsAppAccount.query.filter_by(
        id=account_id, business_id=g.api_business.id
    ).first()
    if not account:
        return err("Compte introuvable.", None, 404)
    name = account.name
    db.session.delete(account)
    db.session.commit()
    log_activity(
        action="api_waba_delete",
        description=f"Compte WhatsApp supprimé via API : {name}",
        user_id=g.api_user.id,
    )
    return ok(None, "Compte supprimé.", 200)


@api_waba_bp.route("/<int:account_id>/test", methods=["POST"])
@jwt_user_required
@business_required
def test_account(account_id: int):
    account = WhatsAppAccount.query.filter_by(
        id=account_id, business_id=g.api_business.id
    ).first()
    if not account:
        return err("Compte introuvable.", None, 404)

    result = WhatsAppService.test_connection(account)
    if result["success"]:
        account.status = "connected"
        account.connected_at = datetime.now(timezone.utc)
    else:
        account.status = "error"
    db.session.commit()

    return ok(
        {"status": account.status, "details": result},
        "Test effectué.",
        200 if result["success"] else 400,
    )