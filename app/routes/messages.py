"""Routes messages — stub (à compléter en PARTIE 6)."""
from flask import Blueprint, render_template
from flask_login import login_required


messages_bp = Blueprint("messages", __name__, template_folder="../templates/messages")


@messages_bp.route("/")
@login_required
def list_messages():
    return render_template("_placeholder.html", title="Messages", icon="envelope")

"""
Liste et consultation des messages.
Filtres par statut, campagne, contact.
"""
from flask import Blueprint, render_template, request
from flask_login import login_required

from app.extensions import db
from app.models.message import Message
from app.models.campaign import Campaign
from app.utils.decorators import require_business, get_current_business


messages_bp = Blueprint("messages", __name__, template_folder="../templates/messages")


@messages_bp.route("/")
@login_required
@require_business
def list_messages():
    business = get_current_business()
    status = (request.args.get("status") or "").strip()
    campaign_id = request.args.get("campaign_id", type=int)
    page = request.args.get("page", 1, type=int)
    per_page = 30

    query = (
        Message.query
        .join(Campaign, Message.campaign_id == Campaign.id)
        .filter(Campaign.business_id == business.id)
    )
    if status:
        query = query.filter(Message.status == status)
    if campaign_id:
        query = query.filter(Message.campaign_id == campaign_id)

    pagination = query.order_by(Message.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    status_counts = dict(
        db.session.query(Message.status, db.func.count(Message.id))
        .join(Campaign, Message.campaign_id == Campaign.id)
        .filter(Campaign.business_id == business.id)
        .group_by(Message.status)
        .all()
    )

    campaigns = (
        Campaign.query
        .filter_by(business_id=business.id)
        .order_by(Campaign.name)
        .all()
    )

    return render_template(
        "messages/list.html",
        messages=pagination.items,
        pagination=pagination,
        business=business,
        status_filter=status,
        campaign_filter=campaign_id,
        campaigns=campaigns,
        status_counts=status_counts,
    )