"""
Tests de l'intégration Celery.
"""
from unittest.mock import patch

import pytest

from app.services import webhook_service


def test_celery_disabled_by_default_in_tests(app):
    """En mode test, Celery doit être désactivé (fallback synchrone)."""
    assert app.config.get("CELERY_ENABLED") is False


def test_celery_always_eager_in_tests(app):
    """En mode test, eager mode activé (si Celery existe)."""
    assert app.config.get("CELERY_TASK_ALWAYS_EAGER") is True


def test_notify_sync_when_celery_disabled(app, db, business):
    """Avec CELERY_ENABLED=False → exécution synchrone directe."""
    with patch.object(webhook_service, "dispatch", return_value=2) as mock_dispatch:
        count = webhook_service.notify("campaign.completed", business.id, test=True)

    assert count == 2
    mock_dispatch.assert_called_once()
    args, kwargs = mock_dispatch.call_args
    assert args[0] == "campaign.completed"
    assert args[2] == business.id


def test_notify_fallback_when_enqueue_fails(app, db, business):
    """Si Celery enqueue échoue → fallback synchrone."""
    # Force CELERY_ENABLED=True dans le contexte
    app.config["CELERY_ENABLED"] = True
    try:
        with patch(
            "app.tasks.webhooks.dispatch_webhook_async.delay",
            side_effect=RuntimeError("broker down"),
        ), patch.object(
            webhook_service, "dispatch", return_value=1
        ) as mock_dispatch:
            count = webhook_service.notify(
                "campaign.completed", business.id, test=True
            )
        assert count == 1
        mock_dispatch.assert_called_once()
    finally:
        app.config["CELERY_ENABLED"] = False


def test_notify_never_raises_on_error():
    """notify() ne doit jamais lever d'exception."""
    with patch.object(webhook_service, "dispatch", side_effect=RuntimeError("boom")):
        count = webhook_service.notify("test.event", 999, foo="bar")
    assert count == 0


def test_celery_module_importable():
    """Le module Celery doit s'importer sans erreur."""
    from app.celery_app import celery
    assert celery is not None
    assert celery.conf.broker_url is not None


def test_tasks_registered():
    """Les tâches doivent être enregistrées."""
    from app.celery_app import celery
    # Import tardif pour déclencher l'enregistrement
    from app.tasks import webhooks, voice  # noqa: F401
    assert "webhooks.dispatch" in celery.tasks
    assert "voice.handle_incoming" in celery.tasks