"""Routes templates de messages — stub (à compléter en PARTIE 6)."""
from flask import Blueprint, render_template
from flask_login import login_required


templates_bp = Blueprint("templates", __name__, template_folder="../templates/templates")


@templates_bp.route("/")
@login_required
def list_templates():
    return render_template("_placeholder.html", title="Modèles de messages", icon="file-text")

"""
CRUD des modèles de messages.
Multi-tenant : filtré par business_id.
"""
from flask import (
    Blueprint, render_template, redirect, url_for, flash, request,
)
from flask_login import login_required
from sqlalchemy import or_

from app.extensions import db
from app.forms.template_forms import TemplateForm
from app.models.template import Template
from app.utils.decorators import require_business, get_current_business
from app.utils.security import log_activity


templates_bp = Blueprint("templates", __name__, template_folder="../templates/templates")


# ==================================================
# LISTE
# ==================================================
@templates_bp.route("/")
@login_required
@require_business
def list_templates():
    business = get_current_business()
    q = (request.args.get("q") or "").strip()
    category = (request.args.get("category") or "").strip()
    page = request.args.get("page", 1, type=int)
    per_page = 12

    query = Template.query.filter_by(business_id=business.id)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            Template.name.ilike(like),
            Template.content.ilike(like),
        ))
    if category:
        query = query.filter(Template.category == category)

    pagination = query.order_by(Template.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # Compteur d'utilisations (nb de campagnes)
    from app.models.campaign import Campaign
    usage_counts = dict(
        db.session.query(Campaign.template_id, db.func.count(Campaign.id))
        .filter(Campaign.business_id == business.id, Campaign.template_id.isnot(None))
        .group_by(Campaign.template_id)
        .all()
    )

    return render_template(
        "templates/list.html",
        templates=pagination.items,
        pagination=pagination,
        business=business,
        q=q,
        category_filter=category,
        usage_counts=usage_counts,
    )


# ==================================================
# CRÉATION
# ==================================================
@templates_bp.route("/new", methods=["GET", "POST"])
@login_required
@require_business
def create_template():
    business = get_current_business()
    form = TemplateForm()

    # Pré-remplissage par catégorie si fournie en GET
    preset = request.args.get("preset")
    if request.method == "GET" and preset:
        presets = {
            "bienvenue": "Bonjour {{prenom}},\n\nBienvenue chez {{entreprise}} ! "
                         "Nous sommes ravis de vous compter parmi nous.",
            "promotion": "Bonjour {{prenom}},\n\nProfitez de notre offre exclusive "
                         "-20% valable cette semaine chez {{entreprise}} !",
            "rappel": "Bonjour {{prenom}},\n\nPetit rappel : votre rendez-vous "
                      "approche. À bientôt chez {{entreprise}} !",
            "confirmation": "Bonjour {{prenom}},\n\nVotre commande a bien été confirmée. "
                            "Merci pour votre confiance chez {{entreprise}}.",
            "anniversaire": "Joyeux anniversaire {{prenom}} ! 🎉 Toute l'équipe "
                            "{{entreprise}} vous souhaite une merveilleuse journée.",
        }
        if preset in presets:
            form.content.data = presets[preset]

    if form.validate_on_submit():
        template = Template(
            business_id=business.id,
            name=form.name.data.strip(),
            category=form.category.data,
            language=form.language.data,
            content=form.content.data.strip(),
        )
        db.session.add(template)
        db.session.commit()

        log_activity(
            action="template_create",
            description=f"Modèle créé : {template.name}",
        )
        flash("Modèle créé.", "success")
        return redirect(url_for("templates.list_templates"))

    return render_template("templates/form.html", form=form, template=None, business=business)


# ==================================================
# MODIFICATION
# ==================================================
@templates_bp.route("/<int:template_id>/edit", methods=["GET", "POST"])
@login_required
@require_business
def edit_template(template_id: int):
    business = get_current_business()
    template = Template.query.filter_by(
        id=template_id, business_id=business.id
    ).first_or_404()

    form = TemplateForm(obj=template)
    if form.validate_on_submit():
        template.name = form.name.data.strip()
        template.category = form.category.data
        template.language = form.language.data
        template.content = form.content.data.strip()
        db.session.commit()

        log_activity(
            action="template_update",
            description=f"Modèle modifié : {template.name}",
        )
        flash("Modèle mis à jour.", "success")
        return redirect(url_for("templates.list_templates"))

    return render_template("templates/form.html", form=form, template=template, business=business)


# ==================================================
# SUPPRESSION
# ==================================================
@templates_bp.route("/<int:template_id>/delete", methods=["POST"])
@login_required
@require_business
def delete_template(template_id: int):
    business = get_current_business()
    template = Template.query.filter_by(
        id=template_id, business_id=business.id
    ).first_or_404()

    name = template.name
    db.session.delete(template)
    db.session.commit()

    log_activity(
        action="template_delete",
        description=f"Modèle supprimé : {name}",
    )
    flash(f"Modèle « {name} » supprimé.", "info")
    return redirect(url_for("templates.list_templates"))


# ==================================================
# APERÇU (AJAX)
# ==================================================
@templates_bp.route("/<int:template_id>/preview")
@login_required
@require_business
def preview_template(template_id: int):
    """Retourne le rendu HTML avec des variables d'exemple."""
    from flask import jsonify
    business = get_current_business()
    template = Template.query.filter_by(
        id=template_id, business_id=business.id
    ).first_or_404()

    class _Fake:
        first_name = "Jean"
        last_name = "Dupont"
        company = "ACME"
        phone = "+33612345678"
        email = "jean@exemple.com"

    rendered = template.render(_Fake())
    return jsonify(success=True, content=rendered, template=template.to_dict())