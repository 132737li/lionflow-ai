"""
Modèle MediaFile — fichier média (image, PDF, vidéo) d'une entreprise.
Utilisé pour les campagnes WhatsApp et la médiathèque.
"""
from datetime import datetime, timezone
from app.extensions import db


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class MediaFile(db.Model):
    __tablename__ = "media_files"

    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(
        db.Integer,
        db.ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Nom de fichier original (pour l'utilisateur)
    original_name = db.Column(db.String(255), nullable=False)
    # Nom de stockage sur le disque (unique)
    stored_name = db.Column(db.String(255), nullable=False, unique=True)
    # Type MIME (image/jpeg, application/pdf, video/mp4...)
    mime_type = db.Column(db.String(100), nullable=False)
    # Catégorie : image, document, video
    media_type = db.Column(
        db.Enum("image", "document", "video", name="media_type"),
        nullable=False,
        index=True,
    )
    # Taille en octets
    size_bytes = db.Column(db.Integer, nullable=False, default=0)
    # Chemin relatif (uploads/media/xxx.jpg)
    file_path = db.Column(db.String(500), nullable=False)
    # URL publique (pour l'envoi WhatsApp Cloud API)
    public_url = db.Column(db.String(500))

    # Métadonnées optionnelles
    width = db.Column(db.Integer)
    height = db.Column(db.Integer)
    duration_seconds = db.Column(db.Integer)
    caption = db.Column(db.String(500))   # légende par défaut

    # Traçabilité
    created_by_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
    )
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow, index=True)

    # ----- Relations -----
    business = db.relationship("Business", backref=db.backref("media_files", lazy="dynamic"))
    created_by = db.relationship("User", foreign_keys=[created_by_id])

    # ----- Propriétés -----
    @property
    def size_human(self) -> str:
        """Taille lisible (ex : '245 Ko')."""
        size = self.size_bytes or 0
        if size < 1024:
            return f"{size} o"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} Ko"
        else:
            return f"{size / (1024 * 1024):.1f} Mo"

    @property
    def icon(self) -> str:
        """Icône Bootstrap selon le type."""
        return {
            "image": "bi-image",
            "document": "bi-file-earmark-pdf",
            "video": "bi-camera-video",
        }.get(self.media_type, "bi-file-earmark")

    @property
    def is_image(self) -> bool:
        return self.media_type == "image"

    @property
    def is_document(self) -> bool:
        return self.media_type == "document"

    @property
    def is_video(self) -> bool:
        return self.media_type == "video"

    def __repr__(self) -> str:
        return f"<MediaFile {self.id} {self.original_name} ({self.media_type})>"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "business_id": self.business_id,
            "original_name": self.original_name,
            "mime_type": self.mime_type,
            "media_type": self.media_type,
            "size_bytes": self.size_bytes,
            "size_human": self.size_human,
            "file_path": self.file_path,
            "public_url": self.public_url,
            "caption": self.caption,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }