"""
Tests de l'API REST — JWT, format, pagination.
"""
import pytest
import json
from app.models.contact import Contact


class TestAPIAuth:
    def test_register(self, client, db):
        resp = client.post("/api/auth/register", json={
            "email": "api@test.com",
            "password": "Password123",
            "first_name": "Api",
            "last_name": "User",
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["success"] is True
        assert data["data"]["email"] == "api@test.com"

    def test_register_missing_fields(self, client):
        resp = client.post("/api/auth/register", json={"email": "x@x.com"})
        assert resp.status_code == 422
        data = resp.get_json()
        assert data["success"] is False
        assert len(data["errors"]) > 0

    def test_login_success(self, client, user):
        resp = client.post("/api/auth/login", json={
            "email": "user@test.com",
            "password": "Password123",
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "access_token" in data["data"]

    def test_login_wrong_password(self, client, user):
        resp = client.post("/api/auth/login", json={
            "email": "user@test.com",
            "password": "Wrong123",
        })
        assert resp.status_code == 401
        data = resp.get_json()
        assert data["success"] is False

    def test_me_requires_jwt(self, client):
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401

    def test_me_with_jwt(self, client, api_headers, user):
        resp = client.get("/api/auth/me", headers=api_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["data"]["email"] == "user@test.com"


class TestAPIContacts:
    def test_create_contact(self, client, api_headers, business, db):
        resp = client.post("/api/contacts", headers=api_headers, json={
            "first_name": "Api",
            "last_name": "Contact",
            "phone": "+33655555555",
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["success"] is True
        assert data["data"]["phone"] == "+33655555555"

    def test_list_contacts_paginated(self, client, api_headers, business, db):
        # Créer 5 contacts
        for i in range(5):
            c = Contact(
                business_id=business.id,
                first_name=f"Contact{i}",
                phone=f"+336666666{i:02d}",
            )
            db.session.add(c)
        db.session.commit()

        resp = client.get("/api/contacts?page=1&per_page=2", headers=api_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert len(data["data"]["items"]) == 2
        assert data["data"]["meta"]["total"] == 5
        assert data["data"]["meta"]["pages"] == 3

    def test_get_contact(self, client, api_headers, business, contact):
        resp = client.get(f"/api/contacts/{contact.id}", headers=api_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["data"]["first_name"] == "Jean"

    def test_update_contact(self, client, api_headers, business, contact, db):
        resp = client.put(f"/api/contacts/{contact.id}", headers=api_headers, json={
            "first_name": "Jean-API",
        })
        assert resp.status_code == 200
        db.session.refresh(contact)
        assert contact.first_name == "Jean-API"

    def test_delete_contact(self, client, api_headers, business, contact, db):
        cid = contact.id
        resp = client.delete(f"/api/contacts/{cid}", headers=api_headers)
        assert resp.status_code == 200
        assert db.session.get(Contact, cid) is None

    def test_create_contact_no_jwt(self, client, business):
        resp = client.post("/api/contacts", json={"phone": "+33600000000"})
        assert resp.status_code == 401

    def test_duplicate_phone_returns_409(self, client, api_headers, business, contact):
        resp = client.post("/api/contacts", headers=api_headers, json={
            "phone": contact.phone,
        })
        assert resp.status_code == 409

    def test_invalid_phone_returns_422(self, client, api_headers, business):
        resp = client.post("/api/contacts", headers=api_headers, json={
            "phone": "not-a-phone",
        })
        assert resp.status_code == 422


class TestAPICampaigns:
    def test_create_campaign(self, client, api_headers, business,
                              waba_account, template, contact, db):
        resp = client.post("/api/campaigns", headers=api_headers, json={
            "name": "API Camp",
            "template_id": template.id,
            "whatsapp_account_id": waba_account.id,
            "contact_ids": [contact.id],
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["data"]["name"] == "API Camp"

    def test_start_campaign(self, client, api_headers, business,
                             waba_account, template, contact, db):
        from app.models.campaign import Campaign, campaign_contacts
        c = Campaign(
            business_id=business.id,
            template_id=template.id,
            whatsapp_account_id=waba_account.id,
            name="Start API",
            status="draft",
            total_contacts=1,
        )
        db.session.add(c)
        db.session.flush()
        db.session.execute(
            campaign_contacts.insert().values(campaign_id=c.id, contact_id=contact.id)
        )
        db.session.commit()

        resp = client.post(f"/api/campaigns/{c.id}/start", headers=api_headers)
        assert resp.status_code == 200


class TestAPIResponseFormat:
    def test_success_format(self, client, api_headers, business, contact):
        resp = client.get("/api/contacts", headers=api_headers)
        data = resp.get_json()
        assert "success" in data
        assert "message" in data
        assert "data" in data
        assert "errors" in data
        assert isinstance(data["errors"], list)

    def test_error_format(self, client, api_headers, business):
        resp = client.get("/api/contacts/999999", headers=api_headers)
        assert resp.status_code == 404
        data = resp.get_json()
        assert data["success"] is False
        assert data["data"] is None

    def test_unauthorized_format(self, client):
        resp = client.get("/api/contacts")
        assert resp.status_code == 401
        data = resp.get_json()
        assert data["success"] is False


class TestAPITemplates:
    def test_create_template(self, client, api_headers, business):
        resp = client.post("/api/templates", headers=api_headers, json={
            "name": "API Template",
            "content": "Bonjour {{prenom}} !",
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["data"]["name"] == "API Template"

    def test_list_templates(self, client, api_headers, business, template):
        resp = client.get("/api/templates", headers=api_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["data"]["meta"]["total"] == 1