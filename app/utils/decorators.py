"""
Décorateurs d'autorisation.
- role_required : restreint à un ou plusieurs rôles ('admin', 'user')
- business_required : vérifie que l'utilisateur a au moins une entreprise
- require_business : injecte l'entreprise active et vérifie l'appartenance
"""
from functools import wraps
from flask import abort, g, current_app
from flask_login import current_user

from app.models.business import Business


def role_required(*roles):
    """Restreint l'accès aux utilisateurs ayant un des rôles fournis."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)
            if current_user.role not in roles:
                abort(403)
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def admin_required(fn):
    return role_required("admin")(fn)


def business_required(fn):
    """Vérifie que l'utilisateur a au moins une entreprise."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)
        if not current_user.businesses:
            abort(403)
        return fn(*args, **kwargs)
    return wrapper


def get_current_business() -> Business | None:
    """
    Récupère l'entreprise active depuis la session,
    ou la première entreprise de l'utilisateur.
    Stocke le résultat dans g.current_business.
    """
    from flask import session
    if hasattr(g, "current_business") and g.current_business:
        return g.current_business

    business_id = session.get("active_business_id")
    biz = None
    if business_id:
        biz = Business.query.filter_by(
            id=business_id, owner_id=current_user.id
        ).first()
    if not biz and current_user.is_authenticated:
        biz = Business.query.filter_by(owner_id=current_user.id).first()
        if biz:
            session["active_business_id"] = biz.id

    g.current_business = biz
    return biz


def require_business(fn):
    """
    Injecte l'entreprise active dans g.current_business et
    refuse si absente.
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)
        biz = get_current_business()
        if not biz:
            abort(403)
        return fn(*args, **kwargs)
    return wrapper