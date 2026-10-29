# app/models/voice_session.py
"""
Modèle VoiceSession — historique des sessions de chat vocal.
Isolation multi-tenant par business_id.
"""
from datetime import datetime, timezone
from app.extensions import db


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class VoiceSession(db.Model):
    __tablename__ = "voice_sessions"
    __table_args__ = (
        db.Index("idx_voice_business_created", "business_id", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(
        db.Integer,
        db.ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Langue détectée ou choisie pour la session
    language = db.Column(db.String(8), default="fr")
    # Statut : active, ended
    status = db.Column(
        db.Enum("active", "ended", name="voice_session_status"),
        nullable=False,
        default="active",
        index=True,
    )
    # Compteurs
    turns_count = db.Column(db.Integer, nullable=False, default=0)
    total_audio_seconds = db.Column(db.Float, nullable=False, default=0.0)

    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)
    ended_at = db.Column(db.DateTime)

    # Relations
    business = db.relationship("Business", backref="voice_sessions")
    user = db.relationship("User", backref="voice_sessions")
    messages = db.relationship(
        "VoiceMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="VoiceMessage.created_at",
        lazy="dynamic",
    )

    def __repr__(self):
        return f"<VoiceSession {self.id} biz={self.business_id} [{self.status}]>"


class VoiceMessage(db.Model):
    __tablename__ = "voice_messages"
    __table_args__ = (
        db.Index("idx_voice_msg_session", "session_id", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(
        db.Integer,
        db.ForeignKey("voice_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = db.Column(
        db.Enum("user", "assistant", name="voice_message_role"),
        nullable=False,
    )
    # Contenu
    transcription = db.Column(db.Text)          # Texte reconnu (user) ou réponse (assistant)
    audio_path = db.Column(db.String(500))      # Chemin relatif vers le fichier audio
    audio_duration = db.Column(db.Float, default=0.0)
    # Métadonnées
    stt_provider = db.Column(db.String(32))     # "groq", "whisper_local", etc.
    tts_provider = db.Column(db.String(32))     # "edge-tts", "gtts", etc.
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)

    session = db.relationship("VoiceSession", back_populates="messages")

    def __repr__(self):
        return f"<VoiceMessage {self.id} {self.role} session={self.session_id}>"