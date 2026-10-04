"""
Routes de gestion des médias (médiathèque).
CRUD complet : liste, upload, détail, suppression.
"""
import os

from flask import (
    Blueprint, render_template, redirect, url_for, flash,
    request, jsonify, send_file, current_app, abort,
)
from flask_login import login_required, current_user
from sqlalchemy import or_

from app.extensions import db
from app.models.media_file import MediaFile
from app.services.media_service import MediaService, MediaServiceError
from app.utils.decorators import require_business, get_current_business


media_bp = Blueprint("media", __name__, template_folder="../templates/media")


# ==================================================
# LISTE
# ==================================================
@media_bp.route("/")
@login_required
@require_business
def list_media():
    """Médiathèque : liste tous les médias de l'entreprise."""
    business = get_current_business()

    q = (request.args.get("q") or "").strip()
    media_type = (request.args.get("type") or "").strip()
    view = (request.args.get("view") or "grid").strip()  # grid | list
    page = request.args.get("page", 1, type=int)
    per_page = 24

    query = MediaFile.query.filter_by(business_id=business.id)

    # Recherche
    if q:
        query = query.filter(MediaFile.original_name.ilike(f"%{q}%"))

    # Filtre par type
    if media_type in ("image", "document", "video"):
        query = query.filter(MediaFile.media_type == media_type)

    pagination = query.order_by(MediaFile.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # Statistiques
    stats = MediaService.stats(business)

    return render_template(
        "media/list.html",
        business=business,
        medias=pagination.items,
        pagination=pagination,
        stats=stats,
        q=q,
        media_type_filter=media_type,
        view=view,
    )


# ==================================================
# UPLOAD (GET = page, POST = upload)
# ==================================================
@media_bp.route("/upload", methods=["GET", "POST"])
@login_required
@require_business
def upload():
    """Upload d'un ou plusieurs médias."""
    business = get_current_business()

    if request.method == "POST":
        files = request.files.getlist("files")
        caption = (request.form.get("caption") or "").strip()

        if not files or all(not f.filename for f in files):
            flash("Aucun fichier sélectionné.", "warning")
            return redirect(url_for("media.upload"))

        uploaded = 0
        errors = []

        for file in files:
            if not file or not file.filename:
                continue
            try:
                MediaService.upload(
                    business=business,
                    file_storage=file,
                    user_id=current_user.id,
                    caption=caption,
                )
                uploaded += 1
            except MediaServiceError as e:
                errors.append(f"{file.filename} : {e.message}")
            except Exception as e:
                current_app.logger.exception("Erreur upload média")
                errors.append(f"{file.filename} : erreur inattendue")

        if uploaded > 0:
            flash(f"{uploaded} fichier(s) uploadé(s) avec succès.", "success")
        if errors:
            for err in errors[:5]:  # limite à 5 messages
                flash(err, "danger")

        return redirect(url_for("media.list_media"))

    return render_template(
        "media/upload.html",
        business=business,
        max_image_mb=current_app.config.get("MAX_MEDIA_SIZE_IMAGE_MB", 5),
        max_video_mb=current_app.config.get("MAX_MEDIA_SIZE_VIDEO_MB", 16),
        max_doc_mb=current_app.config.get("MAX_MEDIA_SIZE_DOC_MB", 100),
    )


# ==================================================
# DÉTAIL
# ==================================================
@media_bp.route("/<int:media_id>")
@login_required
@require_business
def detail(media_id: int):
    """Aperçu détaillé d'un média."""
    business = get_current_business()
    media = MediaFile.query.filter_by(
        id=media_id, business_id=business.id
    ).first_or_404()

    return render_template(
        "media/detail.html",
        business=business,
        media=media,
    )


# ==================================================
# MODIFIER (légende)
# ==================================================
@media_bp.route("/<int:media_id>/edit", methods=["POST"])
@login_required
@require_business
def edit(media_id: int):
    """Modifie la légende d'un média."""
    business = get_current_business()
    media = MediaFile.query.filter_by(
        id=media_id, business_id=business.id
    ).first_or_404()

    new_caption = (request.form.get("caption") or "").strip()[:500]
    media.caption = new_caption or None
    db.session.commit()

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify(success=True, caption=media.caption)

    flash("Légende mise à jour.", "success")
    return redirect(url_for("media.detail", media_id=media.id))


# ==================================================
# SUPPRESSION
# ==================================================
@media_bp.route("/<int:media_id>/delete", methods=["POST"])
@login_required
@require_business
def delete(media_id: int):
    """Supprime un média."""
    business = get_current_business()
    media = MediaFile.query.filter_by(
        id=media_id, business_id=business.id
    ).first_or_404()

    name = media.original_name
    MediaService.delete(media, user_id=current_user.id)
    flash(f"Média « {name} » supprimé.", "info")

    return redirect(url_for("media.list_media"))


# ==================================================
# API JSON (pour sélecteur dans campagnes)
# ==================================================
@media_bp.route("/api/list")
@login_required
@require_business
def api_list():
    """Liste JSON des médias (pour le sélecteur de campagne)."""
    business = get_current_business()
    media_type = (request.args.get("type") or "").strip()
    q = (request.args.get("q") or "").strip()

    query = MediaFile.query.filter_by(business_id=business.id)

    if media_type in ("image", "document", "video"):
        query = query.filter(MediaFile.media_type == media_type)
    if q:
        query = query.filter(MediaFile.original_name.ilike(f"%{q}%"))

    medias = query.order_by(MediaFile.created_at.desc()).limit(100).all()

    return jsonify(
        success=True,
        medias=[m.to_dict() for m in medias],
    )

# ==================================================
# API — Récupérer un média par ID
# ==================================================
@media_bp.route("/api/<int:media_id>")
@login_required
@require_business
def api_get(media_id: int):
    """Retourne les détails JSON d'un média (pour aperçu AJAX)."""
    business = get_current_business()
    media = MediaFile.query.filter_by(
        id=media_id, business_id=business.id
    ).first()

    if not media:
        return jsonify(success=False, message="Média introuvable"), 404

    return jsonify(success=True, media=media.to_dict())


# ==================================================
# TÉLÉCHARGEMENT
# ==================================================
@media_bp.route("/<int:media_id>/download")
@login_required
@require_business
def download(media_id: int):
    """Télécharge un média."""
    business = get_current_business()
    media = MediaFile.query.filter_by(
        id=media_id, business_id=business.id
    ).first_or_404()

    full_path = os.path.join(
        current_app.config["MEDIA_UPLOAD_FOLDER"],
        media.stored_name,
    )

    if not os.path.exists(full_path):
        abort(404)

    return send_file(
        full_path,
        as_attachment=True,
        download_name=media.original_name,
        mimetype=media.mime_type,
    )