"""
LionFlow AI — Service du calendrier des campagnes.

Fournit les opérations métier nécessaires au calendrier visuel :
- récupération des campagnes dans une plage de dates (scopée au business) ;
- conversion au format événement FullCalendar ;
- replanification d'une campagne (drag & drop).

Respecte l'isolation multi-tenant : toute opération exige un business_id.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Optional

from sqlalchemy import and_, or_

from app.extensions import db

# À ADAPTER si le chemin d'import du modèle diffère dans ton projet.
from app.models.campaign import Campaign


# ---------------------------------------------------------------------------
# Mapping statut -> couleur d'affichage
# ---------------------------------------------------------------------------
STATUS_COLORS: dict[str, str] = {
    "draft": "#6c757d",      # gris
    "scheduled": "#0d6efd",  # bleu
    "queued": "#0d6efd",
    "running": "#fd7e14",    # orange
    "sending": "#fd7e14",
    "processing": "#fd7e14",
    "completed": "#198754",  # vert
    "sent": "#198754",
    "delivered": "#198754",
    "paused": "#ffc107",     # jaune
    "failed": "#dc3545",     # rouge
    "error": "#dc3545",
    "cancelled": "#adb5bd",  # gris clair
    "canceled": "#adb5bd",
}

# Statuts pour lesquels le drag & drop (replanification) est autorisé
EDITABLE_STATUSES = {"", "draft", "scheduled", "paused", "queued"}


def _color_for_status(status: Optional[str]) -> str:
    """Retourne la couleur hexadécimale associée à un statut."""
    if not status:
        return STATUS_COLORS["draft"]
    return STATUS_COLORS.get(str(status).lower(), "#0d6efd")


def _event_date(campaign) -> Optional[datetime]:
    """
    Retourne la date à afficher pour une campagne.
    Priorité : scheduled_at → sent_at → created_at.
    """
    for attr in ("scheduled_at", "sent_at", "created_at"):
        value = getattr(campaign, attr, None)
        if value:
            return value
    return None


def _campaign_title(campaign) -> str:
    """Retourne un titre lisible pour une campagne."""
    for attr in ("name", "title", "label"):
        value = getattr(campaign, attr, None)
        if value:
            return str(value)
    return f"Campagne #{getattr(campaign, 'id', '?')}"


def get_campaigns_between(
    business_id: int,
    start: datetime,
    end: datetime,
    statuses: Optional[Iterable[str]] = None,
) -> list:
    """
    Récupère les campagnes d'un business dans une plage de dates.

    La plage s'applique en OR sur scheduled_at / sent_at / created_at.
    """
    query = Campaign.query.filter(Campaign.business_id == business_id)

    date_filters = []
    if hasattr(Campaign, "scheduled_at"):
        date_filters.append(
            and_(
                Campaign.scheduled_at.isnot(None),
                Campaign.scheduled_at >= start,
                Campaign.scheduled_at <= end,
            )
        )
    if hasattr(Campaign, "sent_at"):
        date_filters.append(
            and_(
                Campaign.sent_at.isnot(None),
                Campaign.sent_at >= start,
                Campaign.sent_at <= end,
            )
        )
    if hasattr(Campaign, "created_at"):
        date_filters.append(
            and_(
                Campaign.created_at.isnot(None),
                Campaign.created_at >= start,
                Campaign.created_at <= end,
            )
        )

    if date_filters:
        query = query.filter(or_(*date_filters))

    if statuses:
        statuses_list = [str(s).strip().lower() for s in statuses if str(s).strip()]
        if statuses_list:
            query = query.filter(
                db.func.lower(Campaign.status).in_(statuses_list)
            )

    order_col = getattr(Campaign, "scheduled_at", None) or Campaign.id
    return query.order_by(order_col.asc()).all()


def campaign_to_event(campaign, business_id: int) -> Optional[dict]:
    """
    Convertit une Campaign en dictionnaire d'événement FullCalendar.
    Retourne None si la campagne ne respecte pas l'isolation ou n'a pas de date.
    """
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
            "recipients_count": getattr(campaign, "recipients_count", None)
                                or getattr(campaign, "contacts_count", None),
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
    """Point d'entrée : retourne la liste d'événements pour FullCalendar."""
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
    Met à jour la date planifiée d'une campagne (drag & drop).

    Lève ValueError si :
    - la campagne n'existe pas pour ce business ;
    - son statut n'autorise pas la replanification ;
    - le modèle ne supporte pas scheduled_at.
    """
    campaign = Campaign.query.filter_by(
        id=campaign_id, business_id=business_id
    ).first()

    if campaign is None:
        raise ValueError("Campagne introuvable")

    status_str = str(getattr(campaign, "status", "") or "").lower()
    if status_str not in EDITABLE_STATUSES:
        raise ValueError("Cette campagne ne peut plus être replanifiée")

    if not hasattr(campaign, "scheduled_at"):
        raise ValueError("Le modèle Campaign ne supporte pas la replanification")

    # Normalisation : stockage en UTC naïf (convention SQLAlchemy classique).
    if new_start.tzinfo is not None:
        new_start = new_start.astimezone(timezone.utc).replace(tzinfo=None)

    campaign.scheduled_at = new_start

    if hasattr(campaign, "updated_at"):
        campaign.updated_at = datetime.utcnow()

    db.session.commit()
    return campaign