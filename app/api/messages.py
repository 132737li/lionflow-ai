"""API messages — stub (à compléter en PARTIE 8)."""
from flask import Blueprint


api_messages_bp = Blueprint("api_messages", __name__)

"""
API REST Messages — lecture seule (les messages sont créés par les campagnes).
"""
from flask import Blueprint, request, g

from app.extensions import db
from app.models.message import Message
from app.models.campaign import Campaign
from app.api._helpers import (
    ok, err, paginate, jwt_user_required, business_required,
)


api_messages_bp = Blueprint("api_messages", __name__)


@api_messages_bp.route("", methods=["GET"])
@jwt_user_required
@business_required
def list_messages():
    query = (
        Message.query
        .join(Campaign, Message.campaign_id == Campaign.id)
        .filter(Campaign.business_id == g.api_business.id)
    )

    status = (request.args.get("status") or "").strip()
    if status in ("pending", "sent", "delivered", "read", "failed"):
        query = query.filter(Message.status == status)

    campaign_id = request.args.get("campaign_id", type=int)
    if campaign_id:
        query = query.filter(Message.campaign_id == campaign_id)

    contact_id = request.args.get("contact_id", type=int)
    if contact_id:
        query = query.filter(Message.contact_id == contact_id)

    query = query.order_by(Message.created_at.desc())
    page = paginate(query, default_per_page=30)

    items = []
    for m in page["items"]:
        d = m.to_dict()
        d["contact_name"] = m.contact.full_name if m.contact else None
        d["contact_phone"] = m.contact.phone if m.contact else None
        d["campaign_name"] = m.campaign.name if m.campaign else None
        items.append(d)

    return ok({"items": items, "meta": page["meta"]}, "OK", 200)


@api_messages_bp.route("/<int:message_id>", methods=["GET"])
@jwt_user_required
@business_required
def get_message(message_id: int):
    message = (
        Message.query
        .join(Campaign, Message.campaign_id == Campaign.id)
        .filter(
            Message.id == message_id,
            Campaign.business_id == g.api_business.id,
        )
        .first()
    )
    if not message:
        return err("Message introuvable.", None, 404)

    data = message.to_dict()
    data["contact"] = message.contact.to_dict() if message.contact else None
    data["campaign"] = message.campaign.to_dict() if message.campaign else None
    return ok(data, "OK", 200)