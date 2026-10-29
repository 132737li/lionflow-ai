"""
LionFlow AI — Service vocal WhatsApp.
Orchestration complète : réception → transcription → IA → TTS → OPUS → envoi.
"""

from __future__ import annotations

import os
import uuid
from typing import Optional

from flask import current_app

from app.extensions import db
from app.models.whatsapp_account import WhatsAppAccount
from app.models.voice_session import VoiceSession, VoiceMessage
from app.services import voice_service
from app.services.ai_responder import generate_reply as generate_ai_response
from app.services.whatsapp_client import WhatsAppClient, WhatsAppAPIError
from app.utils.audio_utils import convert_to_ogg_opus, get_audio_duration_seconds


def get_account_by_phone_number_id(phone_number_id: str) -> Optional[WhatsAppAccount]:
    if not phone_number_id:
        return None
    return WhatsAppAccount.query.filter_by(phone_number_id=phone_number_id).first()


def _get_client(account: WhatsAppAccount) -> WhatsAppClient:
    access_token = None
    if hasattr(account, "get_access_token"):
        access_token = account.get_access_token()
    else:
        access_token = getattr(account, "access_token", None)

    if not access_token:
        raise WhatsAppAPIError("Token d'accès WhatsApp manquant")

    return WhatsAppClient(
        phone_number_id=account.phone_number_id,
        access_token=access_token,
    )


def _build_history(session: VoiceSession) -> list:
    """Construit l'historique conversationnel depuis les tours précédents."""
    if session is None:
        return []
    try:
        msgs = (
            session.messages
            .order_by(VoiceMessage.created_at.asc())
            .limit(20)
            .all()
        )
        history = []
        for m in msgs:
            if not m.transcription:
                continue
            role = "user" if m.role == "user" else "assistant"
            history.append({"role": role, "content": m.transcription})
        return history
    except Exception:
        return []


def handle_incoming_voice(
    account: WhatsAppAccount,
    from_number: str,
    media_id: str,
    mime_type: str = "audio/ogg",
    caption: Optional[str] = None,
) -> dict:
    client = _get_client(account)
    business_id = account.business_id

    # 1) Téléchargement
    audio_bytes = client.download_media(media_id)
    if not audio_bytes:
        raise WhatsAppAPIError("Média audio vide")

    audio_dir = voice_service._audio_dir()
    in_filename = f"wa_in_{uuid.uuid4().hex}.ogg"
    in_path = os.path.join(audio_dir, in_filename)
    with open(in_path, "wb") as f:
        f.write(audio_bytes)

    # 2) STT
    language = _detect_language(account)
    stt = voice_service.transcribe_audio(audio_bytes, language=language)
    user_text = stt.get("text", "").strip()
    if not user_text:
        client.send_text(
            from_number,
            "Je n'ai pas pu comprendre votre message vocal. Pouvez-vous réessayer ?",
        )
        return {"ok": False, "reason": "no_speech"}

    # 3) Session
    session = (
        VoiceSession.query
        .filter_by(business_id=business_id, status="active")
        .order_by(VoiceSession.created_at.desc())
        .first()
    )
    if session is None:
        session = voice_service.create_session(business_id, user_id=None, language=language)

    voice_service.add_user_turn(
        session,
        transcription=user_text,
        audio_path=in_path,
        duration=get_audio_duration_seconds(in_path),
        stt_provider=stt.get("provider", "unknown"),
    )

    # 4) Réponse IA avec historique
    history = _build_history(session)
    try:
        assistant_text = generate_ai_response(
            prompt=user_text,
            business_id=business_id,
            user_id=None,
            language=language,
            history=history,
        )
    except Exception as exc:
        current_app.logger.exception("IA voice reply failed")
        assistant_text = (
            "Désolé, je ne peux pas répondre pour le moment. "
            "Veuillez réessayer plus tard."
        )

    # 5) TTS → MP3
    tts = voice_service.synthesize_speech(assistant_text, language=language)
    mp3_path = tts["path"]

    # 6) Conversion OPUS
    try:
        opus_path = convert_to_ogg_opus(mp3_path)
    except Exception as exc:
        current_app.logger.warning("OPUS conversion failed, fallback texte : %s", exc)
        client.send_text(from_number, assistant_text)
        _save_assistant_message(session, assistant_text, None, "text_fallback")
        return {"ok": True, "fallback": "text"}

    # 7) Upload + envoi voix
    try:
        media_id_out = client.upload_audio(opus_path, mime_type="audio/ogg")
        client.send_audio_voice(from_number, media_id_out, voice=True)
    except Exception as exc:
        current_app.logger.warning("Voice send failed, fallback texte : %s", exc)
        client.send_text(from_number, assistant_text)
        _save_assistant_message(session, assistant_text, opus_path, "text_fallback")
        return {"ok": True, "fallback": "text"}

    _save_assistant_message(session, assistant_text, opus_path, tts["provider"])
    return {"ok": True, "fallback": None}


def _save_assistant_message(
    session: VoiceSession,
    text: str,
    audio_path: Optional[str],
    tts_provider: str,
) -> None:
    voice_service.add_assistant_turn(
        session,
        transcription=text,
        audio_path=audio_path or "",
        tts_provider=tts_provider,
    )


def _detect_language(account: WhatsAppAccount) -> str:
    business = getattr(account, "business", None)
    lang = getattr(business, "language", None) if business else None
    return lang or "fr"
