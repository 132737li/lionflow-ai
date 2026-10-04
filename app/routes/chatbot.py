"""
Routes UI du chatbot.
CRUD des règles + consultation des conversations + réglages.
"""
from datetime import datetime, timedelta, timezone

from flask import (
    Blueprint, render_template, redirect, url_for, flash,
    request, jsonify,
)
from flask_login import login_required
from sqlalchemy import func, or_

from app.extensions import db
from app.forms.chatbot_forms import ChatbotRuleForm
from app.models.chatbot_rule import ChatbotRule
from app.models.chatbot_conversation import ChatbotConversation
from app.services.chatbot_service import ChatbotService
from app.utils.decorators import require_business, get_current_business
from app.utils.security import log_activity


chatbot_bp = Blueprint("chatbot", __name__, template_folder="../templates/chatbot")


def _utcnow():
    """Heure UTC naïve."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ==================================================
# TABLEAU DE BORD (accessible via /chatbot/ et /chatbot/dashboard)
# ==================================================
@chatbot_bp.route("/")
@chatbot_bp.route("/dashboard")
@login_required
@require_business
def dashboard():
    business = get_current_business()

    # Statistiques
    total_rules = ChatbotRule.query.filter_by(business_id=business.id).count()
    active_rules = ChatbotRule.query.filter_by(
        business_id=business.id, is_active=True
    ).count()

    total_conversations = ChatbotConversation.query.filter_by(
        business_id=business.id
    ).count()

    active_conversations = ChatbotConversation.query.filter_by(
        business_id=business.id, status="active"
    ).count()

    waiting_conversations = ChatbotConversation.query.filter_by(
        business_id=business.id, status="waiting"
    ).count()

    # Total de messages traités automatiquement
    total_auto_replies = (
        db.session.query(func.sum(ChatbotConversation.auto_replies_count))
        .filter(ChatbotConversation.business_id == business.id)
        .scalar() or 0
    )

    # Règles les plus utilisées
    top_rules = (
        ChatbotRule.query
        .filter_by(business_id=business.id)
        .order_by(ChatbotRule.usage_count.desc())
        .limit(5)
        .all()
    )

    # Conversations récentes
    recent_conversations = (
        ChatbotConversation.query
        .filter_by(business_id=business.id)
        .order_by(ChatbotConversation.created_at.desc())
        .limit(10)
        .all()
    )

    # Graphique : conversations par jour (7 derniers jours)
    since = _utcnow() - timedelta(days=6)
    rows = (
        db.session.query(
            func.date(ChatbotConversation.created_at).label("day"),
            func.count(ChatbotConversation.id).label("count"),
        )
        .filter(
            ChatbotConversation.business_id == business.id,
            ChatbotConversation.created_at >= since,
        )
        .group_by(func.date(ChatbotConversation.created_at))
        .all()
    )
    chart_data = {str(r.day): int(r.count) for r in rows}
    labels, values = [], []
    today = _utcnow().date()
    for i in range(7):
        d = today - timedelta(days=6 - i)
        labels.append(d.strftime("%d/%m"))
        values.append(chart_data.get(d.isoformat(), 0))

    return render_template(
        "chatbot/dashboard.html",
        business=business,
        total_rules=total_rules,
        active_rules=active_rules,
        total_conversations=total_conversations,
        active_conversations=active_conversations,
        waiting_conversations=waiting_conversations,
        total_auto_replies=total_auto_replies,
        top_rules=top_rules,
        recent_conversations=recent_conversations,
        chart_labels=labels,
        chart_values=values,
    )


# ==================================================
# LISTE DES RÈGLES
# ==================================================
@chatbot_bp.route("/rules")
@login_required
@require_business
def list_rules():
    business = get_current_business()

    q = (request.args.get("q") or "").strip()
    status = (request.args.get("status") or "").strip()

    query = ChatbotRule.query.filter_by(business_id=business.id)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            ChatbotRule.name.ilike(like),
            ChatbotRule.keywords.ilike(like),
            ChatbotRule.response.ilike(like),
        ))
    if status == "active":
        query = query.filter_by(is_active=True)
    elif status == "inactive":
        query = query.filter_by(is_active=False)

    rules = query.order_by(
        ChatbotRule.priority.asc(),
        ChatbotRule.created_at.desc(),
    ).all()

    return render_template(
        "chatbot/rules.html",
        business=business,
        rules=rules,
        q=q,
        status_filter=status,
    )


# ==================================================
# CRÉER UNE RÈGLE
# ==================================================
@chatbot_bp.route("/rules/new", methods=["GET", "POST"])
@login_required
@require_business
def create_rule():
    business = get_current_business()
    form = ChatbotRuleForm()

    if form.validate_on_submit():
        rule = ChatbotRule(
            business_id=business.id,
            name=form.name.data.strip(),
            keywords=form.keywords.data.strip(),
            response=form.response.data.strip(),
            match_type=form.match_type.data or "contains",
            priority=form.priority.data or 50,
            send_menu=bool(form.send_menu.data),
            is_active=bool(form.is_active.data),
        )
        db.session.add(rule)
        db.session.commit()

        log_activity(
            action="chatbot_rule_create",
            description=f"Règle chatbot créée : {rule.name}",
        )
        flash("Règle créée avec succès.", "success")
        return redirect(url_for("chatbot.list_rules"))

    return render_template(
        "chatbot/rule_form.html",
        business=business,
        form=form,
        rule=None,
    )


# ==================================================
# MODIFIER UNE RÈGLE
# ==================================================
@chatbot_bp.route("/rules/<int:rule_id>/edit", methods=["GET", "POST"])
@login_required
@require_business
def edit_rule(rule_id: int):
    business = get_current_business()
    rule = ChatbotRule.query.filter_by(
        id=rule_id, business_id=business.id
    ).first_or_404()

    form = ChatbotRuleForm(obj=rule)
    if form.validate_on_submit():
        rule.name = form.name.data.strip()
        rule.keywords = form.keywords.data.strip()
        rule.response = form.response.data.strip()
        rule.match_type = form.match_type.data or "contains"
        rule.priority = form.priority.data or 50
        rule.send_menu = bool(form.send_menu.data)
        rule.is_active = bool(form.is_active.data)

        db.session.commit()

        log_activity(
            action="chatbot_rule_update",
            description=f"Règle chatbot modifiée : {rule.name}",
        )
        flash("Règle mise à jour.", "success")
        return redirect(url_for("chatbot.list_rules"))

    return render_template(
        "chatbot/rule_form.html",
        business=business,
        form=form,
        rule=rule,
    )


# ==================================================
# SUPPRIMER UNE RÈGLE
# ==================================================
@chatbot_bp.route("/rules/<int:rule_id>/delete", methods=["POST"])
@login_required
@require_business
def delete_rule(rule_id: int):
    business = get_current_business()
    rule = ChatbotRule.query.filter_by(
        id=rule_id, business_id=business.id
    ).first_or_404()

    name = rule.name
    db.session.delete(rule)
    db.session.commit()

    log_activity(
        action="chatbot_rule_delete",
        description=f"Règle chatbot supprimée : {name}",
    )
    flash(f"Règle « {name} » supprimée.", "info")
    return redirect(url_for("chatbot.list_rules"))


# ==================================================
# ACTIVER / DÉSACTIVER UNE RÈGLE
# ==================================================
@chatbot_bp.route("/rules/<int:rule_id>/toggle", methods=["POST"])
@login_required
@require_business
def toggle_rule(rule_id: int):
    business = get_current_business()
    rule = ChatbotRule.query.filter_by(
        id=rule_id, business_id=business.id
    ).first_or_404()

    rule.is_active = not rule.is_active
    db.session.commit()

    state = "activée" if rule.is_active else "désactivée"
    flash(f"Règle « {rule.name} » {state}.", "success")
    return redirect(url_for("chatbot.list_rules"))


# ==================================================
# CONVERSATIONS
# ==================================================
@chatbot_bp.route("/conversations")
@login_required
@require_business
def list_conversations():
    business = get_current_business()

    status = (request.args.get("status") or "").strip()
    page = request.args.get("page", 1, type=int)

    query = ChatbotConversation.query.filter_by(business_id=business.id)
    if status in ("active", "waiting", "human", "closed"):
        query = query.filter(ChatbotConversation.status == status)

    pagination = query.order_by(
        ChatbotConversation.created_at.desc()
    ).paginate(page=page, per_page=20, error_out=False)

    # Compteurs par statut
    status_counts = dict(
        db.session.query(
            ChatbotConversation.status,
            func.count(ChatbotConversation.id),
        )
        .filter(ChatbotConversation.business_id == business.id)
        .group_by(ChatbotConversation.status)
        .all()
    )

    return render_template(
        "chatbot/conversations.html",
        business=business,
        conversations=pagination.items,
        pagination=pagination,
        status_filter=status,
        status_counts=status_counts,
    )


@chatbot_bp.route("/conversations/<int:conv_id>")
@login_required
@require_business
def conversation_detail(conv_id: int):
    business = get_current_business()
    conversation = ChatbotConversation.query.filter_by(
        id=conv_id, business_id=business.id
    ).first_or_404()

    return render_template(
        "chatbot/conversation_detail.html",
        business=business,
        conversation=conversation,
    )


# ==================================================
# ACTIONS SUR CONVERSATION
# ==================================================
@chatbot_bp.route("/conversations/<int:conv_id>/take-over", methods=["POST"])
@login_required
@require_business
def take_over_conversation(conv_id: int):
    business = get_current_business()
    conversation = ChatbotConversation.query.filter_by(
        id=conv_id, business_id=business.id
    ).first_or_404()

    conversation.take_over()
    db.session.commit()

    log_activity(
        action="chatbot_take_over",
        description=f"Conversation #{conv_id} prise en main par un humain",
    )
    flash("Vous avez pris la main sur cette conversation.", "success")
    return redirect(url_for("chatbot.conversation_detail", conv_id=conv_id))


@chatbot_bp.route("/conversations/<int:conv_id>/close", methods=["POST"])
@login_required
@require_business
def close_conversation(conv_id: int):
    business = get_current_business()
    conversation = ChatbotConversation.query.filter_by(
        id=conv_id, business_id=business.id
    ).first_or_404()

    conversation.close()
    db.session.commit()

    log_activity(
        action="chatbot_close",
        description=f"Conversation #{conv_id} fermée",
    )
    flash("Conversation fermée.", "info")
    return redirect(url_for("chatbot.list_conversations"))


# ==================================================
# RÉGLAGES
# ==================================================
@chatbot_bp.route("/settings")
@login_required
@require_business
def settings():
    business = get_current_business()
    settings_data = ChatbotService.get_settings(business)
    return render_template(
        "chatbot/settings.html",
        business=business,
        settings=settings_data,
    )