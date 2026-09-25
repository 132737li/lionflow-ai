"""API templates — stub (à compléter en PARTIE 8)."""
from flask import Blueprint


api_templates_bp = Blueprint("api_templates", __name__)

"""
API REST Modèles de messages.
"""
from flask import Blueprint, request, g
from sqlalchemy import or_

from app.extensions import db
from app.models.template import Template
from app.utils.security import log_activity
from app.utils.validators import validate_required
from app.api._helpers import (
    ok, err, paginate, jwt_user_required, business_required,
)


api_templates_bp = Blueprint("api_templates", __name__)


@api_templates_bp.route("", methods=["GET"])
@jwt_user_required
@business_required
def list_templates():
    query = Template.query.filter_by(business_id=g.api_business.id)
    q = (request.args.get("q") or "").strip()
    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            Template.name.ilike(like),
            Template.content.ilike(like),
        ))
    category = (request.args.get("category") or "").strip()
    if category:
        query = query.filter(Template.category == category)

    query = query.order_by(Template.created_at.desc())
    page = paginate(query)
    return ok(
        {"items": [t.to_dict() for t in page["items"]], "meta": page["meta"]},
        "OK",
        200,
    )


@api_templates_bp.route("", methods=["POST"])
@jwt_user_required
@business_required
def create_template():
    data = request.get_json(silent=True) or {}
    missing = validate_required(data, ["name", "content"])
    if missing:
        return err("Champs manquants.", missing, 422)

    tpl = Template(
        business_id=g.api_business.id,
        name=data["name"].strip(),
        content=data["content"].strip(),
        category=(data.get("category") or "general").strip(),
        language=(data.get("language") or "fr").strip(),
    )
    db.session.add(tpl)
    db.session.commit()

    log_activity(
        action="api_template_create",
        description=f"Modèle créé via API : {tpl.name}",
        user_id=g.api_user.id,
    )
    return ok(tpl.to_dict(), "Modèle créé.", 201)


@api_templates_bp.route("/<int:template_id>", methods=["GET"])
@jwt_user_required
@business_required
def get_template(template_id: int):
    tpl = Template.query.filter_by(
        id=template_id, business_id=g.api_business.id
    ).first()
    if not tpl:
        return err("Modèle introuvable.", None, 404)
    data = tpl.to_dict()
    data["usage_count"] = tpl.campaigns.count()
    return ok(data, "OK", 200)


@api_templates_bp.route("/<int:template_id>", methods=["PUT", "PATCH"])
@jwt_user_required
@business_required
def update_template(template_id: int):
    tpl = Template.query.filter_by(
        id=template_id, business_id=g.api_business.id
    ).first()
    if not tpl:
        return err("Modèle introuvable.", None, 404)

    data = request.get_json(silent=True) or {}
    if "name" in data and data["name"]:
        tpl.name = data["name"].strip()
    if "content" in data and data["content"]:
        tpl.content = data["content"].strip()
    if "category" in data:
        tpl.category = (data["category"] or "general").strip()
    if "language" in data:
        tpl.language = (data["language"] or "fr").strip()

    db.session.commit()
    log_activity(
        action="api_template_update",
        description=f"Modèle modifié via API : {tpl.name}",
        user_id=g.api_user.id,
    )
    return ok(tpl.to_dict(), "Modèle mis à jour.", 200)


@api_templates_bp.route("/<int:template_id>", methods=["DELETE"])
@jwt_user_required
@business_required
def delete_template(template_id: int):
    tpl = Template.query.filter_by(
        id=template_id, business_id=g.api_business.id
    ).first()
    if not tpl:
        return err("Modèle introuvable.", None, 404)
    name = tpl.name
    db.session.delete(tpl)
    db.session.commit()
    log_activity(
        action="api_template_delete",
        description=f"Modèle supprimé via API : {name}",
        user_id=g.api_user.id,
    )
    return ok(None, "Modèle supprimé.", 200)