"""
Service de gestion des médias (images, PDF, vidéos).
Gère l'upload, la validation, le stockage et la suppression.
"""
import os
import secrets
from datetime import datetime, timezone

from flask import current_app
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models.media_file import MediaFile
from app.models.business import Business
from app.utils.security import log_activity


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


# Tailles max par type (en Mo) — adaptées aux limites WhatsApp Cloud API
WHATSAPP_LIMITS = {
    "image": 5,
    "video": 16,
    "document": 100,
}


class MediaServiceError(Exception):
    """Erreur métier du service média."""
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class MediaService:

    # ==================================================
    # DÉTECTION DU TYPE
    # ==================================================
    @staticmethod
    def detect_media_type(filename: str) -> str | None:
        """Retourne 'image', 'document' ou 'video' selon l'extension."""
        if not filename or "." not in filename:
            return None

        ext = filename.rsplit(".", 1)[1].lower()
        cfg = current_app.config

        if ext in cfg["ALLOWED_MEDIA_IMAGE_EXT"]:
            return "image"
        if ext in cfg["ALLOWED_MEDIA_DOC_EXT"]:
            return "document"
        if ext in cfg["ALLOWED_MEDIA_VIDEO_EXT"]:
            return "video"
        return None

    # ==================================================
    # VALIDATION
    # ==================================================
    @staticmethod
    def validate_file(file_storage) -> tuple[str, str]:
        """
        Valide un fichier uploadé.
        Retourne (media_type, extension) ou lève MediaServiceError.
        """
        if not file_storage or not file_storage.filename:
            raise MediaServiceError("Aucun fichier fourni.")

        filename = file_storage.filename
        media_type = MediaService.detect_media_type(filename)

        if not media_type:
            allowed = (
                list(current_app.config["ALLOWED_MEDIA_IMAGE_EXT"])
                + list(current_app.config["ALLOWED_MEDIA_DOC_EXT"])
                + list(current_app.config["ALLOWED_MEDIA_VIDEO_EXT"])
            )
            raise MediaServiceError(
                f"Format non autorisé. Formats acceptés : {', '.join(allowed)}"
            )

        ext = filename.rsplit(".", 1)[1].lower()

        # Vérifier la taille
        # Astuce : on se déplace à la fin pour connaître la taille
        file_storage.seek(0, os.SEEK_END)
        size_bytes = file_storage.tell()
        file_storage.seek(0)

        max_mb = WHATSAPP_LIMITS.get(media_type, 5)
        if size_bytes > max_mb * 1024 * 1024:
            raise MediaServiceError(
                f"Fichier trop volumineux. Maximum {max_mb} Mo pour les {media_type}s."
            )

        return media_type, ext

    # ==================================================
    # UPLOAD
    # ==================================================
    @staticmethod
    def upload(
        business: Business,
        file_storage,
        user_id: int | None = None,
        caption: str = "",
    ) -> MediaFile:
        """
        Upload un fichier et crée un MediaFile.
        Lève MediaServiceError en cas de problème.
        """
        media_type, ext = MediaService.validate_file(file_storage)

        # Générer un nom unique
        unique = secrets.token_hex(8)
        stored_name = f"{unique}.{ext}"

        # Chemin de stockage
        folder = current_app.config["MEDIA_UPLOAD_FOLDER"]
        os.makedirs(folder, exist_ok=True)
        full_path = os.path.join(folder, stored_name)

        # Sauvegarder
        file_storage.seek(0)
        file_storage.save(full_path)

        # Taille
        size_bytes = os.path.getsize(full_path)

        # Chemin relatif pour URL
        file_path = f"uploads/media/{stored_name}"

        # URL publique (servie par Flask static)
        base_url = current_app.config.get("APP_BASE_URL", "").rstrip("/")
        public_url = f"{base_url}/static/{file_path}"

        # Détecter les dimensions pour les images
        width, height = None, None
        if media_type == "image":
            try:
                from PIL import Image
                with Image.open(full_path) as img:
                    width, height = img.size
            except Exception:
                pass

        # Créer l'enregistrement
        media = MediaFile(
            business_id=business.id,
            original_name=secure_filename(file_storage.filename)[:255],
            stored_name=stored_name,
            mime_type=file_storage.mimetype or "application/octet-stream",
            media_type=media_type,
            size_bytes=size_bytes,
            file_path=file_path,
            public_url=public_url,
            width=width,
            height=height,
            caption=(caption or "").strip()[:500] or None,
            created_by_id=user_id,
        )
        db.session.add(media)
        db.session.commit()

        log_activity(
            action="media_upload",
            description=f"Média uploadé : {media.original_name} ({media.size_human})",
            user_id=user_id,
        )

        return media

    # ==================================================
    # SUPPRESSION
    # ==================================================
    @staticmethod
    def delete(media: MediaFile, user_id: int | None = None) -> bool:
        """Supprime un média (BDD + fichier disque)."""
        # Vérifier qu'aucune campagne n'utilise ce média
        # (dans une version future : bloquer la suppression si utilisé)
        # Pour l'instant, on supprime

        try:
            full_path = os.path.join(
                current_app.config["MEDIA_UPLOAD_FOLDER"],
                media.stored_name,
            )
            if os.path.exists(full_path):
                os.remove(full_path)
        except OSError as e:
            current_app.logger.warning(f"[Media] Impossible de supprimer le fichier : {e}")

        name = media.original_name
        db.session.delete(media)
        db.session.commit()

        log_activity(
            action="media_delete",
            description=f"Média supprimé : {name}",
            user_id=user_id,
        )
        return True

    # ==================================================
    # STATISTIQUES
    # ==================================================
    @staticmethod
    def stats(business: Business) -> dict:
        """Retourne les stats de la médiathèque."""
        from sqlalchemy import func

        total = MediaFile.query.filter_by(business_id=business.id).count()
        total_size = (
            db.session.query(func.sum(MediaFile.size_bytes))
            .filter(MediaFile.business_id == business.id)
            .scalar() or 0
        )

        by_type = dict(
            db.session.query(MediaFile.media_type, func.count(MediaFile.id))
            .filter(MediaFile.business_id == business.id)
            .group_by(MediaFile.media_type)
            .all()
        )

        return {
            "total": total,
            "total_size": total_size,
            "total_size_human": MediaService._human_size(total_size),
            "images": by_type.get("image", 0),
            "documents": by_type.get("document", 0),
            "videos": by_type.get("video", 0),
        }

    @staticmethod
    def _human_size(size: int) -> str:
        if size < 1024:
            return f"{size} o"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} Ko"
        elif size < 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024):.1f} Mo"
        else:
            return f"{size / (1024 * 1024 * 1024):.2f} Go"