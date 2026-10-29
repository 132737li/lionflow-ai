"""
Tests de l'intégration vocale WhatsApp (webhook + conversion OPUS).
"""

import os
import tempfile
from unittest.mock import patch, MagicMock

import pytest

from app.services import whatsapp_voice_service
from app.services.whatsapp_client import WhatsAppClient
from app.utils.audio_utils import convert_to_ogg_opus, AudioConversionError
from app.models.whatsapp_account import WhatsAppAccount
from app.models.voice_session import VoiceSession


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def waba_voice(db, business, waba_account):
    """Compte WhatsApp avec phone_number_id unique."""
    waba_account.phone_number_id = "voice_test_pnid"
    db.session.commit()
    return waba_account


@pytest.fixture
def fake_ogg_bytes():
    """Bytes factices (peu importe le contenu pour les mocks)."""
    return b"OggS\x00fake-opus-data"


# ---------------------------------------------------------------------------
# Webhook — vérification
# ---------------------------------------------------------------------------
def test_webhook_verify_ok(client, app):
    app.config["WHATSAPP_VERIFY_TOKEN"] = "secret123"
    resp = client.get(
        "/webhooks/whatsapp/voice?hub.mode=subscribe"
        "&hub.verify_token=secret123&hub.challenge=CHALLENGE"
    )
    assert resp.status_code == 200
    assert resp.data == b"CHALLENGE"


def test_webhook_verify_forbidden(client):
    resp = client.get(
        "/webhooks/whatsapp/voice?hub.mode=subscribe"
        "&hub.verify_token=wrong&hub.challenge=X"
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Webhook — réception audio
# ---------------------------------------------------------------------------
def test_webhook_audio_triggers_service(client, waba_voice):
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "changes": [{
                "value": {
                    "metadata": {"phone_number_id": waba_voice.phone_number_id},
                    "messages": [{
                        "from": "+33612345678",
                        "type": "audio",
                        "audio": {
                            "id": "MEDIA_IN_123",
                            "mime_type": "audio/ogg",
                        },
                    }],
                },
            }],
        }],
    }

    with patch.object(
        whatsapp_voice_service, "handle_incoming_voice"
    ) as mock_handle:
        resp = client.post("/webhooks/whatsapp/voice", json=payload)
        assert resp.status_code == 200
        mock_handle.assert_called_once()
        kwargs = mock_handle.call_args.kwargs
        assert kwargs["media_id"] == "MEDIA_IN_123"
        assert kwargs["from_number"] == "+33612345678"


def test_webhook_unknown_phone_number(client, db):
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "changes": [{
                "value": {
                    "metadata": {"phone_number_id": "unknown_pnid"},
                    "messages": [{"from": "+1", "type": "audio",
                                  "audio": {"id": "X"}}],
                },
            }],
        }],
    }
    with patch.object(
        whatsapp_voice_service, "handle_incoming_voice"
    ) as mock_handle:
        resp = client.post("/webhooks/whatsapp/voice", json=payload)
        assert resp.status_code == 200
        mock_handle.assert_not_called()


# ---------------------------------------------------------------------------
# Service — flow complet (mocks)
# ---------------------------------------------------------------------------
def test_handle_incoming_voice_full_flow(db, waba_voice, fake_ogg_bytes):
    with patch.object(
        WhatsAppClient, "download_media", return_value=fake_ogg_bytes
    ), patch.object(
        whatsapp_voice_service.voice_service, "transcribe_audio",
        return_value={"text": "Bonjour", "language": "fr", "provider": "mock"},
    ), patch.object(
        whatsapp_voice_service.voice_service, "synthesize_speech",
        return_value={"path": "/tmp/fake.mp3", "provider": "mock"},
    ), patch(
        "app.services.whatsapp_voice_service.convert_to_ogg_opus",
        return_value="/tmp/fake.opus.ogg",
    ), patch(
        "app.services.whatsapp_voice_service.get_audio_duration_seconds",
        return_value=2.5,
    ), patch.object(
        WhatsAppClient, "upload_audio", return_value="MEDIA_OUT_999"
    ), patch.object(
        WhatsAppClient, "send_audio_voice", return_value={"messages": [{"id": "wamid"}]}
    ), patch(
        "app.services.whatsapp_voice_service.generate_ai_response",
        return_value="Bonjour à vous !",
    ) as mock_ai:
        result = whatsapp_voice_service.handle_incoming_voice(
            account=waba_voice,
            from_number="+33612345678",
            media_id="MEDIA_IN_123",
        )

    assert result["ok"] is True
    assert result["fallback"] is None
    mock_ai.assert_called_once()

    session = VoiceSession.query.filter_by(business_id=waba_voice.business_id).first()
    assert session is not None
    assert session.turns_count >= 1


def test_handle_incoming_voice_fallback_text(db, waba_voice, fake_ogg_bytes):
    """Si la conversion OPUS échoue → fallback texte."""
    with patch.object(
        WhatsAppClient, "download_media", return_value=fake_ogg_bytes
    ), patch.object(
        whatsapp_voice_service.voice_service, "transcribe_audio",
        return_value={"text": "Salut", "language": "fr", "provider": "mock"},
    ), patch.object(
        whatsapp_voice_service.voice_service, "synthesize_speech",
        return_value={"path": "/tmp/fake.mp3", "provider": "mock"},
    ), patch(
        "app.services.whatsapp_voice_service.convert_to_ogg_opus",
        side_effect=AudioConversionError("ffmpeg missing"),
    ), patch(
        "app.services.whatsapp_voice_service.generate_ai_response",
        return_value="Réponse de secours",
    ), patch.object(
        WhatsAppClient, "send_text", return_value={"messages": [{"id": "wamid"}]}
    ) as mock_send_text:
        result = whatsapp_voice_service.handle_incoming_voice(
            account=waba_voice,
            from_number="+33612345678",
            media_id="MEDIA_IN_123",
        )

    assert result["ok"] is True
    assert result["fallback"] == "text"
    mock_send_text.assert_called_once()


# ---------------------------------------------------------------------------
# Utils — conversion
# ---------------------------------------------------------------------------
def test_convert_to_ogg_opus_requires_ffmpeg():
    with patch("app.utils.audio_utils._ffmpeg_available", return_value=False):
        with pytest.raises(AudioConversionError):
            convert_to_ogg_opus("/tmp/whatever.mp3")


def test_convert_to_ogg_opus_file_missing():
    with pytest.raises(AudioConversionError):
        convert_to_ogg_opus("/nonexistent/file.mp3")