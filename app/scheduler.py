"""
Planificateur de tâches (APScheduler) pour le mode développement.
En production, remplacer par Celery + Redis.
"""
import atexit
import logging
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler

import app

_scheduler: BackgroundScheduler | None = None


def init_scheduler(app):
    """Initialise le scheduler une seule fois."""
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    _scheduler = BackgroundScheduler(timezone="UTC")

    def run_due_campaigns():
        with app.app_context():
            try:
                from app.services.campaign_service import CampaignService
                CampaignService.process_due_campaigns()
            except Exception:
                logging.getLogger("lionflow.scheduler").exception(
                    "Erreur lors du traitement des campagnes planifiées"
                )

    # Toutes les 60 secondes, on regarde les campagnes planifiées dues
    _scheduler.add_job(
        run_due_campaigns,
        "interval",
        seconds=60,
        id="process_due_campaigns",
        next_run_time=datetime.now(timezone.utc),
        replace_existing=True,
    )

    _scheduler.start()
    atexit.register(lambda: _scheduler.shutdown(wait=False))
    logging.getLogger("lionflow.scheduler").info("Scheduler démarré.")
    return _scheduler

# dans app/scheduler.py
from apscheduler.schedulers.background import BackgroundScheduler
from app.services import webhook_service

scheduler = BackgroundScheduler()

# Toutes les 60 secondes : retry pending deliveries
scheduler.add_job(
    func=lambda: _retry_webhook_job(),
    trigger="interval",
    seconds=60,
    id="webhook_retries",
    replace_existing=True,
)

def _retry_webhook_job():
    with app.app_context():
        try:
            result = webhook_service.retry_pending_deliveries(limit=50)
            if result["processed"]:
                app.logger.info("[webhooks] retries: %s", result)
        except Exception:
            app.logger.exception("[webhooks] retry job error")