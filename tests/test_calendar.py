"""
Tests du calendrier des campagnes LionFlow AI.

Utilise les fixtures réelles définies dans tests/conftest.py :
- client          : test_client non authentifié
- logged_client   : client authentifié + active_business_id en session
- business        : entreprise de test liée à user
- other_business  : entreprise d'un autre user (pour tester l'isolation)
- db              : session SQLAlchemy de test
"""

from datetime import datetime, timedelta

import pytest

from app.models.campaign import Campaign


# ---------------------------------------------------------------------------
# Fabrique de campagnes locale
# ---------------------------------------------------------------------------
@pytest.fixture
def make_campaign(db, business):
    def _make(**overrides):
        now = datetime.utcnow()
        defaults = {
            "business_id": business.id,
            "name": "Campagne test",
            "status": "scheduled",
            "scheduled_at": now + timedelta(days=1),
            "total_contacts": 10,
        }
        defaults.update(overrides)
        campaign = Campaign(**defaults)
        db.session.add(campaign)
        db.session.commit()
        return campaign

    return _make


def _range_params(days_back: int = 7, days_forward: int = 30) -> str:
    start = (datetime.utcnow() - timedelta(days=days_back)).isoformat()
    end = (datetime.utcnow() + timedelta(days=days_forward)).isoformat()
    return f"start={start}&end={end}"


# ---------------------------------------------------------------------------
# Accès et permissions
# ---------------------------------------------------------------------------
def test_calendar_requires_login(client):
    """Un utilisateur non connecté est redirigé vers /auth/login."""
    response = client.get("/calendar/")
    assert response.status_code == 302
    assert "/auth/login" in response.headers.get("Location", "")


def test_api_events_requires_login(client):
    response = client.get("/calendar/api/events")
    assert response.status_code == 302


def test_calendar_page_renders(logged_client):
    """La page du calendrier se charge pour un utilisateur connecté."""
    response = logged_client.get("/calendar/")
    assert response.status_code == 200
    assert b"campaignCalendar" in response.data


# ---------------------------------------------------------------------------
# API events — Cas nominal + filtres
# ---------------------------------------------------------------------------
def test_api_events_returns_json(logged_client, make_campaign):
    make_campaign(name="Ma campagne A")

    response = logged_client.get(f"/calendar/api/events?{_range_params()}")
    assert response.status_code == 200

    data = response.get_json()
    assert isinstance(data, list)
    titles = [ev["title"] for ev in data]
    assert "Ma campagne A" in titles


def test_api_events_isolated_by_business(
    logged_client, make_campaign, db, business, other_business
):
    """Une campagne d'un autre business ne doit pas apparaître."""
    make_campaign(name="Visible", business_id=business.id)
    make_campaign(name="Invisible", business_id=other_business.id)

    response = logged_client.get(f"/calendar/api/events?{_range_params()}")
    data = response.get_json()
    titles = [ev["title"] for ev in data]

    assert "Visible" in titles
    assert "Invisible" not in titles


def test_api_events_filter_by_status(logged_client, make_campaign):
    make_campaign(name="Brouillon", status="draft")
    make_campaign(name="Planifiee", status="scheduled")

    response = logged_client.get(
        f"/calendar/api/events?{_range_params()}&statuses=draft"
    )
    data = response.get_json()
    titles = [ev["title"] for ev in data]

    assert "Brouillon" in titles
    assert "Planifiee" not in titles


def test_api_events_filter_multiple_statuses(logged_client, make_campaign):
    make_campaign(name="A", status="draft")
    make_campaign(name="B", status="scheduled")
    make_campaign(name="C", status="completed")

    response = logged_client.get(
        f"/calendar/api/events?{_range_params()}&statuses=draft,scheduled"
    )
    data = response.get_json()
    titles = [ev["title"] for ev in data]

    assert "A" in titles
    assert "B" in titles
    assert "C" not in titles


def test_api_events_empty_range(logged_client, make_campaign):
    """Une plage lointaine ne retourne rien."""
    make_campaign(
        name="Campagne lointaine",
        scheduled_at=datetime.utcnow() + timedelta(days=365),
    )
    start = (datetime.utcnow() + timedelta(days=100)).isoformat()
    end = (datetime.utcnow() + timedelta(days=200)).isoformat()

    response = logged_client.get(
        f"/calendar/api/events?start={start}&end={end}"
    )
    assert response.status_code == 200
    assert response.get_json() == []


# ---------------------------------------------------------------------------
# Replanification
# ---------------------------------------------------------------------------
def test_reschedule_draft_campaign(logged_client, make_campaign):
    campaign = make_campaign(status="draft")
    new_date = (datetime.utcnow() + timedelta(days=10)).isoformat()

    response = logged_client.post(
        f"/calendar/api/events/{campaign.id}/reschedule",
        json={"start": new_date},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["campaign_id"] == campaign.id


def test_reschedule_completed_forbidden(logged_client, make_campaign):
    campaign = make_campaign(status="completed")
    new_date = (datetime.utcnow() + timedelta(days=10)).isoformat()

    response = logged_client.post(
        f"/calendar/api/events/{campaign.id}/reschedule",
        json={"start": new_date},
    )
    assert response.status_code == 400
    assert "replanifiée" in response.get_json()["error"].lower()


def test_reschedule_running_forbidden(logged_client, make_campaign):
    campaign = make_campaign(status="running")
    new_date = (datetime.utcnow() + timedelta(days=10)).isoformat()

    response = logged_client.post(
        f"/calendar/api/events/{campaign.id}/reschedule",
        json={"start": new_date},
    )
    assert response.status_code == 400


def test_reschedule_cross_tenant_forbidden(
    logged_client, make_campaign, other_business
):
    """Impossible de replanifier une campagne d'un autre business."""
    foreign = make_campaign(status="draft", business_id=other_business.id)
    new_date = (datetime.utcnow() + timedelta(days=10)).isoformat()

    response = logged_client.post(
        f"/calendar/api/events/{foreign.id}/reschedule",
        json={"start": new_date},
    )
    assert response.status_code == 400
    assert "introuvable" in response.get_json()["error"].lower()


def test_reschedule_rejects_invalid_date(logged_client, make_campaign):
    campaign = make_campaign(status="draft")

    response = logged_client.post(
        f"/calendar/api/events/{campaign.id}/reschedule",
        json={"start": "pas-une-date"},
    )
    assert response.status_code == 400
    assert "invalide" in response.get_json()["error"].lower()


def test_reschedule_persists_new_date(logged_client, make_campaign, db):
    campaign = make_campaign(status="scheduled")
    new_date = datetime.utcnow() + timedelta(days=15)
    new_date_iso = new_date.replace(microsecond=0).isoformat()

    response = logged_client.post(
        f"/calendar/api/events/{campaign.id}/reschedule",
        json={"start": new_date_iso},
    )
    assert response.status_code == 200

    db.session.expire_all()
    refreshed = db.session.get(Campaign, campaign.id)
    # Comparaison tolérante (arrondi seconde)
    assert refreshed.scheduled_at is not None
    assert abs((refreshed.scheduled_at - new_date).total_seconds()) < 2