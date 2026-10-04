"""
Page journal d'activité.
Suppression d'une entrée ou de tout le journal.
"""
from flask import (
    Blueprint, render_template, request, redirect, url_for, flash,
)
from flask_login import login_required, current_user

from app.extensions import db
from app.models.log import Log
from app.utils.security import log_activity


logs_bp = Blueprint("logs", __name__, template_folder="../templates/logs")


# ==================================================
# LISTE
# ==================================================
@logs_bp.route("/")
@login_required
def list_logs():
    action = (request.args.get("action") or "").strip()
    page = request.args.get("page", 1, type=int)

    query = Log.query.filter_by(user_id=current_user.id)
    if action:
        query = query.filter(Log.action.ilike(f"%{action}%"))

    pagination = query.order_by(Log.created_at.desc()).paginate(
        page=page, per_page=50, error_out=False
    )

    # Liste des actions distinctes pour le filtre
    actions = [
        row[0] for row in
        Log.query.with_entities(Log.action)
        .filter(Log.user_id == current_user.id)
        .distinct()
        .order_by(Log.action)
        .all()
    ]

    # Nombre total de logs pour cet utilisateur
    total_logs = Log.query.filter_by(user_id=current_user.id).count()

    return render_template(
        "logs/list.html",
        logs=pagination.items,
        pagination=pagination,
        actions=actions,
        filter_action=action,
        total_logs=total_logs,
    )


# ==================================================
# SUPPRIMER UNE ENTRÉE
# ==================================================
@logs_bp.route("/<int:log_id>/delete", methods=["POST"])
@login_required
def delete_log(log_id: int):
    """Supprime une entrée de log (uniquement celle de l'utilisateur)."""
    log = Log.query.filter_by(
        id=log_id, user_id=current_user.id
    ).first_or_404()

    db.session.delete(log)
    db.session.commit()

    flash("Entrée supprimée du journal.", "info")
    return redirect(url_for("logs.list_logs"))


# ==================================================
# SUPPRIMER TOUT LE JOURNAL
# ==================================================
@logs_bp.route("/delete-all", methods=["POST"])
@login_required
def delete_all_logs():
    """Supprime toutes les entrées de log de l'utilisateur."""
    count = (
        Log.query
        .filter_by(user_id=current_user.id)
        .delete(synchronize_session=False)
    )
    db.session.commit()

    # On ajoute une nouvelle entrée pour tracer cette action
    log_activity(
        action="logs_cleared",
        description=f"{count} entrée(s) supprimée(s) du journal",
    )

    flash(f"{count} entrée(s) supprimée(s) du journal.", "success")
    return redirect(url_for("logs.list_logs"))