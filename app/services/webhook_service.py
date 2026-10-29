"""
LionFlow AI — Service de webhooks sortants.

Fonctions :
- dispatch(event, data, business_id)   → envoie à tous les webhooks souscrits
- notify(event, business_id, **data)    → helper silencieux (ne plante jamais)
- retry_pending_deliveries(limit)       → batch de retry (à scheduler)
- send_test(webhook)                    → payload de test
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
import uuid
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

import requests
from flask import current_app

from app.extensions import db
from app.models.webhook import Webhook, WebhookDelivery
from app.models.voice_session import VoiceSession, VoiceMessage

logger = logging.getLogger(__name__)

# Politique de retry : délais en secondes entre tentatives
# Retry #1 après 0s, #2 après 30s, #3 après 5min, #4 après 30min, #5 après 2h
RETRY_DELAYS = [0, 30, 300, 1800, 7200]
MAX_ATTEMPTS = len(RETRY_DELAYS)  # = 5
REQUEST_TIMEOUT = 10

SUPPORTED_EVENTS = [
    "campaign.created",
    "campaign.scheduled",
    "campaign.started",
    "campaign.paused",
    "campaign.resumed",
    "campaign.completed",
    "campaign.failed",
    "campaign.cancelled",
    "contact.created",
    "contact.updated",
    "contact.deleted",
    "message.sent",
    "message.delivered",
    "message.read",
    "message.failed",
    "voice.session.ended",
    "webhook.test",
]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _sign(secret: str, payload_bytes: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _is_valid_url(url: str) -> bool:
    if not url or not url.startswith(("http://", "https://")):
        return False
    if not current_app.config.get("TESTING"):
        host = (urlparse(url).hostname or "").lower()
        if host in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
            return current_app.config.get("WEBHOOK_ALLOW_LOCAL", False)
    return True


def build_payload(event: str, data: dict, business_id: int) -> dict:
    return {
        "id": f"evt_{uuid.uuid4().hex}",
        "event": event,
        "timestamp": _utcnow().isoformat() + "Z",
        "business_id": business_id,
        "api_version": "v1",
        "data": data,
    }


def dispatch(event: str, data: dict, business_id: int) -> int:
    """Dispatch vers tous les webhooks actifs souscrits. Retourne le nb ciblé."""
    webhooks = Webhook.query.filter_by(business_id=business_id, is_active=True).all()
    targets = [w for w in webhooks if w.subscribes_to(event)]
    if not targets:
        return 0

    payload = build_payload(event, data, business_id)
    count = 0
    for webhook in targets:
        try:
            _deliver(webhook, payload)
            count += 1
        except Exception:
            logger.exception("[webhooks] Erreur delivery webhook %s", webhook.id)
    return count


def _deliver(webhook: Webhook, payload: dict) -> WebhookDelivery:
    delivery = WebhookDelivery(
        webhook_id=webhook.id,
        event=payload["event"],
        event_id=payload["id"],
        payload=json.dumps(payload),
        status="pending",
    )
    db.session.add(delivery)
    db.session.flush()
    _attempt_delivery(webhook, delivery)
    db.session.commit()
    return delivery


def _attempt_delivery(webhook: Webhook, delivery: WebhookDelivery) -> None:
    payload_bytes = delivery.payload.encode("utf-8")
    signature = _sign(webhook.secret, payload_bytes)
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "LionFlow-Webhooks/1.0",
        "X-LionFlow-Event": delivery.event,
        "X-LionFlow-Delivery": str(delivery.id),
        "X-LionFlow-Event-Id": delivery.event_id,
        "X-LionFlow-Signature": signature,
    }

    delivery.attempts += 1
    delivery.last_attempt_at = _utcnow()
    start = time.perf_counter()

    try:
        resp = requests.post(
            webhook.url,
            data=payload_bytes,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=False,
        )
        delivery.response_status = resp.status_code
        delivery.response_body = (resp.text or "")[:2000]
        delivery.duration_ms = int((time.perf_counter() - start) * 1000)

        if 200 <= resp.status_code < 300:
            delivery.status = "success"
            delivery.next_retry_at = None
            delivery.error = None
        else:
            _schedule_retry(delivery, f"HTTP {resp.status_code}")

    except requests.RequestException as exc:
        delivery.error = str(exc)[:1000]
        delivery.duration_ms = int((time.perf_counter() - start) * 1000)
        _schedule_retry(delivery, str(exc)[:1000])


def _schedule_retry(delivery: WebhookDelivery, error: str) -> None:
    """Planifie la prochaine tentative ou abandonne si épuisé."""
    if delivery.attempts >= MAX_ATTEMPTS:
        delivery.status = "gave_up"
        delivery.next_retry_at = None
        delivery.error = (delivery.error or error or "")[:1000]
        return

    # ⚠️ FIX : index - 1 (après 1er échec → RETRY_DELAYS[0] = 0s)
    delay = RETRY_DELAYS[delivery.attempts - 1]
    delivery.status = "retrying"
    delivery.next_retry_at = _utcnow() + timedelta(seconds=delay)
    delivery.error = (error or "")[:1000]


def retry_pending_deliveries(limit: int = 50) -> dict:
    """Reprend les deliveries en attente dont next_retry_at est dépassé."""
    now = _utcnow()
    pending = (
        WebhookDelivery.query
        .filter(
            WebhookDelivery.status == "retrying",
            WebhookDelivery.next_retry_at.isnot(None),
            WebhookDelivery.next_retry_at <= now,
        )
        .order_by(WebhookDelivery.next_retry_at.asc())
        .limit(limit)
        .all()
    )
    results = {"processed": 0, "success": 0, "failed": 0}
    for delivery in pending:
        webhook = delivery.webhook
        if not webhook or not webhook.is_active:
            delivery.status = "gave_up"
            delivery.next_retry_at = None
            continue
        _attempt_delivery(webhook, delivery)
        results["processed"] += 1
        if delivery.status == "success":
            results["success"] += 1
        elif delivery.status == "gave_up":
            results["failed"] += 1
    db.session.commit()
    return results


def send_test(webhook: Webhook) -> WebhookDelivery:
    payload = build_payload(
        "webhook.test",
        {"message": "Ceci est un événement de test LionFlow.", "webhook_name": webhook.name},
        webhook.business_id,
    )
    return _deliver(webhook, payload)


def notify(event: str, business_id: int, **data) -> int:
    """
    Helper à appeler depuis n'importe quel service. Ne plante jamais.

    Si `CELERY_ENABLED=True` → enqueue vers Celery (async).
    Sinon → exécution synchrone (dev/test).

    En cas d'échec d'enqueue Celery (broker down), fallback synchrone.
    """
    try:
        # Détection Celery
        try:
            from flask import current_app
            celery_enabled = current_app.config.get("CELERY_ENABLED", False)
        except RuntimeError:
            celery_enabled = False

        if celery_enabled:
            try:
                from app.tasks.webhooks import dispatch_webhook_async

                dispatch_webhook_async.delay(event, data, business_id)
                return 1  # nombre de targets inconnu avant exécution
            except Exception:
                logger.exception(
                    "[webhooks] Enqueue Celery échoué, fallback synchrone "
                    "pour event=%s",
                    event,
                )
                # Fallback synchrone
                return dispatch(event, data, business_id)

        # Mode synchrone
        return dispatch(event, data, business_id)
    except Exception:
        logger.exception("[webhooks] Erreur notify %s", event)
        return 0