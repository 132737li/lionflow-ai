"""
LionFlow AI — Routes du chat vocal.
Expose l'interface web, l'API de transcription et l'API de synthèse.
"""

from __future__ import annotations

import os
import uuid
from flask import (
    Blueprint, render_template, request, jsonify, current_app, send_from_directory,
)
from flask_login import login_required, current_user

from app.extensions import db
from app.services import voice_service
from app.services.ai_responder import generate_reply as generate_ai_response
from app.utils.decorators import require_business, get_current_business


voice_bp = Blueprint(
    "voice",
    __name__,
    template_folder="../templates/voice",
)


def _current_business_id() -> int:
    business = get_current_business()
    if business is None:
        from flask import abort
        abort(403)
    return int(business.id)


def _build_history(session) -> list:
    """Construit l'historique conversationnel à partir des tours précédents."""
    if session is None:
        return []
    try:
        from app.models.voice_session import VoiceMessage
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


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------
@voice_bp.route("/", methods=["GET"])
@login_required
@require_business
def chat():
    """Page de chat vocal."""
    return render_template("voice/chat.html")


# ---------------------------------------------------------------------------
# API : upload d'un enregistrement vocal
# ---------------------------------------------------------------------------
@voice_bp.route("/api/transcribe", methods=["POST"])
@login_required
@require_business
def api_transcribe():
    business_id = _current_business_id()

    if "audio" not in request.files:
        return jsonify({"error": "Aucun fichier audio fourni"}), 400

    audio_file = request.files["audio"]
    if audio_file.filename == "":
        return jsonify({"error": "Fichier vide"}), 400

    audio_bytes = audio_file.read()
    if len(audio_bytes) == 0:
        return jsonify({"error": "Fichier vide"}), 400

    language = request.form.get("language", current_user.language or "fr")

    # 1) STT
    try:
        stt_result = voice_service.transcribe_audio(
            audio_bytes, language=language
        )
    except Exception as exc:
        current_app.logger.exception("Erreur STT")
        return jsonify({"error": f"Transcription impossible : {exc}"}), 500

    user_text = stt_result["text"]
    if not user_text:
        return jsonify({"error": "Aucune parole détectée"}), 400

    # 2) Récupérer ou créer une session
    session_id = request.form.get("session_id", type=int)
    session = None
    if session_id:
        session = voice_service.get_session(session_id, business_id)
    if session is None:
        session = voice_service.create_session(business_id, current_user.id, language)

    # 3) Sauvegarder le tour utilisateur
    filename = f"user_{uuid.uuid4().hex}.ogg"
    user_audio_path = os.path.join(voice_service._audio_dir(), filename)
    with open(user_audio_path, "wb") as f:
        f.write(audio_bytes)
    voice_service.add_user_turn(
        session,
        transcription=user_text,
        audio_path=user_audio_path,
        duration=0.0,
        stt_provider=stt_result["provider"],
    )

    # 4) Générer la réponse IA avec l'historique
    history = _build_history(session)
    try:
        assistant_text = generate_ai_response(
            prompt=user_text,
            business_id=business_id,
            user_id=current_user.id,
            language=language,
            history=history,
            contact_name=current_user.full_name,
        )
    except Exception as exc:
        current_app.logger.exception("Erreur IA")
        assistant_text = "Désolé, je n'ai pas pu générer de réponse."

    # 5) TTS
    try:
        tts_result = voice_service.synthesize_speech(
            assistant_text, language=language
        )
        audio_filename = os.path.basename(tts_result["path"])
        tts_provider = tts_result["provider"]
    except Exception as exc:
        current_app.logger.exception("Erreur TTS")
        return jsonify({
            "user_text": user_text,
            "assistant_text": assistant_text,
            "assistant_audio_url": None,
            "error": f"Synthèse vocale impossible : {exc}",
            "session_id": session.id,
        }), 500

    # 6) Sauvegarder le tour assistant
    voice_service.add_assistant_turn(
        session,
        transcription=assistant_text,
        audio_path=tts_result["path"],
        tts_provider=tts_provider,
    )

    return jsonify({
        "user_text": user_text,
        "assistant_text": assistant_text,
        "assistant_audio_url": f"/voice/audio/{audio_filename}",
        "session_id": session.id,
    })


# ---------------------------------------------------------------------------
# Service des fichiers audio générés
# ---------------------------------------------------------------------------
@voice_bp.route("/audio/<path:filename>", methods=["GET"])
@login_required
@require_business
def serve_audio(filename):
    if "/" in filename or ".." in filename:
        from flask import abort
        abort(400)
    audio_dir = voice_service._audio_dir()
    return send_from_directory(audio_dir, filename)


# ---------------------------------------------------------------------------
# Fin de session
# ---------------------------------------------------------------------------
@voice_bp.route("/api/session/<int:session_id>/end", methods=["POST"])
@login_required
@require_business
def api_end_session(session_id: int):
    business_id = _current_business_id()
    session = voice_service.get_session(session_id, business_id)
    if session is None:
        return jsonify({"error": "Session introuvable"}), 404
    voice_service.end_session(session)
    return jsonify({"ok": True})