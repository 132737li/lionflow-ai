"""
LionFlow AI — Service du calendrier des campagnes.

⚠️ Aligné sur le modèle réel Campaign :
   - status Enum strict : draft, scheduled, running, paused, completed, cancelled
   - dates disponibles : scheduled_at, started_at, finished_at, created_at
   - compteur : total_contacts
   - titre : name
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Optional

from sqlalchemy import and_, or_

from app.extensions import db
from app.models.campaign import Campaign


# ---------------------------------------------------------------------------
# Mapping statut -> couleur / libellé (aligné sur l'Enum réel)
# ---------------------------------------------------------------------------
STATUS_COLORS: dict[str, str] = {
    "draft": "#6c757d",      # gris   — brouillon
    "scheduled": "#0d6efd",  # bleu   — planifiée
    "running": "#fd7e14",    # orange — en cours
    "paused": "#ffc107",     # jaune  — en pause
    "completed": "#198754",  # vert   — terminée
    "cancelled": "#adb5bd",  # gris c — annulée
}

STATUS_LABELS_FR: dict[str, str] = {
    "draft": "Brouillon",
    "scheduled": "Planifiée",
    "running": "En cours",
    "paused": "En pause",
    "completed": "Terminée",
    "cancelled": "Annulée",
}

# Aligné sur Campaign.can_start (draft, scheduled, paused).
EDITABLE_STATUSES = {"draft", "scheduled", "paused"}


def _color_for_status(status: Optional[str]) -> str:
    if not status:
        return STATUS_COLORS["draft"]
    return STATUS_COLORS.get(str(status).lower(), "#0d6efd")


def _label_for_status(status: Optional[str]) -> str:
    if not status:
        return STATUS_LABELS_FR["draft"]
    return STATUS_LABELS_FR.get(str(status).lower(), str(status))


def _event_date(campaign) -> Optional[datetime]:
    """Priorité : scheduled_at → started_at → finished_at → created_at."""
    for attr in ("scheduled_at", "started_at", "finished_at", "created_at"):
        value = getattr(campaign, attr, None)
        if value:
            return value
    return None


def _campaign_title(campaign) -> str:
    name = getattr(campaign, "name", None)
    if name:
        return str(name)
    return f"Campagne #{getattr(campaign, 'id', '?')}"


def get_campaigns_between(
    business_id: int,
    start: datetime,
    end: datetime,
    statuses: Optional[Iterable[str]] = None,
) -> list:
    """
    Récupère les campagnes d'un business dans une plage de dates.
    La plage s'applique en OR sur scheduled_at / started_at / finished_at / created_at.
    """
    query = Campaign.query.filter(Campaign.business_id == business_id)

    date_filters = []
    for attr in ("scheduled_at", "started_at", "finished_at", "created_at"):
        col = getattr(Campaign, attr, None)
        if col is not None:
            date_filters.append(
                and_(col.isnot(None), col >= start, col <= end)
            )

    if date_filters:
        query = query.filter(or_(*date_filters))

    if statuses:
        statuses_list = [str(s).strip().lower() for s in statuses if str(s).strip()]
        if statuses_list:
            query = query.filter(Campaign.status.in_(statuses_list))

    order_col = getattr(Campaign, "scheduled_at", None) or Campaign.id
    return query.order_by(order_col.asc()).all()


def campaign_to_event(campaign, business_id: int) -> Optional[dict]:
    if getattr(campaign, "business_id", None) != business_id:
        return None

    event_date = _event_date(campaign)
    if event_date is None:
        return None

    status = getattr(campaign, "status", None)
    status_str = str(status).lower() if status is not None else ""

    return {
        "id": str(campaign.id),
        "title": _campaign_title(campaign),
        "start": event_date.isoformat(),
        "color": _color_for_status(status),
        "textColor": "#ffffff",
        "editable": status_str in EDITABLE_STATUSES,
        "extendedProps": {
            "status": status_str,
            "status_label": _label_for_status(status),
            "total_contacts": getattr(campaign, "total_contacts", 0) or 0,
            "url": f"/campaigns/{campaign.id}",
            "edit_url": f"/campaigns/{campaign.id}/edit",
        },
    }


def get_events(
    business_id: int,
    start: datetime,
    end: datetime,
    statuses: Optional[Iterable[str]] = None,
) -> list[dict]:
    campaigns = get_campaigns_between(business_id, start, end, statuses)
    events: list[dict] = []
    for campaign in campaigns:
        event = campaign_to_event(campaign, business_id)
        if event:
            events.append(event)
    return events


def reschedule_campaign(
    campaign_id: int,
    business_id: int,
    new_start: datetime,
) -> Campaign:
    """
    Met à jour scheduled_at (drag & drop).
    Lève ValueError si la campagne est introuvable ou non replanifiable.
    """
    campaign = Campaign.query.filter_by(
        id=campaign_id, business_id=business_id
    ).first()

    if campaign is None:
        raise ValueError("Campagne introuvable")

    status_str = str(getattr(campaign, "status", "") or "").lower()
    if status_str not in EDITABLE_STATUSES:
        raise ValueError(
            f"Cette campagne ne peut pas être replanifiée (statut : {status_str})"
        )

    # Normalisation UTC naïf (cohérent avec le helper _utcnow() du modèle)
    if new_start.tzinfo is not None:
        new_start = new_start.astimezone(timezone.utc).replace(tzinfo=None)

    campaign.scheduled_at = new_start
    # updated_at est géré automatiquement par onupdate=_utcnow

    db.session.commit()
    return campaign