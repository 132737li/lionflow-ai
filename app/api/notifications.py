"""
API REST Notifications.
"""
from flask import Blueprint, request, g

from app.extensions import db
from app.models.notification import Notification
from app.services.notification_service import NotificationService
from app.api._helpers import (
    ok, err, paginate, jwt_user_required,
)


api_notifications_bp = Blueprint("api_notifications", __name__)


@api_notifications_bp.route("", methods=["GET"])
@jwt_user_required
def list_notifications():
    query = Notification.query.filter_by(user_id=g.api_user.id)

    unread_only = request.args.get("unread", "false").lower() == "true"
    if unread_only:
        query = query.filter_by(is_read=False)

    type_filter = (request.args.get("type") or "").strip()
    if type_filter in ("success", "info", "warning", "error"):
        query = query.filter(Notification.type == type_filter)

    query = query.order_by(Notification.created_at.desc())
    page = paginate(query, default_per_page=30)
    return ok(
        {"items": [n.to_dict() for n in page["items"]], "meta": page["meta"]},
        "OK", 200,
    )


@api_notifications_bp.route("/unread_count", methods=["GET"])
@jwt_user_required
def unread_count():
    count = NotificationService.unread_count(g.api_user.id)
    return ok({"count": count}, "OK", 200)


@api_notifications_bp.route("/<int:notif_id>/read", methods=["POST"])
@jwt_user_required
def mark_read(notif_id: int):
    notif = Notification.query.filter_by(
        id=notif_id, user_id=g.api_user.id
    ).first()
    if not notif:
        return err("Notification introuvable.", None, 404)
    notif.mark_read()
    db.session.commit()
    return ok(notif.to_dict(), "Notification marquée comme lue.", 200)


@api_notifications_bp.route("/read-all", methods=["POST"])
@jwt_user_required
def mark_all_read():
    count = NotificationService.mark_all_read(g.api_user.id)
    return ok({"updated": count}, f"{count} notification(s) marquée(s) lue(s).", 200)