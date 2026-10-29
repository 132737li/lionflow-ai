"""
Tâche Celery pour l'envoi d'emails en arrière-plan.
"""
from __future__ import annotations

import logging

from app.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(
    name="email.send",
    bind=True,
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def send_email_async(
    self,
    to_email: str,
    subject: str,
    html_body: str,
    text_body: str = "",
    attachments: list | None = None,
) -> bool:
    from flask import current_app
    from flask_mail import Message
    from app.extensions import mail

    msg = Message(
        subject=subject,
        recipients=[to_email],
        html=html_body,
        body=text_body or "",
        sender=current_app.config.get("MAIL_DEFAULT_SENDER"),
    )

    if attachments:
        for att in attachments:
            msg.attach(
                filename=att.get("filename", "document.pdf"),
                content_type=att.get("content_type", "application/pdf"),
                data=att.get("data", b""),
            )

    try:
        mail.send(msg)
        return True
    except Exception:
        logger.exception("[celery] Erreur envoi email à %s", to_email)
        raise