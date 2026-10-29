"""
LionFlow AI — Routes du calendrier visuel des campagnes.

Expose :
- GET  /calendar/                                 → page HTML
- GET  /calendar/api/events                       → JSON FullCalendar
- POST /calendar/api/events/<id>/reschedule       → replanification (drag & drop)

⚠️ Le préfixe /calendar est appliqué via
    app.register_blueprint(calendar_bp, url_prefix="/calendar")
    dans app/__init__.py — le Blueprint NE DOIT PAS contenir de url_prefix.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from flask import Blueprint, abort, jsonify, render_template, request
from flask_login import login_required

from app.services import calendar_service
from app.utils.decorators import require_business, get_current_business


calendar_bp = Blueprint(
    "calendar",
    __name__,
    template_folder="../templates/calendar",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _current_business_id() -> int:
    """
    Retourne l'ID du business courant via le helper standard du projet.
    Aligné sur app/routes/campaigns.py.
    """
    business = get_current_business()
    if business is None:
        abort(403)
    return int(business.id)


def _parse_datetime(
    value: str | None, default: datetime | None = None
) -> datetime | None:
    """Parse une date ISO 8601 (avec ou sans timezone) en datetime naïf UTC."""
    if not value:
        return default
    try:
        cleaned = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(cleaned)
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone().replace(tzinfo=None)
        return parsed
    except (ValueError, TypeError):
        return default


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@calendar_bp.route("/", methods=["GET"])
@login_required
@require_business
def index():
    """Page principale du calendrier."""
    return render_template("calendar/index.html")


@calendar_bp.route("/api/events", methods=["GET"])
@login_required
@require_business
def api_events():
    """
    Endpoint JSON consommé par FullCalendar.

    Query params :
        start     : ISO datetime (début de plage visible)
        end       : ISO datetime (fin de plage visible)
        statuses  : liste séparée par virgules (ex. "draft,scheduled")
    """
    business_id = _current_business_id()

    now = datetime.utcnow()
    start = _parse_datetime(request.args.get("start"), now - timedelta(days=30))
    end = _parse_datetime(request.args.get("end"), now + timedelta(days=60))

    if end and start and end < start:
        start, end = end, start

    statuses_raw = request.args.get("statuses") or ""
    statuses = [s.strip().lower() for s in statuses_raw.split(",") if s.strip()] or None

    events = calendar_service.get_events(business_id, start, end, statuses)
    return jsonify(events)


@calendar_bp.route(
    "/api/events/<int:campaign_id>/reschedule", methods=["POST"]
)
@login_required
@require_business
def api_reschedule(campaign_id: int):
    """
    Replanifie une campagne (appelé par le drag & drop FullCalendar).

    Payload JSON :
        { "start": "2026-10-15T14:00:00" }

    Le CSRF est vérifié automatiquement par Flask-WTF (CSRFProtect actif
    globalement via csrf.init_app(app)).
    """
    business_id = _current_business_id()

    payload = request.get_json(silent=True) or {}
    new_start = _parse_datetime(payload.get("start"))
    if new_start is None:
        return jsonify({"error": "Date de replanification invalide"}), 400

    try:
        campaign = calendar_service.reschedule_campaign(
            campaign_id=campaign_id,
            business_id=business_id,
            new_start=new_start,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(
        {
            "ok": True,
            "campaign_id": campaign.id,
            "scheduled_at": campaign.scheduled_at.isoformat(),
        }
    )