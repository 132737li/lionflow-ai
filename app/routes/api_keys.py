"""
Page de gestion des clés API.
La clé en clair est affichée UNE SEULE FOIS à la création.
"""
from flask import (
    Blueprint, render_template, redirect, url_for, flash,
    request, session,
)
from flask_login import login_required, current_user

from app.extensions import db
from app.models.api_key import ApiKey
from app.utils.security import log_activity


api_keys_bp = Blueprint("api_keys", __name__, template_folder="../templates/api_keys")


@api_keys_bp.route("/")
@login_required
def list_keys():
    keys = (
        ApiKey.query
        .filter_by(user_id=current_user.id)
        .order_by(ApiKey.created_at.desc())
        .all()
    )
    # Récupère la clé en clair stockée temporairement en session
    new_key = session.pop("new_api_key", None)

    return render_template("api_keys/list.html", keys=keys, new_key=new_key)


@api_keys_bp.route("/new", methods=["POST"])
@login_required
def create_key():
    name = (request.form.get("name") or "").strip()
    if not name:
        flash("Le nom de la clé est requis.", "danger")
        return redirect(url_for("api_keys.list_keys"))

    api_key, raw = ApiKey.create_for_user(current_user, name)
    db.session.commit()

    # Stocke la clé en clair en session pour l'afficher une fois
    session["new_api_key"] = raw

    log_activity(
        action="api_key_create",
        description=f"Clé API créée : {name}",
    )
    flash("Clé créée. Copiez-la maintenant, elle ne sera plus affichée.", "success")
    return redirect(url_for("api_keys.list_keys"))


@api_keys_bp.route("/<int:key_id>/delete", methods=["POST"])
@login_required
def delete_key(key_id: int):
    key = ApiKey.query.filter_by(id=key_id, user_id=current_user.id).first_or_404()
    name = key.name
    db.session.delete(key)
    db.session.commit()

    log_activity(
        action="api_key_delete",
        description=f"Clé API supprimée : {name}",
    )
    flash(f"Clé « {name} » supprimée.", "info")
    return redirect(url_for("api_keys.list_keys"))