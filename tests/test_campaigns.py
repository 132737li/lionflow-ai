"""
Tests CRUD campagnes + transitions de statut + génération messages.
"""
import pytest
from datetime import datetime, timedelta, timezone
from app.models.campaign import Campaign, campaign_contacts
from app.models.message import Message


class TestCampaignCRUD:
    def test_create_campaign_draft(self, logged_client, business, waba_account,
                                    contact, template, db):
        resp = logged_client.post("/campaigns/new", data={
            "name": "Test Promo",
            "template_id": template.id,
            "whatsapp_account_id": waba_account.id,
            "message": "",
            "timezone": "UTC",
            "contact_ids": [contact.id],
        }, follow_redirects=True)
        assert resp.status_code == 200
        c = Campaign.query.filter_by(name="Test Promo").first()
        assert c is not None
        assert c.status == "draft"
        assert c.total_contacts == 1

    def test_create_campaign_scheduled(self, logged_client, business,
                                       waba_account, contact, template):
        future = (datetime.now(timezone.utc) + timedelta(hours=1)).strftime(
            "%Y-%m-%dT%H:%M"
        )
        logged_client.post("/campaigns/new", data={
            "name": "Scheduled Camp",
            "template_id": template.id,
            "whatsapp_account_id": waba_account.id,
            "scheduled_at": future,
            "timezone": "UTC",
            "contact_ids": [contact.id],
        }, follow_redirects=True)
        c = Campaign.query.filter_by(name="Scheduled Camp").first()
        assert c is not None
        assert c.status == "scheduled"

    def test_campaign_requires_waba(self, logged_client, business,
                                     contact, template):
        resp = logged_client.post("/campaigns/new", data={
            "name": "No WABA",
            "template_id": template.id,
            "whatsapp_account_id": 0,
            "contact_ids": [contact.id],
        }, follow_redirects=True)
        assert Campaign.query.filter_by(name="No WABA").first() is None


class TestCampaignActions:
    def test_start_campaign_generates_messages(self, logged_client, business,
                                                waba_account, contact, template, db):
        c = Campaign(
            business_id=business.id,
            template_id=template.id,
            whatsapp_account_id=waba_account.id,
            name="Auto Start",
            status="draft",
            total_contacts=1,
        )
        db.session.add(c)
        db.session.flush()
        db.session.execute(
            campaign_contacts.insert().values(
                campaign_id=c.id, contact_id=contact.id
            )
        )
        db.session.commit()

        resp = logged_client.post(f"/campaigns/{c.id}/start", follow_redirects=True)
        assert resp.status_code == 200

        db.session.refresh(c)
        assert c.status in ("completed", "running")

        messages = Message.query.filter_by(campaign_id=c.id).all()
        assert len(messages) == 1
        assert "Jean" in messages[0].content

    def test_pause_running_campaign(self, logged_client, business, waba_account, db):
        c = Campaign(
            business_id=business.id,
            whatsapp_account_id=waba_account.id,
            name="Running Camp",
            status="running",
        )
        db.session.add(c)
        db.session.commit()

        logged_client.post(f"/campaigns/{c.id}/pause", follow_redirects=True)
        db.session.refresh(c)
        assert c.status == "paused"

    def test_cannot_delete_running_campaign(self, logged_client, business, db):
        c = Campaign(
            business_id=business.id,
            name="Running To Delete",
            status="running",
        )
        db.session.add(c)
        db.session.commit()
        cid = c.id

        logged_client.post(f"/campaigns/{cid}/delete", follow_redirects=True)
        assert db.session.get(Campaign, cid) is not None


class TestCampaignIsolation:
    def test_campaign_of_other_user_invisible(self, logged_client, business,
                                               other_business, db):
        c = Campaign(
            business_id=other_business.id,
            name="Secret Camp",
            status="draft",
        )
        db.session.add(c)
        db.session.commit()

        resp = logged_client.get(f"/campaigns/{c.id}")
        assert resp.status_code == 404