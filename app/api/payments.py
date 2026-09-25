"""
API REST Paiements (lecture seule côté client).
"""
from flask import Blueprint, g

from app.models.payment import Payment
from app.api._helpers import (
    ok, err, paginate, jwt_user_required, business_required,
)


api_payments_bp = Blueprint("api_payments", __name__)


@api_payments_bp.route("", methods=["GET"])
@jwt_user_required
@business_required
def list_payments():
    query = Payment.query.filter_by(
        business_id=g.api_business.id
    ).order_by(Payment.created_at.desc())
    page = paginate(query)
    return ok(
        {"items": [p.to_dict() for p in page["items"]], "meta": page["meta"]},
        "OK", 200,
    )


@api_payments_bp.route("/<int:payment_id>", methods=["GET"])
@jwt_user_required
@business_required
def get_payment(payment_id: int):
    p = Payment.query.filter_by(
        id=payment_id, business_id=g.api_business.id
    ).first()
    if not p:
        return err("Paiement introuvable.", None, 404)
    return ok(p.to_dict(), "OK", 200)