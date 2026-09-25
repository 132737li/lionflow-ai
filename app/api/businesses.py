"""
CRUD entreprises via API.
"""
from flask import Blueprint, request

from app.extensions import db
from app.models.business import Business
from app.models.subscription import Subscription
from app.utils.security import log_activity
from app.utils.validators import is_valid_email, normalize_phone, validate_required
from app.api._helpers import (
    ok, err, paginate, jwt_user_required, business_required,
)


api_businesses_bp = Blueprint("api_businesses", __name__)


def _serialize(biz: Business) -> dict:
    return biz.to_dict()


# ==================================================
# LIST
# ==================================================
@api_businesses_bp.route("", methods=["GET"])
@jwt_user_required
def list_businesses():
    from flask import g
    q = Business.query.filter_by(owner_id=g.api_user.id).order_by(Business.created_at.desc())
    page = paginate(q)
    return ok(
        {"items": [_serialize(b) for b in page["items"]], "meta": page["meta"]},
        "OK",
        200,
    )


# ==================================================
# CREATE
# ==================================================
@api_businesses_bp.route("", methods=["POST"])
@jwt_user_required
def create_business():
    from flask import g
    data = request.get_json(silent=True) or {}
    missing = validate_required(data, ["name"])
    if missing:
        return err("Champs manquants.", missing, 422)

    email = (data.get("email") or "").strip() or None
    if email and not is_valid_email(email):
        return err("Email invalide.", ["Format d'email incorrect."], 422)

    phone = (data.get("phone") or "").strip() or None
    if phone:
        normalized = normalize_phone(phone)
        if not normalized:
            return err("Téléphone invalide.", ["Format international requis."], 422)
        phone = normalized

    biz = Business(
        owner_id=g.api_user.id,
        name=data["name"].strip(),
        email=email,
        phone=phone,
        address=(data.get("address") or "").strip() or None,
        country=(data.get("country") or "").strip() or None,
    )
    db.session.add(biz)
    db.session.flush()

    # Abonnement Free par défaut
    sub = Subscription(business_id=biz.id, plan="free", status="active")
    db.session.add(sub)
    db.session.commit()

    log_activity(
        action="api_business_create",
        description=f"Business créé via API : {biz.name}",
        user_id=g.api_user.id,
    )
    return ok(_serialize(biz), "Entreprise créée.", 201)


# ==================================================
# GET ONE
# ==================================================
@api_businesses_bp.route("/<int:business_id>", methods=["GET"])
@jwt_user_required
def get_business(business_id: int):
    from flask import g
    biz = Business.query.filter_by(id=business_id, owner_id=g.api_user.id).first()
    if not biz:
        return err("Entreprise introuvable.", None, 404)
    return ok(_serialize(biz), "OK", 200)


# ==================================================
# UPDATE
# ==================================================
@api_businesses_bp.route("/<int:business_id>", methods=["PUT", "PATCH"])
@jwt_user_required
def update_business(business_id: int):
    from flask import g
    biz = Business.query.filter_by(id=business_id, owner_id=g.api_user.id).first()
    if not biz:
        return err("Entreprise introuvable.", None, 404)

    data = request.get_json(silent=True) or {}
    if "name" in data and data["name"]:
        biz.name = data["name"].strip()
    if "email" in data:
        email = (data["email"] or "").strip() or None
        if email and not is_valid_email(email):
            return err("Email invalide.", ["Format d'email incorrect."], 422)
        biz.email = email
    if "phone" in data:
        phone = (data["phone"] or "").strip() or None
        if phone:
            normalized = normalize_phone(phone)
            if not normalized:
                return err("Téléphone invalide.", ["Format international requis."], 422)
            phone = normalized
        biz.phone = phone
    if "address" in data:
        biz.address = (data["address"] or "").strip() or None
    if "country" in data:
        biz.country = (data["country"] or "").strip() or None

    db.session.commit()
    log_activity(
        action="api_business_update",
        description=f"Business modifié via API : {biz.name}",
        user_id=g.api_user.id,
    )
    return ok(_serialize(biz), "Entreprise mise à jour.", 200)


# ==================================================
# DELETE
# ==================================================
@api_businesses_bp.route("/<int:business_id>", methods=["DELETE"])
@jwt_user_required
def delete_business(business_id: int):
    from flask import g
    biz = Business.query.filter_by(id=business_id, owner_id=g.api_user.id).first()
    if not biz:
        return err("Entreprise introuvable.", None, 404)

    name = biz.name
    db.session.delete(biz)
    db.session.commit()

    log_activity(
        action="api_business_delete",
        description=f"Business supprimé via API : {name}",
        user_id=g.api_user.id,
    )
    return ok(None, "Entreprise supprimée.", 200)