"""
API REST Logs d'activité.
"""
from flask import Blueprint, request, g

from app.models.log import Log
from app.api._helpers import ok, paginate, jwt_user_required


api_logs_bp = Blueprint("api_logs", __name__)


@api_logs_bp.route("", methods=["GET"])
@jwt_user_required
def list_logs():
    query = Log.query.filter_by(user_id=g.api_user.id)

    action = (request.args.get("action") or "").strip()
    if action:
        query = query.filter(Log.action.ilike(f"%{action}%"))

    query = query.order_by(Log.created_at.desc())
    page = paginate(query, default_per_page=50)
    return ok(
        {"items": [l.to_dict() for l in page["items"]], "meta": page["meta"]},
        "OK", 200,
    )