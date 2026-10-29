"""
LionFlow AI — Configuration Celery.
"""
from __future__ import annotations

from celery import Celery
from flask import Flask


celery = Celery(__name__)


def init_celery(app: Flask) -> Celery:
    """
    Configure l'instance Celery à partir de la config Flask.
    """
    broker_url = app.config.get(
        "CELERY_BROKER_URL", "redis://localhost:6379/0"
    )
    result_backend = app.config.get(
        "CELERY_RESULT_BACKEND", broker_url
    )

    celery.conf.update(
        broker_url=broker_url,
        result_backend=result_backend,
        task_always_eager=bool(app.config.get("CELERY_TASK_ALWAYS_EAGER", False)),
        task_eager_propagates=True,
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
        task_default_queue="lionflow",
        task_track_started=True,
        task_time_limit=300,       # 5 min hard limit
        task_soft_time_limit=240,  # 4 min soft limit
        broker_connection_retry_on_startup=True,
        worker_max_tasks_per_child=100,
        worker_prefetch_multiplier=1,
        # ✅ TRÈS IMPORTANT : On dit à Celery où trouver les fichiers contenant les tâches
        imports=[
            "app.tasks.email",
            "app.tasks.webhooks",
            "app.tasks.voice",
        ]
    )

    class FlaskTask(celery.Task):
        """Task Celery qui encapsule le contexte Flask."""

        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = FlaskTask
    return celery