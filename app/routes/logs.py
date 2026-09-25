"""
Page journal d'activité.
"""
from flask import Blueprint, render_template, request
from flask_login import login_required, current_user

from app.models.log import Log


logs_bp = Blueprint("logs", __name__, template_folder="../templates/logs")


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

    return render_template(
        "logs/list.html",
        logs=pagination.items,
        pagination=pagination,
        actions=actions,
        filter_action=action,
    )