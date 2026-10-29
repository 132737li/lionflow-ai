"""
LionFlow AI — Webhook WhatsApp dédié aux notes vocales.
"""
from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from app.services import whatsapp_voice_service


whatsapp_voice_bp = Blueprint(
    "whatsapp_voice",
    __name__,
)


# ---------------------------------------------------------------------------
# Vérification du webhook (Meta)
# ---------------------------------------------------------------------------
@whatsapp_voice_bp.route("/webhooks/whatsapp/voice", methods=["GET"])
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    expected = current_app.config.get("WHATSAPP_VERIFY_TOKEN")
    if mode == "subscribe" and token == expected:
        return challenge or "", 200
    return "Forbidden", 403


# ---------------------------------------------------------------------------
# Réception d'événements
# ---------------------------------------------------------------------------
@whatsapp_voice_bp.route("/webhooks/whatsapp/voice", methods=["POST"])
def receive_webhook():
    payload = request.get_json(silent=True) or {}
    try:
        _process_payload(payload)
    except Exception:
        current_app.logger.exception("WhatsApp voice webhook error")
    return jsonify({"status": "ok"}), 200


def _process_payload(payload: dict) -> None:
    if payload.get("object") != "whatsapp_business_account":
        return

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            metadata = value.get("metadata", {})
            phone_number_id = metadata.get("phone_number_id")
            if not phone_number_id:
                continue

            account = whatsapp_voice_service.get_account_by_phone_number_id(
                phone_number_id
            )
            if account is None:
                current_app.logger.warning(
                    "Compte WhatsApp inconnu pour phone_number_id=%s", phone_number_id
                )
                continue

            for msg in value.get("messages", []):
                _handle_message(account, msg)


def _handle_message(account, msg: dict) -> None:
    msg_type = msg.get("type")
    from_number = msg.get("from")
    if not from_number:
        return

    if msg_type == "audio":
        audio = msg.get("audio", {})
        media_id = audio.get("id")
        mime_type = audio.get("mime_type", "audio/ogg")
        if media_id:
            whatsapp_voice_service.handle_incoming_voice(
                account=account,
                from_number=from_number,
                media_id=media_id,
                mime_type=mime_type,
                caption=audio.get("caption"),
            )
        return

    if msg_type == "voice":
        voice = msg.get("voice", {})
        media_id = voice.get("id")
        if media_id:
            whatsapp_voice_service.handle_incoming_voice(
                account=account,
                from_number=from_number,
                media_id=media_id,
                mime_type=voice.get("mime_type", "audio/ogg"),
            )
        return