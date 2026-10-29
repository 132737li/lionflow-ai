"""
Tâches Celery pour les webhooks sortants.
"""
from __future__ import annotations

import logging

from app.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(
    name="webhooks.dispatch",
    bind=True,
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)
def dispatch_webhook_async(self, event: str, data: dict, business_id: int) -> int:
    """
    Exécute `webhook_service.dispatch()` en arrière-plan.

    Import tardif pour éviter les imports circulaires.
    """
    from app.services.webhook_service import dispatch

    try:
        return dispatch(event, data, business_id)
    except Exception:
        logger.exception("[celery] Erreur dispatch_webhook_async")
        raise