"""Routes notifications — stub (à compléter en PARTIE 9)."""
from flask import Blueprint, render_template
from flask_login import login_required


notifications_bp = Blueprint("notifications", __name__, template_folder="../templates/notifications")


@notifications_bp.route("/")
@login_required
def list_notifications():
    return render_template("_placeholder.html", title="Notifications", icon="bell")

"""
Page notifications : liste, filtre, marquage lu.
"""
from flask import (
    Blueprint, render_template, redirect, url_for, flash, request,
)
from flask_login import login_required, current_user

from app.extensions import db
from app.models.notification import Notification
from app.services.notification_service import NotificationService


notifications_bp = Blueprint("notifications", __name__,
                              template_folder="../templates/notifications")


@notifications_bp.route("/")
@login_required
def list_notifications():
    unread = request.args.get("unread") == "1"
    type_filter = (request.args.get("type") or "").strip()
    page = request.args.get("page", 1, type=int)

    query = Notification.query.filter_by(user_id=current_user.id)
    if unread:
        query = query.filter_by(is_read=False)
    if type_filter in ("success", "info", "warning", "error"):
        query = query.filter(Notification.type == type_filter)

    pagination = query.order_by(Notification.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )

    unread_count = NotificationService.unread_count(current_user.id)

    return render_template(
        "notifications/list.html",
        notifications=pagination.items,
        pagination=pagination,
        unread_count=unread_count,
        filter_unread=unread,
        filter_type=type_filter,
    )


@notifications_bp.route("/<int:notif_id>/read", methods=["POST"])
@login_required
def mark_read(notif_id: int):
    notif = Notification.query.filter_by(
        id=notif_id, user_id=current_user.id
    ).first_or_404()
    notif.mark_read()
    db.session.commit()
    if notif.link:
        return redirect(notif.link)
    return redirect(url_for("notifications.list_notifications"))


@notifications_bp.route("/read-all", methods=["POST"])
@login_required
def mark_all_read():
    count = NotificationService.mark_all_read(current_user.id)
    flash(f"{count} notification(s) marquée(s) comme lue(s).", "success")
    return redirect(url_for("notifications.list_notifications"))


@notifications_bp.route("/<int:notif_id>/delete", methods=["POST"])
@login_required
def delete_notification(notif_id: int):
    notif = Notification.query.filter_by(
        id=notif_id, user_id=current_user.id
    ).first_or_404()
    db.session.delete(notif)
    db.session.commit()
    return redirect(url_for("notifications.list_notifications"))