"""
Routes API REST d'authentification — JWT.
Format de réponse : { success, message, data, errors }.
"""
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    create_access_token, jwt_required,
    get_jwt_identity, get_jwt,
)

from app.extensions import db
from app.models.user import User
from app.services.auth_service import AuthService, AuthError
from app.utils.validators import validate_required, is_valid_email, validate_password_strength
from app.utils.security import log_activity


api_auth_bp = Blueprint("api_auth", __name__)


# --------------------------------------------------
# Helpers de réponse
# --------------------------------------------------
def ok(data=None, message="OK", status=200):
    return jsonify(success=True, message=message, data=data, errors=[]), status


def err(message="Erreur", errors=None, status=400):
    return jsonify(success=False, message=message, data=None, errors=errors or []), status


def _user_identity(user: User) -> dict:
    return {"id": user.id, "email": user.email, "role": user.role}


# --------------------------------------------------
# REGISTER
# --------------------------------------------------
@api_auth_bp.route("/register", methods=["POST"])
def api_register():
    data = request.get_json(silent=True) or {}

    missing = validate_required(data, ["email", "password", "first_name", "last_name"])
    if missing:
        return err("Champs manquants.", missing, 422)

    if not is_valid_email(data["email"]):
        return err("Email invalide.", ["Format d'email incorrect."], 422)

    pwd_errors = validate_password_strength(data["password"])
    if pwd_errors:
        return err("Mot de passe trop faible.", pwd_errors, 422)

    try:
        user = AuthService.register({
            "email": data["email"],
            "password": data["password"],
            "first_name": data.get("first_name"),
            "last_name": data.get("last_name"),
        })
        return ok(user.to_dict(), "Compte créé.", 201)
    except AuthError as e:
        return err(e.message, [e.message], e.code)


# --------------------------------------------------
# LOGIN
# --------------------------------------------------
@api_auth_bp.route("/login", methods=["POST"])
def api_login():
    data = request.get_json(silent=True) or {}
    missing = validate_required(data, ["email", "password"])
    if missing:
        return err("Champs manquants.", missing, 422)

    try:
        user = AuthService.authenticate(data["email"], data["password"])
    except AuthError as e:
        return err(e.message, [e.message], e.code)

    access = create_access_token(
        identity=str(user.id),
        additional_claims={"role": user.role, "email": user.email},
    )
    return ok(
        {
            "access_token": access,
            "token_type": "Bearer",
            "user": user.to_dict(),
        },
        "Connexion réussie.",
        200,
    )


# --------------------------------------------------
# ME
# --------------------------------------------------
@api_auth_bp.route("/me", methods=["GET"])
@jwt_required()
def api_me():
    user_id = int(get_jwt_identity())
    user = db.session.get(User, user_id)
    if not user or not user.is_active:
        return err("Utilisateur introuvable ou inactif.", None, 401)
    return ok(user.to_dict(include_private=True), "OK", 200)


# --------------------------------------------------
# LOGOUT (côté client principalement — liste noire optionnelle)
# --------------------------------------------------
@api_auth_bp.route("/logout", methods=["POST"])
@jwt_required()
def api_logout():
    user_id = int(get_jwt_identity())
    user = db.session.get(User, user_id)
    if user:
        log_activity(
            action="api_logout",
            description=f"Déconnexion API : {user.email}",
            user_id=user.id,
        )
    # En JWT stateless, la déconnexion est côté client.
    # Pour une vraie révocation, implémenter une blocklist (Redis).
    return ok(None, "Déconnecté.", 200)


# --------------------------------------------------
# CHANGE PASSWORD
# --------------------------------------------------
@api_auth_bp.route("/change-password", methods=["POST"])
@jwt_required()
def api_change_password():
    data = request.get_json(silent=True) or {}
    missing = validate_required(data, ["current_password", "new_password"])
    if missing:
        return err("Champs manquants.", missing, 422)

    user_id = int(get_jwt_identity())
    user = db.session.get(User, user_id)
    if not user:
        return err("Utilisateur introuvable.", None, 404)

    try:
        AuthService.change_password(user, data["current_password"], data["new_password"])
        return ok(None, "Mot de passe modifié.", 200)
    except AuthError as e:
        return err(e.message, [e.message], e.code)
    
    """
API d'authentification — JWT.
"""
from datetime import datetime, timezone
from flask import Blueprint, request
from flask_jwt_extended import (
    create_access_token, jwt_required, get_jwt_identity, get_jwt,
)

from app.extensions import db
from app.models.user import User
from app.services.auth_service import AuthService, AuthError
from app.utils.validators import (
    validate_required, is_valid_email, validate_password_strength,
)
from app.utils.security import log_activity
from app.api._helpers import ok, err, jwt_user_required


api_auth_bp = Blueprint("api_auth", __name__)


# ==================================================
# REGISTER
# ==================================================
@api_auth_bp.route("/register", methods=["POST"])
def api_register():
    data = request.get_json(silent=True) or {}

    missing = validate_required(data, ["email", "password", "first_name", "last_name"])
    if missing:
        return err("Champs manquants.", missing, 422)

    if not is_valid_email(data["email"]):
        return err("Email invalide.", ["Format d'email incorrect."], 422)

    pwd_errors = validate_password_strength(data["password"])
    if pwd_errors:
        return err("Mot de passe trop faible.", pwd_errors, 422)

    try:
        user = AuthService.register({
            "email": data["email"],
            "password": data["password"],
            "first_name": data.get("first_name"),
            "last_name": data.get("last_name"),
        })
        return ok(user.to_dict(), "Compte créé.", 201)
    except AuthError as e:
        return err(e.message, [e.message], e.code)


# ==================================================
# LOGIN
# ==================================================
@api_auth_bp.route("/login", methods=["POST"])
def api_login():
    data = request.get_json(silent=True) or {}
    missing = validate_required(data, ["email", "password"])
    if missing:
        return err("Champs manquants.", missing, 422)

    try:
        user = AuthService.authenticate(data["email"], data["password"])
    except AuthError as e:
        return err(e.message, [e.message], e.code)

    access = create_access_token(
        identity=str(user.id),
        additional_claims={"role": user.role, "email": user.email},
    )
    return ok(
        {
            "access_token": access,
            "token_type": "Bearer",
            "user": user.to_dict(),
        },
        "Connexion réussie.",
        200,
    )


# ==================================================
# ME
# ==================================================
@api_auth_bp.route("/me", methods=["GET"])
@jwt_user_required
def api_me():
    from flask import g
    return ok(g.api_user.to_dict(include_private=True), "OK", 200)


# ==================================================
# LOGOUT (stateless)
# ==================================================
@api_auth_bp.route("/logout", methods=["POST"])
@jwt_required()
def api_logout():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    if user:
        log_activity(
            action="api_logout",
            description=f"Déconnexion API : {user.email}",
            user_id=user.id,
        )
    return ok(None, "Déconnecté.", 200)


# ==================================================
# CHANGE PASSWORD
# ==================================================
@api_auth_bp.route("/change-password", methods=["POST"])
@jwt_user_required
def api_change_password():
    from flask import g
    data = request.get_json(silent=True) or {}
    missing = validate_required(data, ["current_password", "new_password"])
    if missing:
        return err("Champs manquants.", missing, 422)

    try:
        AuthService.change_password(
            g.api_user, data["current_password"], data["new_password"],
        )
        return ok(None, "Mot de passe modifié.", 200)
    except AuthError as e:
        return err(e.message, [e.message], e.code)