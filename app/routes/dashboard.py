"""
Dashboard principal : statistiques, graphiques, activité récente.
"""
from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_required, current_user

from app.utils.decorators import get_current_business
from app.services.statistics_service import StatisticsService
from app.models.notification import Notification


dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
@login_required
def index():
    # Aucune entreprise → on pousse vers la création
    business = get_current_business()
    if not business:
        flash(
            "Bienvenue ! Commencez par créer votre entreprise pour utiliser LionFlow AI.",
            "info",
        )
        return redirect(url_for("businesses.create_business"))

    stats = StatisticsService.summary(business.id)
    msgs_day = StatisticsService.messages_per_day(business.id, days=30)
    msgs_status = StatisticsService.messages_by_status(business.id)
    contacts_evo = StatisticsService.contacts_evolution(business.id, weeks=12)
    recent_activity = StatisticsService.recent_activity(current_user.id, limit=8)
    recent_campaigns = StatisticsService.recent_campaigns(business.id, limit=5)
    recent_messages = StatisticsService.recent_messages(business.id, limit=8)
    delivery_rate = StatisticsService.delivery_rate(business.id)

    # Plan actuel
    sub = business.subscription
    plan_config = business.plan_config

    # 5 dernières notifications non lues
    notifications = (
        Notification.query
        .filter_by(user_id=current_user.id, is_read=False)
        .order_by(Notification.created_at.desc())
        .limit(5)
        .all()
    )

    return render_template(
        "dashboard/index.html",
        business=business,
        stats=stats,
        msgs_day=msgs_day,
        msgs_status=msgs_status,
        contacts_evo=contacts_evo,
        recent_activity=recent_activity,
        recent_campaigns=recent_campaigns,
        recent_messages=recent_messages,
        delivery_rate=delivery_rate,
        subscription=sub,
        plan_config=plan_config,
        notifications=notifications,
    )