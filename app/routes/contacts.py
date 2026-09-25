"""
CRUD complet des contacts + import CSV/Excel.
Filtrage multi-tenant : l'utilisateur ne voit que les contacts de l'entreprise active.
Pays par défaut : Burundi (+257). Tous les pays acceptés.
"""
import phonenumbers

from flask import (
    Blueprint, render_template, redirect, url_for, flash,
    request, current_app, abort,
)
from flask_login import login_required, current_user
from sqlalchemy import or_

from app.extensions import db
from app.forms.contact_forms import ContactForm, ImportContactsForm, ContactSearchForm
from app.models.contact import Contact
from app.services.contact_import_service import ContactImportService
from app.utils.decorators import require_business, get_current_business
from app.utils.security import log_activity
from app.utils.validators import allowed_file, normalize_phone


contacts_bp = Blueprint("contacts", __name__, template_folder="../templates/contacts")


# ==================================================
# HELPER — Fusionner indicatif + numéro
# ==================================================
def _merge_country_and_phone(country_code: str, raw_phone: str) -> str | None:
    """
    Fusionne l'indicatif du pays sélectionné avec le numéro saisi.
    - Si le numéro contient déjà un '+', on le respecte (international).
    - Sinon, on préfixe avec l'indicatif du pays choisi.
    Retourne le numéro au format E.164 (+XXX...) ou None si invalide.
    """
    if not raw_phone:
        return None
    raw = str(raw_phone).strip()

    # Si l'utilisateur a déjà tapé +XXX..., on valide tel quel
    if raw.startswith("+"):
        return normalize_phone(raw, default_region="BI")

    # Sinon, on ajoute l'indicatif du pays sélectionné
    region = country_code or "BI"
    if region == "OTHER":
        region = "BI"
    return normalize_phone(raw, default_region=region)


# ==================================================
# LISTE + RECHERCHE + FILTRES + PAGINATION
# ==================================================
@contacts_bp.route("/")
@login_required
@require_business
def list_contacts():
    business = get_current_business()

    q = (request.args.get("q") or "").strip()
    status = (request.args.get("status") or "").strip()
    tag = (request.args.get("tag") or "").strip()
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 20, type=int), 100)

    query = Contact.query.filter_by(business_id=business.id)

    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            Contact.first_name.ilike(like),
            Contact.last_name.ilike(like),
            Contact.phone.ilike(like),
            Contact.email.ilike(like),
            Contact.company.ilike(like),
        ))

    if status and status in ("active", "inactive", "blocked"):
        query = query.filter(Contact.status == status)

    if tag:
        query = query.filter(Contact.tags.ilike(f"%{tag}%"))

    pagination = query.order_by(Contact.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    form = ContactSearchForm()
    form.q.data = q
    form.status.data = status
    form.tag.data = tag

    return render_template(
        "contacts/list.html",
        contacts=pagination.items,
        pagination=pagination,
        form=form,
        business=business,
        total=pagination.total,
        q=q,
        status_filter=status,
        tag_filter=tag,
    )


# ==================================================
# CRÉATION
# ==================================================
@contacts_bp.route("/new", methods=["GET", "POST"])
@login_required
@require_business
def create_contact():
    business = get_current_business()

    if not business.can_add_contact():
        flash(
            f"Quota de contacts atteint pour le plan '{business.plan}'. "
            "Passez à un plan supérieur.",
            "warning",
        )
        return redirect(url_for("subscriptions.current"))

    form = ContactForm()
    if form.validate_on_submit():
        # Fusionner indicatif pays + numéro
        final_phone = _merge_country_and_phone(
            form.country_code.data, form.phone.data
        )
        if not final_phone:
            flash("Numéro WhatsApp invalide.", "danger")
            return render_template(
                "contacts/form.html", form=form, contact=None, business=business
            )

        # Vérifier doublon
        existing = Contact.query.filter_by(
            business_id=business.id, phone=final_phone
        ).first()
        if existing:
            flash("Un contact avec ce numéro existe déjà.", "warning")
            return render_template(
                "contacts/form.html", form=form, contact=None, business=business
            )

        contact = Contact(
            business_id=business.id,
            first_name=(form.first_name.data or "").strip() or None,
            last_name=(form.last_name.data or "").strip() or None,
            phone=final_phone,
            email=(form.email.data or "").strip() or None,
            company=(form.company.data or "").strip() or None,
            status=form.status.data or "active",
        )
        if form.tags.data:
            tags = [t.strip() for t in form.tags.data.split(",") if t.strip()]
            contact.set_tags(tags)

        db.session.add(contact)
        db.session.commit()

        log_activity(
            action="contact_create",
            description=f"Contact créé : {contact.full_name} ({contact.phone})",
        )
        flash("Contact créé avec succès.", "success")
        return redirect(url_for("contacts.list_contacts"))

    return render_template("contacts/form.html", form=form, contact=None, business=business)


# ==================================================
# DÉTAIL
# ==================================================
@contacts_bp.route("/<int:contact_id>")
@login_required
@require_business
def detail_contact(contact_id: int):
    business = get_current_business()
    contact = Contact.query.filter_by(
        id=contact_id, business_id=business.id
    ).first_or_404()
    return render_template("contacts/detail.html", contact=contact, business=business)


# ==================================================
# MODIFICATION
# ==================================================
@contacts_bp.route("/<int:contact_id>/edit", methods=["GET", "POST"])
@login_required
@require_business
def edit_contact(contact_id: int):
    business = get_current_business()
    contact = Contact.query.filter_by(
        id=contact_id, business_id=business.id
    ).first_or_404()

    form = ContactForm(obj=contact)
    if request.method == "GET":
        form.tags.data = ", ".join(contact.tags_list)
        # Préremplir phone sans l'indicatif s'il correspond à un pays connu
        form.country_code.data = "BI"
        form.phone.data = contact.phone

    if form.validate_on_submit():
        final_phone = _merge_country_and_phone(
            form.country_code.data, form.phone.data
        )
        if not final_phone:
            flash("Numéro WhatsApp invalide.", "danger")
            return render_template(
                "contacts/form.html", form=form, contact=contact, business=business
            )

        # Vérifier doublon (autre contact avec le même numéro)
        dup = Contact.query.filter(
            Contact.business_id == business.id,
            Contact.phone == final_phone,
            Contact.id != contact.id,
        ).first()
        if dup:
            flash("Un autre contact utilise déjà ce numéro.", "warning")
            return render_template(
                "contacts/form.html", form=form, contact=contact, business=business
            )

        contact.first_name = (form.first_name.data or "").strip() or None
        contact.last_name = (form.last_name.data or "").strip() or None
        contact.phone = final_phone
        contact.email = (form.email.data or "").strip() or None
        contact.company = (form.company.data or "").strip() or None
        contact.status = form.status.data or "active"
        if form.tags.data:
            tags = [t.strip() for t in form.tags.data.split(",") if t.strip()]
            contact.set_tags(tags)
        else:
            contact.tags = None

        db.session.commit()

        log_activity(
            action="contact_update",
            description=f"Contact modifié : {contact.full_name} ({contact.phone})",
        )
        flash("Contact mis à jour.", "success")
        return redirect(url_for("contacts.list_contacts"))

    return render_template("contacts/form.html", form=form, contact=contact, business=business)


# ==================================================
# SUPPRESSION
# ==================================================
@contacts_bp.route("/<int:contact_id>/delete", methods=["POST"])
@login_required
@require_business
def delete_contact(contact_id: int):
    business = get_current_business()
    contact = Contact.query.filter_by(
        id=contact_id, business_id=business.id
    ).first_or_404()

    name = contact.full_name
    db.session.delete(contact)
    db.session.commit()

    log_activity(
        action="contact_delete",
        description=f"Contact supprimé : {name} (id={contact_id})",
    )
    flash(f"Contact « {name} » supprimé.", "info")
    return redirect(url_for("contacts.list_contacts"))


# ==================================================
# IMPORT CSV / EXCEL
# ==================================================
@contacts_bp.route("/import", methods=["GET", "POST"])
@login_required
@require_business
def import_contacts():
    business = get_current_business()
    form = ImportContactsForm()

    report = None
    if form.validate_on_submit():
        file = form.file.data

        if not allowed_file(file.filename, current_app.config["ALLOWED_IMPORT_EXTENSIONS"]):
            flash("Extension non autorisée. Formats acceptés : CSV, XLSX, XLS.", "danger")
            return render_template("contacts/import.html", form=form, business=business, report=None)

        report = ContactImportService.import_file(file, business)
        # 🔍 DEBUG TEMPORAIRE
        import sys
        print(f"\n🔍 IMPORT DEBUG:", file=sys.stderr)
        print(f"🔍   fichier = {file.filename}", file=sys.stderr)
        print(f"🔍   business_id = {business.id}", file=sys.stderr)
        print(f"🔍   total_rows = {report.total_rows}", file=sys.stderr)
        print(f"🔍   added = {report.added}", file=sys.stderr)
        print(f"🔍   duplicates = {report.duplicates}", file=sys.stderr)
        print(f"🔍   errors = {report.errors[:3]}", file=sys.stderr)
        print(f"🔍   detected_columns = {report.detected_columns}", file=sys.stderr)
        
        

        log_activity(
            action="contact_import",
            description=(
                f"Import contacts ({file.filename}) : "
                f"{report.added} ajoutés, {report.duplicates} doublons, "
                f"{len(report.errors)} erreurs"
            ),
        )

        if report.added > 0:
            flash(f"Import terminé : {report.added} contact(s) ajouté(s).", "success")
        elif report.duplicates > 0:
            flash(
                f"Aucun nouveau contact ajouté — {report.duplicates} doublon(s) détecté(s).",
                "warning",
            )
        else:
            flash("Aucun contact importé. Consultez le rapport ci-dessous.", "warning")

    return render_template("contacts/import.html", form=form, business=business, report=report)


# ==================================================
# SUPPRESSION EN MASSE
# ==================================================
@contacts_bp.route("/bulk-delete", methods=["POST"])
@login_required
@require_business
def bulk_delete():
    business = get_current_business()
    ids = request.form.getlist("contact_ids")
    if not ids:
        flash("Aucun contact sélectionné.", "warning")
        return redirect(url_for("contacts.list_contacts"))

    try:
        ids = [int(i) for i in ids]
    except ValueError:
        flash("Identifiants invalides.", "danger")
        return redirect(url_for("contacts.list_contacts"))

    deleted = (
        Contact.query
        .filter(Contact.business_id == business.id, Contact.id.in_(ids))
        .delete(synchronize_session=False)
    )
    db.session.commit()

    log_activity(
        action="contact_bulk_delete",
        description=f"{deleted} contact(s) supprimé(s) en masse",
    )
    flash(f"{deleted} contact(s) supprimé(s).", "success")
    return redirect(url_for("contacts.list_contacts"))