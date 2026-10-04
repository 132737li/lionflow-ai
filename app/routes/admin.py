"""
Espace administrateur — Gestion globale de la plateforme.
Réservé aux utilisateurs avec role = 'admin'.
"""
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta, timezone

from flask import (
    Blueprint, render_template, redirect, url_for, flash,
    request, current_app, abort,
)
from flask_login import login_required, current_user
from sqlalchemy import func, or_, extract

from app.extensions import db
from app.models.user import User
from app.models.business import Business
from app.models.contact import Contact
from app.models.campaign import Campaign
from app.models.message import Message
from app.models.subscription import Subscription
from app.models.payment import Payment
from app.models.log import Log
from app.models.chatbot_conversation import ChatbotConversation
from app.utils.security import log_activity


admin_bp = Blueprint("admin", __name__, template_folder="../templates/admin")


def _utcnow():
    """Heure UTC naïve."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ==================================================
# DÉCORATEUR : accès admin uniquement
# ==================================================
def admin_required(fn):
    """Exige un utilisateur avec role='admin'."""
    from functools import wraps

    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)
        if current_user.role != "admin":
            flash("Accès réservé aux administrateurs.", "danger")
            return redirect(url_for("dashboard.index"))
        return fn(*args, **kwargs)
    return wrapper


# ==================================================
# DASHBOARD GLOBAL
# ==================================================
@admin_bp.route("/")
@login_required
@admin_required
def dashboard():
    """Tableau de bord global de la plateforme."""

    # ===== Statistiques utilisateurs =====
    total_users = User.query.count()
    active_users = User.query.filter_by(is_active=True).count()
    admin_users = User.query.filter_by(role="admin").count()

    # Nouveaux utilisateurs ce mois
    now = _utcnow()
    new_users_this_month = User.query.filter(
        extract("year", User.created_at) == now.year,
        extract("month", User.created_at) == now.month,
    ).count()

    # ===== Statistiques entreprises =====
    total_businesses = Business.query.count()

    # Répartition par plan
    plan_counts = dict(
        db.session.query(
            Subscription.plan,
            func.count(Subscription.id),
        )
        .filter(Subscription.status == "active")
        .group_by(Subscription.plan)
        .all()
    )

    # ===== Statistiques contacts =====
    total_contacts = Contact.query.count()

    # ===== Statistiques campagnes et messages =====
    total_campaigns = Campaign.query.count()
    total_messages = Message.query.count()

    messages_by_status = dict(
        db.session.query(
            Message.status,
            func.count(Message.id),
        )
        .group_by(Message.status)
        .all()
    )

    # ===== Statistiques paiements =====
    total_revenue_cents = (
        db.session.query(func.sum(Payment.amount_cents))
        .filter(Payment.status == "succeeded")
        .scalar() or 0
    )
    total_payments = Payment.query.filter_by(status="succeeded").count()

    # ===== Statistiques chatbot =====
    total_conversations = ChatbotConversation.query.count()
    total_auto_replies = (
        db.session.query(func.sum(ChatbotConversation.auto_replies_count))
        .scalar() or 0
    )

    # ===== Graphiques =====
    # Inscriptions sur 30 jours
    since = now - timedelta(days=29)
    user_rows = (
        db.session.query(
            func.date(User.created_at).label("day"),
            func.count(User.id).label("count"),
        )
        .filter(User.created_at >= since)
        .group_by(func.date(User.created_at))
        .all()
    )
    users_chart = {str(r.day): int(r.count) for r in user_rows}
    user_labels, user_values = [], []
    today = now.date()
    for i in range(30):
        d = today - timedelta(days=29 - i)
        user_labels.append(d.strftime("%d/%m"))
        user_values.append(users_chart.get(d.isoformat(), 0))

    # Messages sur 30 jours
    msg_rows = (
        db.session.query(
            func.date(Message.created_at).label("day"),
            func.count(Message.id).label("count"),
        )
        .filter(Message.created_at >= since)
        .group_by(func.date(Message.created_at))
        .all()
    )
    msg_chart = {str(r.day): int(r.count) for r in msg_rows}
    msg_labels, msg_values = [], []
    for i in range(30):
        d = today - timedelta(days=29 - i)
        msg_labels.append(d.strftime("%d/%m"))
        msg_values.append(msg_chart.get(d.isoformat(), 0))

    # ===== Top entreprises (par nombre de contacts) =====
    top_businesses = (
        Business.query
        .order_by(Business.created_at.desc())
        .limit(5)
        .all()
    )

    # ===== Derniers utilisateurs inscrits =====
    recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()

    # ===== Derniers paiements =====
    recent_payments = (
        Payment.query
        .filter_by(status="succeeded")
        .order_by(Payment.created_at.desc())
        .limit(5)
        .all()
    )

    # ===== Logs récents de la plateforme =====
    recent_logs = Log.query.order_by(Log.created_at.desc()).limit(10).all()

    return render_template(
        "admin/dashboard.html",
        # Users
        total_users=total_users,
        active_users=active_users,
        admin_users=admin_users,
        new_users_this_month=new_users_this_month,
        # Businesses
        total_businesses=total_businesses,
        plan_counts=plan_counts,
        # Contacts
        total_contacts=total_contacts,
        # Campagnes / messages
        total_campaigns=total_campaigns,
        total_messages=total_messages,
        messages_by_status=messages_by_status,
        # Paiements
        total_revenue_cents=total_revenue_cents,
        total_revenue_euros=round(total_revenue_cents / 100, 2),
        total_payments=total_payments,
        # Chatbot
        total_conversations=total_conversations,
        total_auto_replies=total_auto_replies,
        # Graphiques
        user_labels=user_labels,
        user_values=user_values,
        msg_labels=msg_labels,
        msg_values=msg_values,
        # Listes
        top_businesses=top_businesses,
        recent_users=recent_users,
        recent_payments=recent_payments,
        recent_logs=recent_logs,
    )
# ==================================================
# LISTE DES UTILISATEURS
# ==================================================
@admin_bp.route("/users")
@login_required
@admin_required
def users_list():
    """Liste tous les utilisateurs de la plateforme."""
    q = (request.args.get("q") or "").strip()
    role = (request.args.get("role") or "").strip()
    status = (request.args.get("status") or "").strip()
    page = request.args.get("page", 1, type=int)

    query = User.query

    # Recherche
    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            User.email.ilike(like),
            User.first_name.ilike(like),
            User.last_name.ilike(like),
        ))

    # Filtre par rôle
    if role in ("admin", "user"):
        query = query.filter(User.role == role)

    # Filtre par statut
    if status == "active":
        query = query.filter(User.is_active == True)
    elif status == "inactive":
        query = query.filter(User.is_active == False)

    pagination = query.order_by(User.created_at.desc()).paginate(
        page=page, per_page=30, error_out=False
    )

    # Compteurs
    total_users = User.query.count()
    total_admins = User.query.filter_by(role="admin").count()
    total_active = User.query.filter_by(is_active=True).count()
    total_inactive = total_users - total_active

    return render_template(
        "admin/users.html",
        users=pagination.items,
        pagination=pagination,
        q=q,
        role_filter=role,
        status_filter=status,
        total_users=total_users,
        total_admins=total_admins,
        total_active=total_active,
        total_inactive=total_inactive,
    )


# ==================================================
# DÉTAIL D'UN UTILISATEUR
# ==================================================
@admin_bp.route("/users/<int:user_id>")
@login_required
@admin_required
def user_detail(user_id: int):
    """Affiche les détails d'un utilisateur."""
    user = User.query.get_or_404(user_id)

    # Statistiques de l'utilisateur
    businesses = user.businesses.all()
    total_businesses = len(businesses)
    total_contacts = sum(b.contacts.count() for b in businesses)
    total_campaigns = sum(b.campaigns.count() for b in businesses)

    # Logs récents
    recent_logs = (
        Log.query
        .filter_by(user_id=user.id)
        .order_by(Log.created_at.desc())
        .limit(20)
        .all()
    )

    # Notifications
    unread_notifications = user.notifications.filter_by(is_read=False).count()
    total_notifications = user.notifications.count()

    # Clés API
    total_api_keys = user.api_keys.count()
    active_api_keys = user.api_keys.filter_by(is_active=True).count()

    return render_template(
        "admin/user_detail.html",
        user=user,
        businesses=businesses,
        total_businesses=total_businesses,
        total_contacts=total_contacts,
        total_campaigns=total_campaigns,
        recent_logs=recent_logs,
        unread_notifications=unread_notifications,
        total_notifications=total_notifications,
        total_api_keys=total_api_keys,
        active_api_keys=active_api_keys,
    )


# ==================================================
# ACTIVER / DÉSACTIVER UN UTILISATEUR
# ==================================================
@admin_bp.route("/users/<int:user_id>/toggle-active", methods=["POST"])
@login_required
@admin_required
def user_toggle_active(user_id: int):
    """Active ou désactive un utilisateur."""
    if user_id == current_user.id:
        flash("Vous ne pouvez pas désactiver votre propre compte.", "danger")
        return redirect(url_for("admin.user_detail", user_id=user_id))

    user = User.query.get_or_404(user_id)
    user.is_active = not user.is_active
    db.session.commit()

    state = "activé" if user.is_active else "désactivé"
    log_activity(
        action="admin_user_toggle",
        description=f"Utilisateur {state} : {user.email}",
    )
    flash(f"Utilisateur « {user.email} » {state}.", "success")
    return redirect(url_for("admin.user_detail", user_id=user_id))


# ==================================================
# PROMOUVOIR / RÉTROGRADER UN ADMIN
# ==================================================
@admin_bp.route("/users/<int:user_id>/toggle-role", methods=["POST"])
@login_required
@admin_required
def user_toggle_role(user_id: int):
    """Change le rôle d'un utilisateur (admin ↔ user)."""
    if user_id == current_user.id:
        flash("Vous ne pouvez pas changer votre propre rôle.", "danger")
        return redirect(url_for("admin.user_detail", user_id=user_id))

    user = User.query.get_or_404(user_id)

    if user.role == "admin":
        # Vérifier qu'il reste au moins 1 admin
        admin_count = User.query.filter_by(role="admin").count()
        if admin_count <= 1:
            flash("Impossible : il doit rester au moins un administrateur.", "danger")
            return redirect(url_for("admin.user_detail", user_id=user_id))
        user.role = "user"
        msg = f"Utilisateur « {user.email} » rétrogradé en user."
    else:
        user.role = "admin"
        msg = f"Utilisateur « {user.email} » promu administrateur."

    db.session.commit()

    log_activity(
        action="admin_user_role",
        description=msg,
    )
    flash(msg, "success")
    return redirect(url_for("admin.user_detail", user_id=user_id))


# ==================================================
# SUPPRIMER UN UTILISATEUR
# ==================================================
@admin_bp.route("/users/<int:user_id>/delete", methods=["POST"])
@login_required
@admin_required
def user_delete(user_id: int):
    """Supprime un utilisateur et toutes ses données (CASCADE)."""
    if user_id == current_user.id:
        flash("Vous ne pouvez pas supprimer votre propre compte.", "danger")
        return redirect(url_for("admin.user_detail", user_id=user_id))

    user = User.query.get_or_404(user_id)

    # Vérifier qu'il reste au moins 1 admin
    if user.role == "admin":
        admin_count = User.query.filter_by(role="admin").count()
        if admin_count <= 1:
            flash("Impossible : il doit rester au moins un administrateur.", "danger")
            return redirect(url_for("admin.user_detail", user_id=user_id))

    email = user.email
    db.session.delete(user)
    db.session.commit()

    log_activity(
        action="admin_user_delete",
        description=f"Utilisateur supprimé : {email}",
    )
    flash(f"Utilisateur « {email} » supprimé.", "info")
    return redirect(url_for("admin.users_list"))


# ==================================================
# RÉINITIALISER LE MOT DE PASSE
# ==================================================
@admin_bp.route("/users/<int:user_id>/reset-password", methods=["POST"])
@login_required
@admin_required
def user_reset_password(user_id: int):
    """Réinitialise le mot de passe d'un utilisateur."""
    user = User.query.get_or_404(user_id)

    new_password = (request.form.get("new_password") or "").strip()
    if len(new_password) < 8:
        flash("Le mot de passe doit contenir au moins 8 caractères.", "danger")
        return redirect(url_for("admin.user_detail", user_id=user_id))

    user.set_password(new_password)
    db.session.commit()

    log_activity(
        action="admin_user_reset_password",
        description=f"Mot de passe réinitialisé pour : {user.email}",
    )
    flash(
        f"Mot de passe de « {user.email} » réinitialisé. "
        "Communiquez-le à l'utilisateur de manière sécurisée.",
        "success",
    )
    return redirect(url_for("admin.user_detail", user_id=user_id))

# ==================================================
# LISTE DES ENTREPRISES
# ==================================================
@admin_bp.route("/businesses")
@login_required
@admin_required
def businesses_list():
    """Liste toutes les entreprises de la plateforme."""
    q = (request.args.get("q") or "").strip()
    plan = (request.args.get("plan") or "").strip()
    country = (request.args.get("country") or "").strip()
    page = request.args.get("page", 1, type=int)

    query = Business.query

    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            Business.name.ilike(like),
            Business.email.ilike(like),
            Business.phone.ilike(like),
        ))

    if country:
        query = query.filter(Business.country == country)

    # Filtre par plan (via join sur subscription active)
    if plan in ("free", "pro", "business"):
        sub_query = (
            db.session.query(Subscription.business_id)
            .filter(Subscription.plan == plan, Subscription.status == "active")
            .subquery()
        )
        query = query.filter(Business.id.in_(db.session.query(sub_query.c.business_id)))

    pagination = query.order_by(Business.created_at.desc()).paginate(
        page=page, per_page=25, error_out=False
    )

    # Compteurs
    total_businesses = Business.query.count()
    free_count = db.session.query(func.count(Subscription.id)).filter(
        Subscription.plan == "free", Subscription.status == "active"
    ).scalar() or 0
    pro_count = db.session.query(func.count(Subscription.id)).filter(
        Subscription.plan == "pro", Subscription.status == "active"
    ).scalar() or 0
    business_count = db.session.query(func.count(Subscription.id)).filter(
        Subscription.plan == "business", Subscription.status == "active"
    ).scalar() or 0

    return render_template(
        "admin/businesses.html",
        businesses=pagination.items,
        pagination=pagination,
        q=q,
        plan_filter=plan,
        country_filter=country,
        total_businesses=total_businesses,
        free_count=free_count,
        pro_count=pro_count,
        business_count=business_count,
    )


# ==================================================
# DÉTAIL D'UNE ENTREPRISE
# ==================================================
@admin_bp.route("/businesses/<int:business_id>")
@login_required
@admin_required
def business_detail(business_id: int):
    """Affiche les détails d'une entreprise."""
    business = Business.query.get_or_404(business_id)

    # Statistiques
    total_contacts = business.contacts.count()
    total_campaigns = business.campaigns.count()
    total_templates = business.templates.count()
    total_waba = business.whatsapp_accounts.count()

    # Messages via campagnes
    total_messages = (
        db.session.query(func.count(Message.id))
        .join(Campaign, Message.campaign_id == Campaign.id)
        .filter(Campaign.business_id == business.id)
        .scalar() or 0
    )

    # Abonnements (historique)
    subscriptions = (
        Subscription.query
        .filter_by(business_id=business.id)
        .order_by(Subscription.created_at.desc())
        .all()
    )

    # Paiements
    payments = (
        Payment.query
        .filter_by(business_id=business.id)
        .order_by(Payment.created_at.desc())
        .limit(20)
        .all()
    )

    # Dernières campagnes
    recent_campaigns = (
        Campaign.query
        .filter_by(business_id=business.id)
        .order_by(Campaign.created_at.desc())
        .limit(5)
        .all()
    )

    # Comptes WhatsApp
    whatsapp_accounts = business.whatsapp_accounts.all()

    # Tous les plans (pour le sélecteur)
    from flask import current_app
    all_plans = current_app.config.get("PLANS", {})

    return render_template(
        "admin/business_detail.html",
        business=business,
        total_contacts=total_contacts,
        total_campaigns=total_campaigns,
        total_templates=total_templates,
        total_waba=total_waba,
        total_messages=total_messages,
        subscriptions=subscriptions,
        payments=payments,
        recent_campaigns=recent_campaigns,
        whatsapp_accounts=whatsapp_accounts,
        all_plans=all_plans,
    )


# ==================================================
# CHANGER LE PLAN D'UNE ENTREPRISE (manuellement)
# ==================================================
@admin_bp.route("/businesses/<int:business_id>/change-plan", methods=["POST"])
@login_required
@admin_required
def business_change_plan(business_id: int):
    """Change le plan d'une entreprise manuellement (sans paiement)."""
    from flask import current_app

    business = Business.query.get_or_404(business_id)
    new_plan = (request.form.get("plan") or "").strip()

    all_plans = current_app.config.get("PLANS", {})
    if new_plan not in all_plans:
        flash("Plan invalide.", "danger")
        return redirect(url_for("admin.business_detail", business_id=business_id))

    # Annuler les anciens abonnements
    Subscription.query.filter_by(
        business_id=business.id, status="active"
    ).update({"status": "cancelled"})

    # Créer le nouvel abonnement
    new_sub = Subscription(
        business_id=business.id,
        plan=new_plan,
        status="active",
        started_at=_utcnow(),
    )
    if new_plan != "free":
        new_sub.extend(30)
    db.session.add(new_sub)
    db.session.commit()

    log_activity(
        action="admin_business_change_plan",
        description=f"Plan de « {business.name} » changé en {new_plan} par admin",
    )
    flash(
        f"Plan de « {business.name} » changé en {all_plans[new_plan]['label']}.",
        "success",
    )
    return redirect(url_for("admin.business_detail", business_id=business_id))


# ==================================================
# PROLONGER UN ABONNEMENT
# ==================================================
@admin_bp.route("/businesses/<int:business_id>/extend", methods=["POST"])
@login_required
@admin_required
def business_extend_subscription(business_id: int):
    """Prolonge l'abonnement actif de X jours."""
    business = Business.query.get_or_404(business_id)

    days = request.form.get("days", 30, type=int)
    if days < 1 or days > 365:
        days = 30

    sub = business.subscription
    if not sub:
        flash("Aucun abonnement actif à prolonger.", "warning")
        return redirect(url_for("admin.business_detail", business_id=business_id))

    sub.extend(days)
    db.session.commit()

    log_activity(
        action="admin_business_extend",
        description=f"Abonnement de « {business.name} » prolongé de {days} jours",
    )
    flash(f"Abonnement prolongé de {days} jours.", "success")
    return redirect(url_for("admin.business_detail", business_id=business_id))


# ==================================================
# SUSPENDRE / ACTIVER UNE ENTREPRISE
# ==================================================
@admin_bp.route("/businesses/<int:business_id>/suspend", methods=["POST"])
@login_required
@admin_required
def business_suspend(business_id: int):
    """Suspend l'abonnement d'une entreprise (statut suspended)."""
    business = Business.query.get_or_404(business_id)

    sub = business.subscription
    if not sub:
        flash("Aucun abonnement actif.", "warning")
        return redirect(url_for("admin.business_detail", business_id=business_id))

    sub.status = "cancelled"
    db.session.commit()

    log_activity(
        action="admin_business_suspend",
        description=f"Entreprise suspendue : {business.name}",
    )
    flash(f"Entreprise « {business.name} » suspendue.", "warning")
    return redirect(url_for("admin.business_detail", business_id=business_id))


@admin_bp.route("/businesses/<int:business_id>/reactivate", methods=["POST"])
@login_required
@admin_required
def business_reactivate(business_id: int):
    """Réactive une entreprise suspendue (retour au plan Free)."""
    business = Business.query.get_or_404(business_id)

    # S'assurer qu'il n'y a pas déjà un abonnement actif
    existing = Subscription.query.filter_by(
        business_id=business.id, status="active"
    ).first()
    if existing:
        flash("Cette entreprise a déjà un abonnement actif.", "info")
        return redirect(url_for("admin.business_detail", business_id=business_id))

    sub = Subscription(
        business_id=business.id,
        plan="free",
        status="active",
        started_at=_utcnow(),
    )
    db.session.add(sub)
    db.session.commit()

    log_activity(
        action="admin_business_reactivate",
        description=f"Entreprise réactivée : {business.name}",
    )
    flash(f"Entreprise « {business.name} » réactivée (plan Free).", "success")
    return redirect(url_for("admin.business_detail", business_id=business_id))


# ==================================================
# SUPPRIMER UNE ENTREPRISE
# ==================================================
@admin_bp.route("/businesses/<int:business_id>/delete", methods=["POST"])
@login_required
@admin_required
def business_delete(business_id: int):
    """Supprime une entreprise et toutes ses données (CASCADE)."""
    business = Business.query.get_or_404(business_id)
    name = business.name

    db.session.delete(business)
    db.session.commit()

    log_activity(
        action="admin_business_delete",
        description=f"Entreprise supprimée : {name}",
    )
    flash(f"Entreprise « {name} » supprimée.", "info")
    return redirect(url_for("admin.businesses_list"))


# ==================================================
# LISTE DES ABONNEMENTS
# ==================================================
@admin_bp.route("/subscriptions")
@login_required
@admin_required
def subscriptions_list():
    """Liste tous les abonnements actifs de la plateforme."""
    plan = (request.args.get("plan") or "").strip()
    status = (request.args.get("status") or "").strip()
    page = request.args.get("page", 1, type=int)

    query = Subscription.query

    if plan in ("free", "pro", "business"):
        query = query.filter(Subscription.plan == plan)
    if status in ("active", "past_due", "cancelled", "expired"):
        query = query.filter(Subscription.status == status)

    pagination = query.order_by(Subscription.created_at.desc()).paginate(
        page=page, per_page=30, error_out=False
    )

    # Statistiques
    plan_stats = dict(
        db.session.query(
            Subscription.plan,
            func.count(Subscription.id),
        )
        .filter(Subscription.status == "active")
        .group_by(Subscription.plan)
        .all()
    )

    total_revenue = (
        db.session.query(func.sum(Payment.amount_cents))
        .filter(Payment.status == "succeeded")
        .scalar() or 0
    )

    return render_template(
        "admin/subscriptions.html",
        subscriptions=pagination.items,
        pagination=pagination,
        plan_filter=plan,
        status_filter=status,
        plan_stats=plan_stats,
        total_revenue_euros=round(total_revenue / 100, 2),
    )
    
    
    # ==================================================
# CAMPAGNES — Modération globale
# ==================================================
@admin_bp.route("/campaigns")
@login_required
@admin_required
def campaigns_list():
    """Liste toutes les campagnes de la plateforme."""
    q = (request.args.get("q") or "").strip()
    status = (request.args.get("status") or "").strip()
    page = request.args.get("page", 1, type=int)

    query = Campaign.query

    if q:
        query = query.filter(Campaign.name.ilike(f"%{q}%"))

    if status in ("draft", "scheduled", "running", "paused", "completed", "cancelled"):
        query = query.filter(Campaign.status == status)

    pagination = query.order_by(Campaign.created_at.desc()).paginate(
        page=page, per_page=25, error_out=False
    )

    # Stats par statut
    status_counts = dict(
        db.session.query(Campaign.status, func.count(Campaign.id))
        .group_by(Campaign.status)
        .all()
    )

    return render_template(
        "admin/campaigns.html",
        campaigns=pagination.items,
        pagination=pagination,
        q=q,
        status_filter=status,
        status_counts=status_counts,
    )


@admin_bp.route("/campaigns/<int:campaign_id>/cancel", methods=["POST"])
@login_required
@admin_required
def campaign_cancel(campaign_id: int):
    """Annule une campagne (modération)."""
    campaign = Campaign.query.get_or_404(campaign_id)

    if campaign.status in ("completed", "cancelled"):
        flash("Cette campagne est déjà terminée ou annulée.", "warning")
        return redirect(url_for("admin.campaigns_list"))

    campaign.status = "cancelled"
    campaign.finished_at = _utcnow()
    db.session.commit()

    log_activity(
        action="admin_campaign_cancel",
        description=f"Campagne annulée par admin : {campaign.name} (id={campaign.id})",
    )
    flash(f"Campagne « {campaign.name} » annulée.", "success")
    return redirect(url_for("admin.campaigns_list"))


@admin_bp.route("/campaigns/<int:campaign_id>/delete", methods=["POST"])
@login_required
@admin_required
def campaign_delete(campaign_id: int):
    """Supprime une campagne (modération)."""
    campaign = Campaign.query.get_or_404(campaign_id)
    name = campaign.name

    if campaign.status == "running":
        flash("Impossible de supprimer une campagne en cours. Annulez-la d'abord.", "warning")
        return redirect(url_for("admin.campaigns_list"))

    db.session.delete(campaign)
    db.session.commit()

    log_activity(
        action="admin_campaign_delete",
        description=f"Campagne supprimée par admin : {name}",
    )
    flash(f"Campagne « {name} » supprimée.", "info")
    return redirect(url_for("admin.campaigns_list"))


# ==================================================
# CHATBOT — Statistiques globales
# ==================================================
@admin_bp.route("/chatbot")
@login_required
@admin_required
def chatbot_stats():
    """Statistiques globales du chatbot de la plateforme."""
    from app.models.chatbot_rule import ChatbotRule

    # Compteurs
    total_rules = ChatbotRule.query.count()
    active_rules = ChatbotRule.query.filter_by(is_active=True).count()
    total_conversations = ChatbotConversation.query.count()
    active_conversations = ChatbotConversation.query.filter_by(status="active").count()
    waiting_conversations = ChatbotConversation.query.filter_by(status="waiting").count()
    total_auto_replies = (
        db.session.query(func.sum(ChatbotConversation.auto_replies_count))
        .scalar() or 0
    )

    # Règles les plus utilisées (toutes entreprises)
    top_rules = (
        ChatbotRule.query
        .order_by(ChatbotRule.usage_count.desc())
        .limit(10)
        .all()
    )

    # Conversations récentes
    recent_conversations = (
        ChatbotConversation.query
        .order_by(ChatbotConversation.created_at.desc())
        .limit(15)
        .all()
    )

    # Graphique : conversations sur 30 jours
    since = _utcnow() - timedelta(days=29)
    rows = (
        db.session.query(
            func.date(ChatbotConversation.created_at).label("day"),
            func.count(ChatbotConversation.id).label("count"),
        )
        .filter(ChatbotConversation.created_at >= since)
        .group_by(func.date(ChatbotConversation.created_at))
        .all()
    )
    chart_data = {str(r.day): int(r.count) for r in rows}
    labels, values = [], []
    today = _utcnow().date()
    for i in range(30):
        d = today - timedelta(days=29 - i)
        labels.append(d.strftime("%d/%m"))
        values.append(chart_data.get(d.isoformat(), 0))

    return render_template(
        "admin/chatbot.html",
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
# JOURNAL GLOBAL — Tous les logs
# ==================================================
@admin_bp.route("/logs")
@login_required
@admin_required
def logs_global():
    """Journal d'activité de tous les utilisateurs."""
    q = (request.args.get("q") or "").strip()
    action = (request.args.get("action") or "").strip()
    page = request.args.get("page", 1, type=int)

    query = Log.query

    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            Log.description.ilike(like),
            Log.ip_address.ilike(like),
        ))

    if action:
        query = query.filter(Log.action.ilike(f"%{action}%"))

    pagination = query.order_by(Log.created_at.desc()).paginate(
        page=page, per_page=50, error_out=False
    )

    # Actions distinctes
    actions = [
        row[0] for row in
        Log.query.with_entities(Log.action)
        .distinct()
        .order_by(Log.action)
        .all()
    ]

    total_logs = Log.query.count()

    return render_template(
        "admin/logs.html",
        logs=pagination.items,
        pagination=pagination,
        q=q,
        actions=actions,
        filter_action=action,
        total_logs=total_logs,
    )


@admin_bp.route("/logs/delete-all", methods=["POST"])
@login_required
@admin_required
def logs_delete_all():
    """Supprime TOUS les logs de la plateforme (reset complet)."""
    count = Log.query.delete(synchronize_session=False)
    db.session.commit()

    # On trace cette action
    log_activity(
        action="admin_logs_cleared",
        description=f"Tous les logs ont été supprimés par admin ({count} entrées)",
        user_id=current_user.id,
    )

    flash(f"{count} entrée(s) supprimée(s) du journal global.", "success")
    return redirect(url_for("admin.logs_global"))


@admin_bp.route("/logs/<int:log_id>/delete", methods=["POST"])
@login_required
@admin_required
def log_delete(log_id: int):
    """Supprime une entrée de log spécifique."""
    log = Log.query.get_or_404(log_id)
    db.session.delete(log)
    db.session.commit()

    flash("Entrée supprimée.", "info")
    return redirect(url_for("admin.logs_global"))


# ==================================================
# RÉGLAGES DE LA PLATEFORME
# ==================================================
@admin_bp.route("/settings")
@login_required
@admin_required
def settings():
    """Page de réglages globaux."""
    # Infos système
    import sys
    import platform

    system_info = {
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "flask_debug": current_app.config.get("DEBUG", False),
        "payment_provider": current_app.config.get("PAYMENT_PROVIDER") or "Non configuré",
        "whatsapp_dev_mode": current_app.config.get("WHATSAPP_DEV_MODE", False),
        "scheduler_enabled": current_app.config.get("SCHEDULER_ENABLED", False),
    }

    # Compteurs globaux
    stats = {
        "users": User.query.count(),
        "businesses": Business.query.count(),
        "contacts": Contact.query.count(),
        "campaigns": Campaign.query.count(),
        "messages": Message.query.count(),
        "logs": Log.query.count(),
    }

    # Plans
    plans = current_app.config.get("PLANS", {})

    return render_template(
        "admin/settings.html",
        system_info=system_info,
        stats=stats,
        plans=plans,
    )
    
@admin_required
def test_email():
    """Teste la configuration SMTP en envoyant un email au compte configuré."""
    from app.services.email_service import EmailService
    result = EmailService.test_connection()

    if result["success"]:
        flash(f"✅ {result['message']}", "success")
    else:
        flash(f"❌ Erreur : {result['error']}", "danger")

    return redirect(url_for("admin.dashboard"))