"""
CRUD des entreprises (Business).
L'utilisateur ne voit que ses propres entreprises.
Pays par défaut : Burundi.
"""
import os
import secrets
from flask import (
    Blueprint, render_template, redirect, url_for, flash,
    request, current_app, abort, session,
)
from flask_login import login_required, current_user

from app.extensions import db
from app.forms.business_forms import BusinessForm
from app.models.business import Business
from app.models.subscription import Subscription
from app.models.business_member import BusinessMember
from app.models.role_change_request import RoleChangeRequest
from app.models.user import User
from app.services.member_service import MemberService
from app.utils.security import log_activity
from app.utils.validators import allowed_file, normalize_phone
from app.utils.decorators import require_business, get_current_business


businesses_bp = Blueprint("businesses", __name__, template_folder="../templates/businesses")


# ==================================================
# HELPERS
# ==================================================
def _merge_country_and_phone(country_code: str, raw_phone: str) -> str | None:
    """
    Fusionne intelligemment le pays et le numéro.
    - Si le numéro a un '+', il est prioritaire (ex: +33...).
    - Sinon, on utilise le pays sélectionné (ou BI).
    """
    if not raw_phone:
        return None
        
    raw = str(raw_phone).strip()
    
    # Si l'utilisateur a déjà tapé un format international (+...)
    if raw.startswith("+"):
        return normalize_phone(raw) # Pas besoin de default_region
        
    # Sinon, on préfixe avec le pays choisi
    region = country_code if country_code and country_code != "OTHER" else "BI"
    return normalize_phone(raw, default_region=region)


def _save_logo(file_storage, business_id: int) -> str | None:
    """Sauvegarde un logo et retourne le chemin relatif."""
    if not file_storage or not file_storage.filename:
        return None
    if not allowed_file(file_storage.filename, current_app.config["ALLOWED_UPLOAD_EXTENSIONS"]):
        flash("Format de logo non autorisé.", "warning")
        return None

    ext = file_storage.filename.rsplit(".", 1)[1].lower()
    filename = f"biz_{business_id}_{secrets.token_hex(6)}.{ext}"
    folder = os.path.join(current_app.config["UPLOAD_FOLDER"], "logos")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, filename)
    file_storage.save(path)
    return f"uploads/logos/{filename}"


# ==================================================
# LISTE
# ==================================================
@businesses_bp.route("/")
@login_required
def list_businesses():
    businesses = (
        Business.query
        .filter_by(owner_id=current_user.id)
        .order_by(Business.created_at.desc())
        .all()
    )
    return render_template("businesses/list.html", businesses=businesses)


# ==================================================
# CRÉATION
# ==================================================
@businesses_bp.route("/new", methods=["GET", "POST"])
@login_required
def create_business():
    form = BusinessForm()
    if form.validate_on_submit():
        # Fusionner indicatif pays + téléphone
        final_phone = None
        if form.phone.data:
            final_phone = _merge_country_and_phone(
                form.country.data, form.phone.data
            )

        business = Business(
            owner_id=current_user.id,
            name=form.name.data.strip(),
            email=(form.email.data or "").strip() or None,
            phone=final_phone,
            address=(form.address.data or "").strip() or None,
            country=form.country.data or "BI",
            # ✅ NOUVEAU
            app_name=(form.app_name.data or "").strip() or None,
            primary_color=form.primary_color.data or "#10b981",
            secondary_color=form.secondary_color.data or "#0ea5e9",
        )
        db.session.add(business)
        db.session.flush()

        logo_path = _save_logo(form.logo.data, business.id)
        if logo_path:
            business.logo_path = logo_path

        sub = Subscription(business_id=business.id, plan="free", status="active")
        db.session.add(sub)

        db.session.commit()

        session["active_business_id"] = business.id

        log_activity(
            action="business_create",
            description=f"Entreprise créée : {business.name} (id={business.id})",
        )
        flash(f"Entreprise « {business.name} » créée.", "success")
        return redirect(url_for("businesses.list_businesses"))

    return render_template("businesses/form.html", form=form, business=None)


# ==================================================
# DÉTAIL
# ==================================================
@businesses_bp.route("/<int:business_id>")
@login_required
def detail_business(business_id: int):
    business = Business.query.filter_by(
        id=business_id, owner_id=current_user.id
    ).first_or_404()
    return render_template("businesses/detail.html", business=business)


# ==================================================
# MODIFICATION
# ==================================================
@businesses_bp.route("/<int:business_id>/edit", methods=["GET", "POST"])
@login_required
def edit_business(business_id: int):
    business = Business.query.filter_by(
        id=business_id, owner_id=current_user.id
    ).first_or_404()

    form = BusinessForm(obj=business)
    if form.validate_on_submit():
        final_phone = None
        if form.phone.data:
            final_phone = _merge_country_and_phone(
                form.country.data, form.phone.data
            )

        business.name = form.name.data.strip()
        business.email = (form.email.data or "").strip() or None
        business.phone = final_phone
        business.address = (form.address.data or "").strip() or None
        business.country = form.country.data or "BI"
        # ✅ NOUVEAU
        business.app_name = (form.app_name.data or "").strip() or None
        business.primary_color = form.primary_color.data or "#10b981"
        business.secondary_color = form.secondary_color.data or "#0ea5e9"
        logo_path = _save_logo(form.logo.data, business.id)
        if logo_path:
            business.logo_path = logo_path

        db.session.commit()

        log_activity(
            action="business_update",
            description=f"Entreprise modifiée : {business.name} (id={business.id})",
        )
        flash("Entreprise mise à jour.", "success")
        return redirect(url_for("businesses.detail_business", business_id=business.id))

    return render_template("businesses/form.html", form=form, business=business)


# ==================================================
# SUPPRESSION
# ==================================================
@businesses_bp.route("/<int:business_id>/delete", methods=["POST"])
@login_required
def delete_business(business_id: int):
    business = Business.query.filter_by(
        id=business_id, owner_id=current_user.id
    ).first_or_404()

    name = business.name
    db.session.delete(business)
    db.session.commit()

    if session.get("active_business_id") == business_id:
        session.pop("active_business_id", None)

    log_activity(
        action="business_delete",
        description=f"Entreprise supprimée : {name} (id={business_id})",
    )
    flash(f"Entreprise « {name} » supprimée.", "info")
    return redirect(url_for("businesses.list_businesses"))


# ==================================================
# CHANGER D'ENTREPRISE ACTIVE
# ==================================================
@businesses_bp.route("/switch/<int:business_id>", methods=["POST"])
@login_required
def switch_business(business_id: int):
    business = Business.query.filter_by(
        id=business_id, owner_id=current_user.id
    ).first_or_404()
    session["active_business_id"] = business.id
    flash(f"Entreprise active : {business.name}", "success")
    return redirect(request.referrer or url_for("dashboard.index"))


# ==================================================
# GESTION DE L'ÉQUIPE
# ==================================================
@businesses_bp.route("/<int:business_id>/team", methods=["GET", "POST"])
@login_required
def team(business_id):
    # ✅ CORRECTION : On cherche l'entreprise par son ID en vérifiant que tu en es le propriétaire
    business = Business.query.filter_by(
        id=business_id, owner_id=current_user.id
    ).first_or_404()

    members = BusinessMember.query.filter_by(business_id=business.id).all()

    if request.method == "POST":
        email = request.form.get("email")
        try:
            MemberService.add_member(business, email, role="viewer")
            flash("Membre ajouté avec succès (rôle par défaut : Lecteur).", "success")
            return redirect(url_for("businesses.team", business_id=business.id))
        except ValueError as e:
            flash(str(e), "danger")

    return render_template("businesses/team.html", business=business, members=members)


@businesses_bp.route("/<int:business_id>/team/<int:user_id>/request-role", methods=["POST"])
@login_required
def request_role(business_id, user_id):
    # ✅ CORRECTION : Même logique ici
    business = Business.query.filter_by(
        id=business_id, owner_id=current_user.id
    ).first_or_404()
    
    target_user = User.query.get_or_404(user_id)
    new_role = request.form.get("new_role")

    if new_role not in ("admin", "editor", "viewer"):
        flash("Rôle invalide.", "danger")
        return redirect(url_for("businesses.team", business_id=business.id))

    try:
        MemberService.request_role_change(business, target_user, new_role, current_user)
        flash("Demande envoyée au Super Admin pour approbation.", "info")
    except ValueError as e:
        flash(str(e), "danger")

    return redirect(url_for("businesses.team", business_id=business.id))