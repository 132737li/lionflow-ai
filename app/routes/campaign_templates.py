"""
Routes de gestion des templates de campagnes.
CRUD + affichage visuel + utilisation dans une campagne.
"""
from flask import (
    Blueprint, render_template, redirect, url_for, flash,
    request, jsonify,
)
from flask_login import login_required, current_user

from app.extensions import db
from app.models.campaign_template import CampaignTemplate
from app.models.template import Template
from app.models.media_file import MediaFile
from app.services.campaign_template_service import CampaignTemplateService
from app.utils.decorators import require_business, get_current_business
from app.utils.security import log_activity


campaign_templates_bp = Blueprint(
    "campaign_templates",
    __name__,
    url_prefix="/campaign-templates",
    template_folder="../templates/campaign_templates",
)


# ==================================================
# LISTE
# ==================================================
@campaign_templates_bp.route("/")
@login_required
@require_business
def list_templates():
    business = get_current_business()

    # Récupérer tous les templates disponibles
    CampaignTemplateService.ensure_global_templates()

    category = (request.args.get("category") or "").strip()
    q = (request.args.get("q") or "").strip()

    templates = CampaignTemplateService.get_for_business(
        business, category=category or None
    )

    # Filtrer par recherche
    if q:
        q_lower = q.lower()
        templates = [
            t for t in templates
            if q_lower in (t.name or "").lower()
            or q_lower in (t.description or "").lower()
            or q_lower in (t.default_message or "").lower()
        ]

    # Grouper par catégorie pour l'affichage
    grouped = {}
    for t in templates:
        grouped.setdefault(t.category, []).append(t)

    stats = CampaignTemplateService.stats(business)

    return render_template(
        "campaign_templates/list.html",
        business=business,
        templates=templates,
        grouped=grouped,
        categories=CampaignTemplateService.get_categories(),
        category_filter=category,
        q=q,
        stats=stats,
    )


# ==================================================
# DÉTAIL / APERÇU (AJAX)
# ==================================================
@campaign_templates_bp.route("/<int:template_id>/preview")
@login_required
@require_business
def preview(template_id: int):
    """Aperçu JSON d'un template (utilisé par la modale)."""
    business = get_current_business()
    tpl = CampaignTemplateService.get_by_id(template_id, business)

    if not tpl:
        return jsonify(success=False, message="Template introuvable"), 404

    return jsonify(
        success=True,
        template=tpl.to_dict(),
    )


# ==================================================
# CRÉATION
# ==================================================
@campaign_templates_bp.route("/new", methods=["GET", "POST"])
@login_required
@require_business
def create_template():
    business = get_current_business()

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        category = (request.form.get("category") or "autre").strip()
        description = (request.form.get("description") or "").strip()
        icon = (request.form.get("icon") or "📢").strip()
        default_message = (request.form.get("default_message") or "").strip()

        if not name:
            flash("Le nom du template est obligatoire.", "danger")
            return redirect(url_for("campaign_templates.create_template"))

        tpl = CampaignTemplateService.create(
            business=business,
            data={
                "name": name,
                "category": category,
                "description": description,
                "icon": icon,
                "default_message": default_message,
            },
        )

        log_activity(
            action="campaign_template_create",
            description=f"Template de campagne créé : {tpl.name}",
        )
        flash(f"Template « {tpl.name} » créé.", "success")
        return redirect(url_for("campaign_templates.list_templates"))

    return render_template(
        "campaign_templates/form.html",
        business=business,
        template=None,
        categories=CampaignTemplateService.get_categories(),
    )


# ==================================================
# MODIFICATION
# ==================================================
@campaign_templates_bp.route("/<int:template_id>/edit", methods=["GET", "POST"])
@login_required
@require_business
def edit_template(template_id: int):
    business = get_current_business()
    tpl = CampaignTemplate.query.filter_by(
        id=template_id, business_id=business.id
    ).first_or_404()

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        if not name:
            flash("Le nom du template est obligatoire.", "danger")
            return redirect(url_for("campaign_templates.edit_template", template_id=tpl.id))

        tpl.name = name[:150]
        tpl.category = (request.form.get("category") or "autre").strip()
        tpl.description = (request.form.get("description") or "").strip()[:500] or None
        tpl.icon = (request.form.get("icon") or "📢").strip()[:10]
        tpl.default_message = (request.form.get("default_message") or "").strip() or None
        db.session.commit()

        log_activity(
            action="campaign_template_update",
            description=f"Template de campagne modifié : {tpl.name}",
        )
        flash("Template mis à jour.", "success")
        return redirect(url_for("campaign_templates.list_templates"))

    return render_template(
        "campaign_templates/form.html",
        business=business,
        template=tpl,
        categories=CampaignTemplateService.get_categories(),
    )


# ==================================================
# SUPPRESSION
# ==================================================
@campaign_templates_bp.route("/<int:template_id>/delete", methods=["POST"])
@login_required
@require_business
def delete_template(template_id: int):
    business = get_current_business()
    tpl = CampaignTemplate.query.filter_by(
        id=template_id, business_id=business.id
    ).first_or_404()

    name = tpl.name
    db.session.delete(tpl)
    db.session.commit()

    log_activity(
        action="campaign_template_delete",
        description=f"Template de campagne supprimé : {name}",
    )
    flash(f"Template « {name} » supprimé.", "info")
    return redirect(url_for("campaign_templates.list_templates"))


# ==================================================
# DUPLIQUER UN TEMPLATE GLOBAL
# ==================================================
@campaign_templates_bp.route("/<int:template_id>/duplicate", methods=["POST"])
@login_required
@require_business
def duplicate_template(template_id: int):
    """Duplique un template (utile pour personnaliser un global)."""
    business = get_current_business()
    source = CampaignTemplateService.get_by_id(template_id, business)

    if not source:
        flash("Template introuvable.", "danger")
        return redirect(url_for("campaign_templates.list_templates"))

    new_tpl = CampaignTemplate(
        business_id=business.id,
        name=f"{source.name} (copie)",
        description=source.description,
        icon=source.icon,
        category=source.category,
        default_message=source.default_message,
        default_timezone=source.default_timezone,
        is_public=False,
        is_active=True,
    )
    db.session.add(new_tpl)
    db.session.commit()

    log_activity(
        action="campaign_template_duplicate",
        description=f"Template dupliqué : {source.name} → {new_tpl.name}",
    )
    flash("Template dupliqué. Vous pouvez maintenant le personnaliser.", "success")
    return redirect(url_for("campaign_templates.edit_template", template_id=new_tpl.id))