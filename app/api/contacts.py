"""API contacts — stub (à compléter en PARTIE 8)."""
from flask import Blueprint


api_contacts_bp = Blueprint("api_contacts", __name__)

"""
API REST Contacts — CRUD complet.
Toutes les opérations sont filtrées par business_id de l'utilisateur.
"""
from flask import Blueprint, request, g
from sqlalchemy import or_

from app.extensions import db
from app.models.contact import Contact
from app.utils.security import log_activity
from app.utils.validators import (
    is_valid_email, normalize_phone, validate_required,
)
from app.api._helpers import (
    ok, err, paginate, jwt_user_required, business_required,
)


api_contacts_bp = Blueprint("api_contacts", __name__)


# ==================================================
# LIST + SEARCH + FILTERS + PAGINATION
# ==================================================
@api_contacts_bp.route("", methods=["GET"])
@jwt_user_required
@business_required
def list_contacts():
    query = Contact.query.filter_by(business_id=g.api_business.id)

    q = (request.args.get("q") or "").strip()
    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            Contact.first_name.ilike(like),
            Contact.last_name.ilike(like),
            Contact.phone.ilike(like),
            Contact.email.ilike(like),
            Contact.company.ilike(like),
        ))

    status = (request.args.get("status") or "").strip()
    if status in ("active", "inactive", "blocked"):
        query = query.filter(Contact.status == status)

    tag = (request.args.get("tag") or "").strip()
    if tag:
        query = query.filter(Contact.tags.ilike(f"%{tag}%"))

    # Tri
    sort = request.args.get("sort", "created_at")
    order = request.args.get("order", "desc")
    if sort not in ("created_at", "first_name", "last_name", "phone"):
        sort = "created_at"
    col = getattr(Contact, sort)
    query = query.order_by(col.asc() if order == "asc" else col.desc())

    page = paginate(query)
    return ok(
        {"items": [c.to_dict() for c in page["items"]], "meta": page["meta"]},
        "OK",
        200,
    )


# ==================================================
# CREATE
# ==================================================
@api_contacts_bp.route("", methods=["POST"])
@jwt_user_required
@business_required
def create_contact():
    biz = g.api_business
    data = request.get_json(silent=True) or {}

    missing = validate_required(data, ["phone"])
    if missing:
        return err("Champs manquants.", missing, 422)

    # Quota
    if not biz.can_add_contact():
        return err(
            f"Quota de contacts atteint pour le plan '{biz.plan}'.",
            None, 403,
        )

    # Téléphone
    phone = normalize_phone(data["phone"])
    if not phone:
        return err("Numéro invalide.", ["Format E.164 requis."], 422)

    # Doublon
    if Contact.query.filter_by(business_id=biz.id, phone=phone).first():
        return err("Un contact avec ce numéro existe déjà.", None, 409)

    # Email
    email = (data.get("email") or "").strip() or None
    if email and not is_valid_email(email):
        return err("Email invalide.", ["Format incorrect."], 422)

    # Statut
    status = (data.get("status") or "active").strip().lower()
    if status not in ("active", "inactive", "blocked"):
        status = "active"

    contact = Contact(
        business_id=biz.id,
        first_name=(data.get("first_name") or "").strip() or None,
        last_name=(data.get("last_name") or "").strip() or None,
        phone=phone,
        email=email,
        company=(data.get("company") or "").strip() or None,
        status=status,
    )

    # Tags (liste ou CSV)
    tags = data.get("tags")
    if isinstance(tags, list):
        contact.set_tags([str(t).strip() for t in tags if str(t).strip()])
    elif isinstance(tags, str):
        contact.set_tags([t.strip() for t in tags.split(",") if t.strip()])

    db.session.add(contact)
    db.session.commit()

    log_activity(
        action="api_contact_create",
        description=f"Contact créé via API : {contact.full_name} ({contact.phone})",
        user_id=g.api_user.id,
    )
    return ok(contact.to_dict(), "Contact créé.", 201)


# ==================================================
# GET ONE
# ==================================================
@api_contacts_bp.route("/<int:contact_id>", methods=["GET"])
@jwt_user_required
@business_required
def get_contact(contact_id: int):
    contact = Contact.query.filter_by(
        id=contact_id, business_id=g.api_business.id
    ).first()
    if not contact:
        return err("Contact introuvable.", None, 404)
    data = contact.to_dict()
    data["messages_count"] = contact.messages.count()
    return ok(data, "OK", 200)


# ==================================================
# UPDATE
# ==================================================
@api_contacts_bp.route("/<int:contact_id>", methods=["PUT", "PATCH"])
@jwt_user_required
@business_required
def update_contact(contact_id: int):
    biz = g.api_business
    contact = Contact.query.filter_by(
        id=contact_id, business_id=biz.id
    ).first()
    if not contact:
        return err("Contact introuvable.", None, 404)

    data = request.get_json(silent=True) or {}

    if "phone" in data and data["phone"]:
        phone = normalize_phone(data["phone"])
        if not phone:
            return err("Numéro invalide.", ["Format E.164 requis."], 422)
        # Doublon ?
        dup = Contact.query.filter(
            Contact.business_id == biz.id,
            Contact.phone == phone,
            Contact.id != contact.id,
        ).first()
        if dup:
            return err("Un autre contact utilise déjà ce numéro.", None, 409)
        contact.phone = phone

    if "first_name" in data:
        contact.first_name = (data["first_name"] or "").strip() or None
    if "last_name" in data:
        contact.last_name = (data["last_name"] or "").strip() or None
    if "email" in data:
        email = (data["email"] or "").strip() or None
        if email and not is_valid_email(email):
            return err("Email invalide.", ["Format incorrect."], 422)
        contact.email = email
    if "company" in data:
        contact.company = (data["company"] or "").strip() or None
    if "status" in data:
        status = (data["status"] or "").strip().lower()
        if status in ("active", "inactive", "blocked"):
            contact.status = status
    if "tags" in data:
        tags = data["tags"]
        if isinstance(tags, list):
            contact.set_tags([str(t).strip() for t in tags if str(t).strip()])
        elif isinstance(tags, str):
            contact.set_tags([t.strip() for t in tags.split(",") if t.strip()])
        elif tags is None:
            contact.tags = None

    db.session.commit()
    log_activity(
        action="api_contact_update",
        description=f"Contact modifié via API : {contact.full_name}",
        user_id=g.api_user.id,
    )
    return ok(contact.to_dict(), "Contact mis à jour.", 200)


# ==================================================
# DELETE
# ==================================================
@api_contacts_bp.route("/<int:contact_id>", methods=["DELETE"])
@jwt_user_required
@business_required
def delete_contact(contact_id: int):
    contact = Contact.query.filter_by(
        id=contact_id, business_id=g.api_business.id
    ).first()
    if not contact:
        return err("Contact introuvable.", None, 404)

    name = contact.full_name
    db.session.delete(contact)
    db.session.commit()

    log_activity(
        action="api_contact_delete",
        description=f"Contact supprimé via API : {name}",
        user_id=g.api_user.id,
    )
    return ok(None, "Contact supprimé.", 200)