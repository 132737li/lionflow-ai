"""Routes campagnes — stub (à compléter en PARTIE 6)."""
from flask import Blueprint, render_template
from flask_login import login_required


campaigns_bp = Blueprint("campaigns", __name__, template_folder="../templates/campaigns")


@campaigns_bp.route("/")
@login_required
def list_campaigns():
    return render_template("_placeholder.html", title="Campagnes", icon="megaphone")


@campaigns_bp.route("/new")
@login_required
def create_campaign():
    return render_template("_placeholder.html", title="Nouvelle campagne", icon="plus-circle")


@campaigns_bp.route("/<int:campaign_id>")
@login_required
def detail_campaign(campaign_id):
    return render_template("_placeholder.html", title=f"Campagne #{campaign_id}", icon="megaphone")

"""
CRUD campagnes + actions (démarrer, pause, reprendre, annuler).
Multi-tenant : filtré par business_id.
"""
from datetime import datetime, timezone
from flask import (
    Blueprint, render_template, redirect, url_for, flash, request, jsonify,
)
from flask_login import login_required

from app.extensions import db
from app.forms.campaign_forms import CampaignForm
from app.models.campaign import Campaign, campaign_contacts
from app.models.template import Template
from app.models.whatsapp_account import WhatsAppAccount
from app.models.contact import Contact
from app.services.campaign_service import CampaignService
from app.utils.decorators import require_business, get_current_business
from app.utils.security import log_activity
from app.utils.timezones import to_utc


campaigns_bp = Blueprint("campaigns", __name__, template_folder="../templates/campaigns")


# ==================================================
# HELPERS POUR LE FORMULAIRE
# ==================================================
def _populate_choices(form, business, selected_contacts_ids=None):
    """Remplit les choix de template, waba, contacts."""
    # Templates
    templates = Template.query.filter_by(business_id=business.id).order_by(Template.name).all()
    form.template_id.choices = [(0, "— Aucun (utiliser le message personnalisé) —")] + [
        (t.id, t.name) for t in templates
    ]

    # Comptes WhatsApp
    wabas = WhatsAppAccount.query.filter_by(business_id=business.id).order_by(WhatsAppAccount.name).all()
    form.whatsapp_account_id.choices = [(0, "— Aucun —")] + [
        (w.id, f"{w.name} ({w.phone_number})") for w in wabas
    ]

    # Contacts (limite à 500 pour ne pas exploser l'UI — recherche possible via API)
    contacts = (
        Contact.query
        .filter_by(business_id=business.id, status="active")
        .order_by(Contact.last_name, Contact.first_name)
        .limit(500)
        .all()
    )
    form.contact_ids.choices = [
        (c.id, f"{c.full_name} — {c.phone}") for c in contacts
    ]
    if selected_contacts_ids:
        form.contact_ids.data = [int(i) for i in selected_contacts_ids if int(i) in {c.id for c in contacts}]


# ==================================================
# LISTE
# ==================================================
@campaigns_bp.route("/")
@login_required
@require_business
def list_campaigns():
    business = get_current_business()
    status = (request.args.get("status") or "").strip()
    q = (request.args.get("q") or "").strip()
    page = request.args.get("page", 1, type=int)
    per_page = 20

    query = Campaign.query.filter_by(business_id=business.id)
    if status:
        query = query.filter(Campaign.status == status)
    if q:
        query = query.filter(Campaign.name.ilike(f"%{q}%"))

    pagination = query.order_by(Campaign.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # Compteurs par statut
    status_counts = dict(
        db.session.query(Campaign.status, db.func.count(Campaign.id))
        .filter(Campaign.business_id == business.id)
        .group_by(Campaign.status)
        .all()
    )

    return render_template(
        "campaigns/list.html",
        campaigns=pagination.items,
        pagination=pagination,
        business=business,
        status_filter=status,
        q=q,
        status_counts=status_counts,
    )


# ==================================================
# CRÉATION
# ==================================================
@campaigns_bp.route("/new", methods=["GET", "POST"])
@login_required
@require_business
def create_campaign():
    business = get_current_business()
    _check_campaign_quota(business)

    form = CampaignForm()
    _populate_choices(form, business)

    if form.validate_on_submit():
        # Validation compte WhatsApp obligatoire
        waba_id = form.whatsapp_account_id.data or 0
        if not waba_id:
            flash("Sélectionnez un compte WhatsApp.", "danger")
            return render_template(
                "campaigns/form.html", form=form, campaign=None, business=business
            )
        waba = WhatsAppAccount.query.filter_by(
            id=waba_id, business_id=business.id
        ).first()
        if not waba:
            flash("Compte WhatsApp invalide.", "danger")
            return render_template(
                "campaigns/form.html", form=form, campaign=None, business=business
            )

        # Validation template
        template_id = form.template_id.data or 0
        template = None
        if template_id:
            template = Template.query.filter_by(
                id=template_id, business_id=business.id
            ).first()

        # Programmation
        scheduled_at_utc = None
        if form.scheduled_at.data:
            scheduled_at_utc = to_utc(form.scheduled_at.data, form.timezone.data)

        # Contacts ciblés
        contact_ids = [int(i) for i in (form.contact_ids.data or [])]
        contacts = Contact.query.filter(
            Contact.business_id == business.id,
            Contact.id.in_(contact_ids),
        ).all() if contact_ids else []

        # Détermination du statut
        status = "scheduled" if scheduled_at_utc else "draft"

        campaign = Campaign(
            business_id=business.id,
            template_id=template.id if template else None,
            whatsapp_account_id=waba.id,
            name=form.name.data.strip(),
            message=(form.message.data or "").strip() or None,
            status=status,
            scheduled_at=scheduled_at_utc,
            timezone=form.timezone.data,
            total_contacts=len(contacts),
        )
        db.session.add(campaign)
        db.session.flush()

        # Association contacts ciblés
        for c in contacts:
            db.session.execute(
                campaign_contacts.insert().values(
                    campaign_id=campaign.id, contact_id=c.id
                )
            )
        db.session.commit()

        log_activity(
            action="campaign_create",
            description=f"Campagne créée : {campaign.name} ({len(contacts)} contacts)",
        )
        flash("Campagne créée.", "success")
        return redirect(url_for("campaigns.detail_campaign", campaign_id=campaign.id))

    return render_template(
        "campaigns/form.html", form=form, campaign=None, business=business
    )


# ==================================================
# DÉTAIL
# ==================================================
@campaigns_bp.route("/<int:campaign_id>")
@login_required
@require_business
def detail_campaign(campaign_id: int):
    business = get_current_business()
    campaign = Campaign.query.filter_by(
        id=campaign_id, business_id=business.id
    ).first_or_404()

    # Recalcul des compteurs (au cas où)
    campaign.recalc_counters()
    db.session.commit()

    messages = (
        campaign.messages
        .order_by(db.desc("created_at"))
        .limit(50)
        .all()
    )

    return render_template(
        "campaigns/detail.html",
        campaign=campaign,
        business=business,
        messages=messages,
    )


# ==================================================
# MODIFICATION
# ==================================================
@campaigns_bp.route("/<int:campaign_id>/edit", methods=["GET", "POST"])
@login_required
@require_business
def edit_campaign(campaign_id: int):
    business = get_current_business()
    campaign = Campaign.query.filter_by(
        id=campaign_id, business_id=business.id
    ).first_or_404()

    # On ne modifie pas une campagne déjà lancée/terminée
    if campaign.status in ("running", "completed", "cancelled"):
        flash("Cette campagne ne peut plus être modifiée.", "warning")
        return redirect(url_for("campaigns.detail_campaign", campaign_id=campaign.id))

    current_contact_ids = [
        row[0] for row in
        db.session.query(campaign_contacts.c.contact_id)
        .filter(campaign_contacts.c.campaign_id == campaign.id)
        .all()
    ]

    form = CampaignForm(obj=campaign)
    _populate_choices(form, business, current_contact_ids)

    if request.method == "GET":
        form.template_id.data = campaign.template_id or 0
        form.whatsapp_account_id.data = campaign.whatsapp_account_id or 0

    if form.validate_on_submit():
        waba_id = form.whatsapp_account_id.data or 0
        waba = WhatsAppAccount.query.filter_by(
            id=waba_id, business_id=business.id
        ).first()
        if not waba:
            flash("Compte WhatsApp invalide.", "danger")
            return render_template(
                "campaigns/form.html", form=form, campaign=campaign, business=business
            )

        template_id = form.template_id.data or 0
        template = None
        if template_id:
            template = Template.query.filter_by(
                id=template_id, business_id=business.id
            ).first()

        scheduled_at_utc = None
        if form.scheduled_at.data:
            scheduled_at_utc = to_utc(form.scheduled_at.data, form.timezone.data)

        contact_ids = [int(i) for i in (form.contact_ids.data or [])]
        contacts = Contact.query.filter(
            Contact.business_id == business.id,
            Contact.id.in_(contact_ids),
        ).all() if contact_ids else []

        # Mise à jour
        campaign.template_id = template.id if template else None
        campaign.whatsapp_account_id = waba.id
        campaign.name = form.name.data.strip()
        campaign.message = (form.message.data or "").strip() or None
        campaign.timezone = form.timezone.data
        campaign.scheduled_at = scheduled_at_utc
        campaign.total_contacts = len(contacts)

        # Recalcul statut
        if campaign.status in ("draft", "scheduled"):
            campaign.status = "scheduled" if scheduled_at_utc else "draft"

        # Reset les associations
        db.session.execute(
            campaign_contacts.delete().where(
                campaign_contacts.c.campaign_id == campaign.id
            )
        )
        for c in contacts:
            db.session.execute(
                campaign_contacts.insert().values(
                    campaign_id=campaign.id, contact_id=c.id
                )
            )

        db.session.commit()

        log_activity(
            action="campaign_update",
            description=f"Campagne modifiée : {campaign.name}",
        )
        flash("Campagne mise à jour.", "success")
        return redirect(url_for("campaigns.detail_campaign", campaign_id=campaign.id))

    return render_template(
        "campaigns/form.html", form=form, campaign=campaign, business=business
    )


# ==================================================
# SUPPRESSION
# ==================================================
@campaigns_bp.route("/<int:campaign_id>/delete", methods=["POST"])
@login_required
@require_business
def delete_campaign(campaign_id: int):
    business = get_current_business()
    campaign = Campaign.query.filter_by(
        id=campaign_id, business_id=business.id
    ).first_or_404()

    if campaign.status == "running":
        flash("Impossible de supprimer une campagne en cours. Arrêtez-la d'abord.", "warning")
        return redirect(url_for("campaigns.detail_campaign", campaign_id=campaign.id))

    name = campaign.name
    db.session.delete(campaign)
    db.session.commit()

    log_activity(
        action="campaign_delete",
        description=f"Campagne supprimée : {name}",
    )
    flash(f"Campagne « {name} » supprimée.", "info")
    return redirect(url_for("campaigns.list_campaigns"))


# ==================================================
# ACTIONS : DÉMARRER / PAUSE / REPRENDRE / ANNULER
# ==================================================
@campaigns_bp.route("/<int:campaign_id>/start", methods=["POST"])
@login_required
@require_business
def start_campaign(campaign_id: int):
    business = get_current_business()
    campaign = Campaign.query.filter_by(
        id=campaign_id, business_id=business.id
    ).first_or_404()

    try:
        CampaignService.start(campaign)
        flash("Campagne lancée.", "success")
    except ValueError as e:
        flash(str(e), "danger")
    return redirect(url_for("campaigns.detail_campaign", campaign_id=campaign.id))


@campaigns_bp.route("/<int:campaign_id>/pause", methods=["POST"])
@login_required
@require_business
def pause_campaign(campaign_id: int):
    business = get_current_business()
    campaign = Campaign.query.filter_by(
        id=campaign_id, business_id=business.id
    ).first_or_404()

    try:
        CampaignService.pause(campaign)
        flash("Campagne mise en pause.", "info")
    except ValueError as e:
        flash(str(e), "danger")
    return redirect(url_for("campaigns.detail_campaign", campaign_id=campaign.id))


@campaigns_bp.route("/<int:campaign_id>/resume", methods=["POST"])
@login_required
@require_business
def resume_campaign(campaign_id: int):
    business = get_current_business()
    campaign = Campaign.query.filter_by(
        id=campaign_id, business_id=business.id
    ).first_or_404()

    try:
        CampaignService.resume(campaign)
        flash("Campagne reprise.", "success")
    except ValueError as e:
        flash(str(e), "danger")
    return redirect(url_for("campaigns.detail_campaign", campaign_id=campaign.id))


@campaigns_bp.route("/<int:campaign_id>/cancel", methods=["POST"])
@login_required
@require_business
def cancel_campaign(campaign_id: int):
    business = get_current_business()
    campaign = Campaign.query.filter_by(
        id=campaign_id, business_id=business.id
    ).first_or_404()

    try:
        CampaignService.cancel(campaign)
        flash("Campagne annulée.", "warning")
    except ValueError as e:
        flash(str(e), "danger")
    return redirect(url_for("campaigns.detail_campaign", campaign_id=campaign.id))


# ==================================================
# QUOTAS
# ==================================================
def _check_campaign_quota(business) -> None:
    max_campaigns = business.plan_config.get("max_campaigns", 0)
    if max_campaigns == 0:
        return
    count = Campaign.query.filter_by(business_id=business.id).count()
    if count >= max_campaigns:
        flash(
            f"Quota de campagnes atteint ({max_campaigns}) pour le plan "
            f"'{business.plan}'. Passez à un plan supérieur.",
            "warning",
        )
        return redirect(url_for("subscriptions.current"))