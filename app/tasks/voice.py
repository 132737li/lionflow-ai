"""
Tâches Celery pour le traitement vocal WhatsApp.

⚠️ Activable via `VOICE_ASYNC_ENABLED=true` dans `.env`.
Par défaut (false), le traitement reste synchrone dans le webhook.
"""
from __future__ import annotations

import logging

from app.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(
    name="voice.handle_incoming",
    bind=True,
    max_retries=2,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=120,
    retry_jitter=True,
)
def handle_incoming_voice_async(
    self,
    account_id: int,
    from_number: str,
    media_id: str,
    mime_type: str = "audio/ogg",
    caption: str | None = None,
) -> dict:
    """
    Traite une note vocale WhatsApp en arrière-plan.

    `account_id` (int) est passé au lieu de l'objet `account` car Celery
    sérialise les arguments en JSON — un objet SQLAlchemy ne l'est pas.
    """
    from app.extensions import db
    from app.models.whatsapp_account import WhatsAppAccount
    from app.services import whatsapp_voice_service

    account = db.session.get(WhatsAppAccount, account_id)
    if account is None:
        logger.warning(
            "[celery] voice.handle_incoming : account introuvable id=%s",
            account_id,
        )
        return {"ok": False, "reason": "account_not_found"}

    try:
        return whatsapp_voice_service.handle_incoming_voice(
            account=account,
            from_number=from_number,
            media_id=media_id,
            mime_type=mime_type,
            caption=caption,
        )
    except Exception:
        logger.exception("[celery] Erreur handle_incoming_voice_async")
        raise