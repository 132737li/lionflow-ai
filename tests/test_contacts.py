"""
Tests CRUD contacts + isolation multi-tenant.
"""
import pytest
from app.models.contact import Contact


class TestContactCRUD:
    
    def test_create_contact(self, logged_client, business, db):
        resp = logged_client.post("/contacts/new", data={
            "first_name": "Alice",
            "last_name": "Durand",
            "country_code": "FR",
            "phone": "+33622222222",
            "email": "alice@test.com",
            "status": "active",
        }, follow_redirects=True)
        assert resp.status_code == 200
        c = Contact.query.filter_by(phone="+33622222222").first()
        assert c is not None
        assert c.first_name == "Alice"
         
    def test_login_works_in_tests(self, logged_client):
            """Vérifie que le client de test est bien authentifié."""
            resp = logged_client.get("/contacts/", follow_redirects=False)
            assert resp.status_code == 200, f"Redirigé vers {resp.headers.get('Location')}"

    def test_create_invalid_phone(self, logged_client, business, db):
        resp = logged_client.post("/contacts/new", data={
            "first_name": "Bob",
            "country_code": "FR",
            "phone": "abc123",
            "status": "active",
        }, follow_redirects=True)
        assert Contact.query.filter_by(first_name="Bob").first() is None

    def test_create_duplicate_phone(self, logged_client, business, contact, db):
        count_before = Contact.query.count()
        logged_client.post("/contacts/new", data={
            "first_name": "Duplicate",
            "country_code": "FR",
            "phone": contact.phone,
            "status": "active",
        }, follow_redirects=True)
        assert Contact.query.count() == count_before

    def test_edit_contact(self, logged_client, business, contact, db):
        logged_client.post(f"/contacts/{contact.id}/edit", data={
            "first_name": "Jean-Édité",
            "last_name": "Dupont",
            "country_code": "FR",
            "phone": contact.phone,
            "status": "active",
        }, follow_redirects=True)
        db.session.refresh(contact)
        assert contact.first_name == "Jean-Édité"

    def test_delete_contact(self, logged_client, business, contact, db):
        cid = contact.id
        logged_client.post(f"/contacts/{cid}/delete", follow_redirects=True)
        assert db.session.get(Contact, cid) is None

    def test_list_contacts(self, logged_client, business, contact):
        resp = logged_client.get("/contacts/")
        assert resp.status_code == 200
        assert contact.first_name.encode() in resp.data


class TestContactFilters:
    def test_search_by_name(self, logged_client, business, contact):
        resp = logged_client.get("/contacts/?q=Jean")
        assert resp.status_code == 200
        assert b"Jean" in resp.data

    def test_filter_by_status(self, logged_client, business, contact):
        resp = logged_client.get("/contacts/?status=active")
        assert resp.status_code == 200

    def test_no_results(self, logged_client, business):
        resp = logged_client.get("/contacts/?q=zzznonexistent")
        assert resp.status_code == 200


class TestMultiTenantIsolation:
    def test_user_cannot_see_other_business_contact(
        self, logged_client, business, other_business, db
    ):
        c = Contact(
            business_id=other_business.id,
            first_name="Secret",
            phone="+33699999999",
        )
        db.session.add(c)
        db.session.commit()

        resp = logged_client.get("/contacts/")
        assert b"Secret" not in resp.data

    def test_user_cannot_edit_other_business_contact(
        self, logged_client, business, other_business, db
    ):
        c = Contact(
            business_id=other_business.id,
            first_name="Other",
            phone="+33688888888",
        )
        db.session.add(c)
        db.session.commit()

        resp = logged_client.get(f"/contacts/{c.id}/edit")
        assert resp.status_code == 404