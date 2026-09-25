"""
API REST Abonnements.
"""
from datetime import datetime, timezone
from flask import Blueprint, request, g

from app.extensions import db
from app.models.subscription import Subscription
from app.utils.security import log_activity
from app.api._helpers import (
    ok, err, paginate, jwt_user_required, business_required,
)


api_subscriptions_bp = Blueprint("api_subscriptions", __name__)


@api_subscriptions_bp.route("", methods=["GET"])
@jwt_user_required
@business_required
def list_subscriptions():
    query = Subscription.query.filter_by(
        business_id=g.api_business.id
    ).order_by(Subscription.created_at.desc())
    page = paginate(query)
    return ok(
        {"items": [s.to_dict() for s in page["items"]], "meta": page["meta"]},
        "OK", 200,
    )


@api_subscriptions_bp.route("/current", methods=["GET"])
@jwt_user_required
@business_required
def current():
    biz = g.api_business
    sub = biz.subscription
    from flask import current_app
    plans = current_app.config.get("PLANS", {})
    return ok(
        {
            "subscription": sub.to_dict() if sub else None,
            "plan_config": biz.plan_config,
            "available_plans": plans,
        },
        "OK", 200,
    )


@api_subscriptions_bp.route("/change", methods=["POST"])
@jwt_user_required
@business_required
def change_plan():
    """Change le plan (en dev uniquement — en prod, passer par le paiement)."""
    biz = g.api_business
    data = request.get_json(silent=True) or {}
    plan = (data.get("plan") or "").strip().lower()

    from flask import current_app
    plans = current_app.config.get("PLANS", {})
    if plan not in plans:
        return err("Plan invalide.", [f"Plans disponibles : {list(plans.keys())}"], 422)

    current_sub = biz.subscription
    if current_sub:
        current_sub.status = "cancelled"

    new_sub = Subscription(
        business_id=biz.id,
        plan=plan,
        status="active",
        started_at=datetime.now(timezone.utc),
    )
    db.session.add(new_sub)
    db.session.commit()

    log_activity(
        action="api_subscription_change",
        description=f"Plan changé pour {plan} (business {biz.id})",
        user_id=g.api_user.id,
    )
    return ok(new_sub.to_dict(), f"Plan changé en {plan}.", 200)