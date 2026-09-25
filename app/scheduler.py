"""
Planificateur de tâches (APScheduler) pour le mode développement.
En production, remplacer par Celery + Redis.
"""
import atexit
import logging
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler

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