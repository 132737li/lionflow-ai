"""
API REST Clés d'API.
La clé en clair n'est retournée qu'à la création.
"""
from flask import Blueprint, request, g

from app.extensions import db
from app.models.api_key import ApiKey
from app.utils.security import log_activity
from app.utils.validators import validate_required
from app.api._helpers import ok, err, jwt_user_required, paginate


api_keys_bp = Blueprint("api_api_keys", __name__)


@api_keys_bp.route("", methods=["GET"])
@jwt_user_required
def list_keys():
    query = ApiKey.query.filter_by(user_id=g.api_user.id).order_by(ApiKey.created_at.desc())
    page = paginate(query)
    return ok(
        {"items": [k.to_dict() for k in page["items"]], "meta": page["meta"]},
        "OK", 200,
    )


@api_keys_bp.route("", methods=["POST"])
@jwt_user_required
def create_key():
    data = request.get_json(silent=True) or {}
    missing = validate_required(data, ["name"])
    if missing:
        return err("Champs manquants.", missing, 422)

    api_key, raw = ApiKey.create_for_user(g.api_user, data["name"].strip())
    db.session.commit()

    log_activity(
        action="api_key_create",
        description=f"Clé API créée : {api_key.name}",
        user_id=g.api_user.id,
    )
    return ok(
        api_key.to_dict(include_raw=raw),
        "Clé créée. Conservez-la, elle ne sera plus affichée.",
        201,
    )


@api_keys_bp.route("/<int:key_id>", methods=["DELETE"])
@jwt_user_required
def delete_key(key_id: int):
    key = ApiKey.query.filter_by(id=key_id, user_id=g.api_user.id).first()
    if not key:
        return err("Clé introuvable.", None, 404)
    name = key.name
    db.session.delete(key)
    db.session.commit()
    log_activity(
        action="api_key_delete",
        description=f"Clé API supprimée : {name}",
        user_id=g.api_user.id,
    )
    return ok(None, "Clé supprimée.", 200)