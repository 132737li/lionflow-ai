"""
Tests du chat vocal.
"""

from datetime import datetime
import pytest
from app.models.voice_session import VoiceSession, VoiceMessage


@pytest.fixture
def voice_session(db, business):
    s = VoiceSession(business_id=business.id, language="fr", status="active")
    db.session.add(s)
    db.session.commit()
    return s


def test_voice_requires_login(client):
    resp = client.get("/voice/")
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers.get("Location", "")


def test_voice_page_renders(logged_client):
    resp = logged_client.get("/voice/")
    assert resp.status_code == 200
    assert b"voiceChat" in resp.data


def test_transcribe_requires_file(logged_client):
    resp = logged_client.post("/voice/api/transcribe")
    assert resp.status_code == 400
    assert "audio" in resp.get_json()["error"].lower()


def test_transcribe_empty_file(logged_client):
    data = {"audio": (b"", "empty.webm")}
    resp = logged_client.post(
        "/voice/api/transcribe", data=data, content_type="multipart/form-data"
    )
    assert resp.status_code == 400


def test_voice_session_isolation(db, business, other_business):
    from app.services import voice_service
    s1 = voice_service.create_session(business.id, None)
    s2 = voice_service.create_session(other_business.id, None)

    assert voice_service.get_session(s1.id, business.id) is not None
    assert voice_service.get_session(s1.id, other_business.id) is None
    assert voice_service.get_session(s2.id, business.id) is None


def test_end_session(logged_client, db, business, voice_session):
    resp = logged_client.post(f"/voice/api/session/{voice_session.id}/end")
    assert resp.status_code == 200
    db.session.refresh(voice_session)
    assert voice_session.status == "ended"
    assert voice_session.ended_at is not None