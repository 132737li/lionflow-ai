"""
LionFlow AI — Modèles Webhook + WebhookDelivery.
Système de webhooks sortants signés HMAC-SHA256.
"""
from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone

from app.extensions import db


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _gen_secret() -> str:
    return f"whsec_{secrets.token_urlsafe(32)}"


class Webhook(db.Model):
    __tablename__ = "webhooks"
    __table_args__ = (
        db.Index("idx_webhook_business_active", "business_id", "is_active"),
    )

    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(
        db.Integer,
        db.ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = db.Column(db.String(120), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    secret = db.Column(db.String(120), nullable=False, default=_gen_secret)
    events = db.Column(db.Text, nullable=False, default="[]")
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    business = db.relationship("Business", backref="webhooks")
    deliveries = db.relationship(
        "WebhookDelivery",
        back_populates="webhook",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )

    def get_events(self) -> list:
        try:
            return json.loads(self.events or "[]")
        except (ValueError, TypeError):
            return []

    def set_events(self, events) -> None:
        self.events = json.dumps(sorted(set(events or [])))

    def subscribes_to(self, event: str) -> bool:
        evts = self.get_events()
        return "*" in evts or event in evts

    def __repr__(self):
        return f"<Webhook {self.id} {self.name} active={self.is_active}>"


class WebhookDelivery(db.Model):
    __tablename__ = "webhook_deliveries"
    __table_args__ = (
        db.Index("idx_wh_delivery_webhook_created", "webhook_id", "created_at"),
        db.Index("idx_wh_delivery_status_retry", "status", "next_retry_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    webhook_id = db.Column(
        db.Integer,
        db.ForeignKey("webhooks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event = db.Column(db.String(80), nullable=False, index=True)
    event_id = db.Column(db.String(64), nullable=False, index=True)
    payload = db.Column(db.Text, nullable=False)
    status = db.Column(
        db.Enum(
            "pending", "success", "failed", "retrying", "gave_up",
            name="webhook_delivery_status",
        ),
        nullable=False,
        default="pending",
        index=True,
    )
    attempts = db.Column(db.Integer, nullable=False, default=0)
    last_attempt_at = db.Column(db.DateTime)
    next_retry_at = db.Column(db.DateTime, index=True)
    response_status = db.Column(db.Integer)
    response_body = db.Column(db.Text)
    error = db.Column(db.Text)
    duration_ms = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)

    webhook = db.relationship("Webhook", back_populates="deliveries")

    def __repr__(self):
        return f"<WebhookDelivery {self.id} {self.event} [{self.status}]>"