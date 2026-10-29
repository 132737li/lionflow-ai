"""
Tests des webhooks sortants.
"""
import json
from unittest.mock import patch, MagicMock

import pytest

from app.extensions import db
from app.models.webhook import Webhook, WebhookDelivery
from app.models.voice_session import VoiceSession, VoiceMessage
from app.services import webhook_service


@pytest.fixture
def webhook_obj(db, business):
    w = Webhook(business_id=business.id, name="Test hook", url="https://example.com/hook")
    w.set_events(["campaign.completed", "contact.created"])
    db.session.add(w)
    db.session.commit()
    return w


# ---------------------------------------------------------------------------
# CRUD UI
# ---------------------------------------------------------------------------
def test_list_webhooks_requires_login(client):
    resp = client.get("/webhooks/")
    assert resp.status_code == 302


def test_list_webhooks_renders(logged_client):
    resp = logged_client.get("/webhooks/")
    assert resp.status_code == 200
    assert b"webhooks.title" in resp.data or b"Webhooks" in resp.data


def test_create_webhook(logged_client, db, business):
    resp = logged_client.post("/webhooks/new", data={
        "name": "Mon hook",
        "url": "https://example.com/hook",
        "events": ["campaign.completed", "contact.created"],
        "description": "test",
    }, follow_redirects=False)
    assert resp.status_code == 302
    w = Webhook.query.filter_by(business_id=business.id, name="Mon hook").first()
    assert w is not None
    assert w.secret.startswith("whsec_")
    assert set(w.get_events()) == {"campaign.completed", "contact.created"}


def test_create_webhook_invalid_url(logged_client, db, business):
    resp = logged_client.post("/webhooks/new", data={
        "name": "Bad", "url": "not-a-url", "events": ["campaign.completed"],
    }, follow_redirects=True)
    assert Webhook.query.filter_by(name="Bad").count() == 0


def test_cross_tenant_detail_forbidden(logged_client, db, other_business):
    foreign = Webhook(business_id=other_business.id, name="Foreign", url="https://x.com/h")
    foreign.set_events(["campaign.completed"])
    db.session.add(foreign)
    db.session.commit()
    resp = logged_client.get(f"/webhooks/{foreign.id}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Signature
# ---------------------------------------------------------------------------
def test_signature_format():
    sig = webhook_service._sign("secret", b'{"a":1}')
    assert sig.startswith("sha256=")
    assert len(sig) == 7 + 64  # "sha256=" + 64 hex


def test_signature_deterministic():
    a = webhook_service._sign("s", b"payload")
    b = webhook_service._sign("s", b"payload")
    c = webhook_service._sign("other", b"payload")
    assert a == b
    assert a != c


# ---------------------------------------------------------------------------
# Dispatch + Deliveries
# ---------------------------------------------------------------------------
def test_dispatch_creates_delivery(db, business, webhook_obj):
    with patch("app.services.webhook_service.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200, text="OK")
        count = webhook_service.dispatch(
            "campaign.completed",
            {"campaign_id": 42},
            business.id,
        )
    assert count == 1
    d = WebhookDelivery.query.filter_by(webhook_id=webhook_obj.id).first()
    assert d is not None
    assert d.status == "success"
    assert d.response_status == 200
    assert d.attempts == 1


def test_dispatch_ignores_unsubscribed_event(db, business, webhook_obj):
    with patch("app.services.webhook_service.requests.post") as mock_post:
        count = webhook_service.dispatch("message.sent", {}, business.id)
    assert count == 0
    mock_post.assert_not_called()


def test_dispatch_isolated_by_business(db, business, other_business, webhook_obj):
    foreign = Webhook(business_id=other_business.id, name="F", url="https://x.com/h")
    foreign.set_events(["*"])
    db.session.add(foreign)
    db.session.commit()

    with patch("app.services.webhook_service.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200, text="OK")
        webhook_service.dispatch("campaign.completed", {}, business.id)
    assert mock_post.call_count == 1


def test_dispatch_retry_on_error(db, business, webhook_obj):
    import requests as _rq
    with patch("app.services.webhook_service.requests.post",
               side_effect=_rq.ConnectionError("fail")):
        webhook_service.dispatch("campaign.completed", {}, business.id)
    d = WebhookDelivery.query.filter_by(webhook_id=webhook_obj.id).first()
    assert d.status == "retrying"
    assert d.next_retry_at is not None


def test_dispatch_gave_up_after_max_attempts(db, business, webhook_obj):
    """Simule 5 échecs → gave_up. Force next_retry_at dans le passé."""
    import requests as _rq
    from datetime import datetime, timedelta

    with patch("app.services.webhook_service.requests.post",
               side_effect=_rq.ConnectionError("fail")):
        webhook_service.dispatch("campaign.completed", {}, business.id)

        for _ in range(webhook_service.MAX_ATTEMPTS - 1):
            # Force le retry immédiat (contourne les délais de backoff)
            d = WebhookDelivery.query.filter_by(webhook_id=webhook_obj.id).first()
            d.next_retry_at = datetime.utcnow() - timedelta(seconds=1)
            db.session.commit()

            webhook_service.retry_pending_deliveries()

    d = WebhookDelivery.query.filter_by(webhook_id=webhook_obj.id).first()
    assert d.status == "gave_up"
    assert d.attempts == webhook_service.MAX_ATTEMPTS

def test_notify_never_raises():
    with patch.object(webhook_service, "dispatch", side_effect=RuntimeError("boom")):
        result = webhook_service.notify("test.event", 1, foo="bar")
    assert result == 0


# ---------------------------------------------------------------------------
# Test endpoint
# ---------------------------------------------------------------------------
def test_test_endpoint(logged_client, db, webhook_obj):
    with patch("app.services.webhook_service.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200, text="OK")
        resp = logged_client.post(f"/webhooks/{webhook_obj.id}/test")
    assert resp.status_code == 302
    d = WebhookDelivery.query.filter_by(webhook_id=webhook_obj.id, event="webhook.test").first()
    assert d is not None
    assert d.status == "success"


def test_toggle_webhook(logged_client, db, webhook_obj):
    assert webhook_obj.is_active is True
    logged_client.post(f"/webhooks/{webhook_obj.id}/toggle")
    db.session.refresh(webhook_obj)
    assert webhook_obj.is_active is False