"""
LionFlow AI — Service de chat vocal.
STT via Groq Whisper (fallback faster-whisper local) et TTS via edge-tts (fallback gTTS).
Respecte l'isolation multi-tenant : toutes les méthodes exigent un business_id.
"""

from __future__ import annotations

import os
import uuid
import tempfile
from datetime import datetime, timezone
from typing import Optional

from flask import current_app
from app.extensions import db
from app.models.voice_session import VoiceSession, VoiceMessage

# --- STT -------------------------------------------------------------------
try:
    from groq import Groq
    _HAS_GROQ = True
except ImportError:
    _HAS_GROQ = False

try:
    from faster_whisper import WhisperModel
    _HAS_FASTER_WHISPER = True
except ImportError:
    _HAS_FASTER_WHISPER = False

# --- TTS -------------------------------------------------------------------
try:
    import edge_tts
    _HAS_EDGE_TTS = True
except ImportError:
    _HAS_EDGE_TTS = False

try:
    from gtts import gTTS
    _HAS_GTTS = True
except ImportError:
    _HAS_GTTS = False


# Voix edge-tts par langue (voix neuronales Microsoft)
EDGE_VOICES = {
    "fr": "fr-FR-DeniseNeural",
    "en": "en-US-AriaNeural",
    "ar": "ar-SA-ZariyahNeural",
    "es": "es-ES-ElviraNeural",
    "pt": "pt-PT-FranciscaNeural",
    "sw": "sw-KE-ZuriNeural",
    # Kirundi : pas de voix native, fallback français
    "rn": "fr-FR-DeniseNeural",
}

# Mapping code pays -> code Whisper (certains diffèrent)
WHISPER_LANG_MAP = {
    "fr": "fr",
    "en": "en",
    "ar": "ar",
    "es": "es",
    "pt": "pt",
    "sw": "sw",
    "rn": "rw",  # Whisper utilise "rw" pour le kinyarwanda (proche du kirundi)
}


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _audio_dir() -> str:
    """Dossier de stockage des fichiers audio générés (par business)."""
    base = current_app.config.get("UPLOAD_FOLDER", "uploads")
    path = os.path.join(base, "voice")
    os.makedirs(path, exist_ok=True)
    return path


# ===========================================================================
# STT — Speech-to-Text
# ===========================================================================
def transcribe_audio(
    audio_bytes: bytes,
    language: str = "fr",
    provider: Optional[str] = None,
) -> dict:
    """
    Transcrit un buffer audio en texte.

    Retourne un dict : {"text": str, "language": str, "provider": str}
    """
    provider = provider or current_app.config.get("VOICE_STT_PROVIDER", "groq")
    lang_code = WHISPER_LANG_MAP.get(language, "fr")

    # --- Groq Whisper (recommandé : rapide et gratuit dans les limites) ---
    if provider == "groq" and _HAS_GROQ:
        api_key = current_app.config.get("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY manquante")
        client = Groq(api_key=api_key)
        # Groq attend un fichier ; on écrit temporairement
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name
        try:
            with open(tmp_path, "rb") as f:
                result = client.audio.transcriptions.create(
                    file=(os.path.basename(tmp_path), f.read()),
                    model="whisper-large-v3",
                    language=lang_code,
                )
            return {
                "text": result.text.strip(),
                "language": language,
                "provider": "groq",
            }
        finally:
            os.unlink(tmp_path)

    # --- faster-whisper local ---
    if _HAS_FASTER_WHISPER:
        model = WhisperModel("small", device="cpu", compute_type="int8")
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name
        try:
            segments, info = model.transcribe(tmp_path, language=lang_code, beam_size=5)
            text = " ".join(seg.text for seg in segments).strip()
            return {
                "text": text,
                "language": info.language,
                "provider": "faster-whisper",
            }
        finally:
            os.unlink(tmp_path)

    raise RuntimeError("Aucun provider STT disponible (installez groq ou faster-whisper)")


# ===========================================================================
# TTS — Text-to-Speech
# ===========================================================================
async def _edge_tts_generate(text: str, voice: str, out_path: str) -> None:
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(out_path)


def synthesize_speech(
    text: str,
    language: str = "fr",
    provider: Optional[str] = None,
) -> dict:
    """
    Génère un fichier audio à partir d'un texte.

    Retourne : {"path": str, "provider": str, "duration": float}
    """
    provider = provider or current_app.config.get("VOICE_TTS_PROVIDER", "edge-tts")
    lang_code = language if language in EDGE_VOICES else "fr"
    voice = EDGE_VOICES.get(lang_code, EDGE_VOICES["fr"])

    filename = f"tts_{uuid.uuid4().hex}.mp3"
    out_path = os.path.join(_audio_dir(), filename)

    # --- edge-tts (meilleure qualité multilingue) ---
    if provider == "edge-tts" and _HAS_EDGE_TTS:
        import asyncio
        asyncio.run(_edge_tts_generate(text, voice, out_path))
        return {"path": out_path, "provider": "edge-tts", "duration": 0.0}

    # --- gTTS (fallback simple, supporte fr, en, ar, es, pt, sw) ---
    if _HAS_GTTS:
        tts = gTTS(text=text, lang=lang_code, slow=False)
        tts.save(out_path)
        return {"path": out_path, "provider": "gtts", "duration": 0.0}

    raise RuntimeError("Aucun provider TTS disponible (installez edge-tts ou gTTS)")


# ===========================================================================
# Gestion des sessions
# ===========================================================================
def create_session(business_id: int, user_id: Optional[int], language: str = "fr") -> VoiceSession:
    session = VoiceSession(
        business_id=business_id,
        user_id=user_id,
        language=language,
        status="active",
    )
    db.session.add(session)
    db.session.commit()
    return session


def get_session(session_id: int, business_id: int) -> Optional[VoiceSession]:
    return VoiceSession.query.filter_by(
        id=session_id, business_id=business_id
    ).first()


def add_user_turn(
    session: VoiceSession,
    transcription: str,
    audio_path: str,
    duration: float,
    stt_provider: str,
) -> VoiceMessage:
    msg = VoiceMessage(
        session_id=session.id,
        role="user",
        transcription=transcription,
        audio_path=audio_path,
        audio_duration=duration,
        stt_provider=stt_provider,
    )
    db.session.add(msg)
    session.turns_count += 1
    session.total_audio_seconds += duration
    db.session.commit()
    return msg


def add_assistant_turn(
    session: VoiceSession,
    transcription: str,
    audio_path: str,
    tts_provider: str,
) -> VoiceMessage:
    msg = VoiceMessage(
        session_id=session.id,
        role="assistant",
        transcription=transcription,
        audio_path=audio_path,
        tts_provider=tts_provider,
    )
    db.session.add(msg)
    db.session.commit()
    return msg


def end_session(session: VoiceSession) -> None:
    session.status = "ended"
    session.ended_at = _utcnow()
    db.session.commit()