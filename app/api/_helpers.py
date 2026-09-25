"""
Helpers communs à toutes les routes API :
- réponses unifiées
- pagination
- validation JWT + utilisateur
- récupération du business courant
"""
from functools import wraps
from flask import jsonify, request, g
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

from app.extensions import db
from app.models.user import User
from app.models.business import Business


# ==================================================
# RÉPONSES UNIFIÉES
# ==================================================
def ok(data=None, message="OK", status=200, meta=None):
    payload = {"success": True, "message": message, "data": data, "errors": []}
    if meta is not None:
        if isinstance(payload["data"], dict):
            payload["data"].setdefault("meta", meta)
        else:
            payload["data"] = {"items": data, "meta": meta}
    return jsonify(payload), status


def err(message="Erreur", errors=None, status=400, data=None):
    if isinstance(errors, str):
        errors = [errors]
    return jsonify({
        "success": False,
        "message": message,
        "data": data,
        "errors": errors or [],
    }), status


def validation_err(field_errors: dict):
    """422 pour erreurs de validation par champ."""
    flat = []
    for field, msgs in field_errors.items():
        if isinstance(msgs, list):
            for m in msgs:
                flat.append(f"{field}: {m}")
        else:
            flat.append(f"{field}: {msgs}")
    return err("Données invalides.", flat, 422)


# ==================================================
# PAGINATION
# ==================================================
def paginate(query, default_per_page=20, max_per_page=100):
    page = max(request.args.get("page", 1, type=int), 1)
    per_page = min(
        max(request.args.get("per_page", default_per_page, type=int), 1),
        max_per_page,
    )
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    return {
        "items": pagination.items,
        "meta": {
            "page": pagination.page,
            "per_page": pagination.per_page,
            "total": pagination.total,
            "pages": pagination.pages,
            "has_prev": pagination.has_prev,
            "has_next": pagination.has_next,
            "prev_num": pagination.prev_num,
            "next_num": pagination.next_num,
        },
    }


# ==================================================
# AUTH
# ==================================================
def current_api_user() -> User | None:
    """Retourne l'utilisateur à partir du JWT, ou None."""
    try:
        uid = get_jwt_identity()
        if uid is None:
            return None
        return db.session.get(User, int(uid))
    except Exception:
        return None


def jwt_user_required(fn):
    """Décorateur : exige un JWT valide + utilisateur actif."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        verify_jwt_in_request()
        user = current_api_user()
        if not user or not user.is_active:
            return err("Non authentifié ou compte inactif.", None, 401)
        g.api_user = user
        return fn(*args, **kwargs)
    return wrapper


def jwt_admin_required(fn):
    """Décorateur : exige un JWT + rôle admin."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        verify_jwt_in_request()
        user = current_api_user()
        if not user or not user.is_active:
            return err("Non authentifié.", None, 401)
        if user.role != "admin":
            return err("Accès refusé — rôle admin requis.", None, 403)
        g.api_user = user
        return fn(*args, **kwargs)
    return wrapper


def current_business(business_id: int | None = None) -> Business | None:
    """
    Retourne l'entreprise demandée si l'utilisateur y a accès,
    sinon la première entreprise de l'utilisateur.
    """
    user = getattr(g, "api_user", None)
    if not user:
        return None
    if business_id:
        return Business.query.filter_by(id=business_id, owner_id=user.id).first()
    biz_id = request.args.get("business_id", type=int)
    if biz_id:
        b = Business.query.filter_by(id=biz_id, owner_id=user.id).first()
        if b:
            return b
    return Business.query.filter_by(owner_id=user.id).first()


def business_required(fn):
    """Injecte g.api_business ou renvoie 403."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        biz = current_business()
        if not biz:
            return err(
                "Aucune entreprise associée. Créez-en une d'abord.",
                None,
                403,
            )
        g.api_business = biz
        return fn(*args, **kwargs)
    return wrapper


# ==================================================
# SERIALISATION
# ==================================================
def page_response(items, meta, serializer, message="OK"):
    """Sérialise une liste paginée avec son meta."""
    return ok(
        {"items": [serializer(i) for i in items], "meta": meta},
        message,
        200,
    )