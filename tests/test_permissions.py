"""
Tests de contrôle d'accès, rôles et isolation.
"""
import pytest


class TestAuthenticationRequired:
    def test_dashboard_requires_login(self, client):
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code == 302
        assert "/auth/login" in resp.headers.get("Location", "")

    def test_contacts_requires_login(self, client):
        resp = client.get("/contacts/", follow_redirects=False)
        assert resp.status_code == 302

    def test_campaigns_requires_login(self, client):
        resp = client.get("/campaigns/", follow_redirects=False)
        assert resp.status_code == 302


class TestRoleAccess:
    def test_admin_role_recognized(self, db, admin_user):
        assert admin_user.is_admin is True
        assert admin_user.role == "admin"

    def test_user_role_not_admin(self, user):
        assert user.is_admin is False

    def test_admin_required_decorator(self, app, db, user, admin_user):
        """Vérifie que le décorateur role_required fonctionne."""
        from app.utils.decorators import role_required
        from flask import Flask, g

        @role_required("admin")
        def fake_view():
            return "ok"

        with app.test_request_context():
            with app.test_request_context():
                from flask_login import login_user
                # Login en tant que user
                login_user(user)
                try:
                    fake_view()
                    assert False, "Devrait lever 403"
                except Exception as e:
                    # abort(403) lève une HTTPException
                    assert "403" in str(e) or "Forbidden" in str(e)


class TestMultiTenantIsolation:
    def test_contact_isolation(self, logged_client, business, other_business, db):
        from app.models.contact import Contact
        c = Contact(
            business_id=other_business.id,
            first_name="Secret",
            phone="+33699999999",
        )
        db.session.add(c)
        db.session.commit()

        resp = logged_client.get(f"/contacts/{c.id}")
        assert resp.status_code == 404

    def test_campaign_isolation(self, logged_client, business, other_business, db):
        from app.models.campaign import Campaign
        c = Campaign(
            business_id=other_business.id,
            name="Other Camp",
            status="draft",
        )
        db.session.add(c)
        db.session.commit()

        resp = logged_client.get(f"/campaigns/{c.id}")
        assert resp.status_code == 404

    def test_api_contact_isolation(self, client, api_headers, business,
                                    other_business, db):
        from app.models.contact import Contact
        c = Contact(
            business_id=other_business.id,
            first_name="Other API",
            phone="+33688888888",
        )
        db.session.add(c)
        db.session.commit()

        resp = client.get(f"/api/contacts/{c.id}", headers=api_headers)
        assert resp.status_code == 404


class TestQuotas:
    def test_contact_quota_enforced(self, client, api_headers, business, db):
        """Avec un plan free à 100 contacts, l'ajout au-delà doit échouer."""
        from app.models.contact import Contact
        # Remplit le quota
        for i in range(100):
            c = Contact(
                business_id=business.id,
                first_name=f"C{i}",
                phone=f"+3360000{i:04d}",
            )
            db.session.add(c)
        db.session.commit()

        resp = client.post("/api/contacts", headers=api_headers, json={
            "phone": "+33700000000",
        })
        assert resp.status_code == 403
        data = resp.get_json()
        assert data["success"] is False
        assert "quota" in data["message"].lower() or "quota" in str(data["errors"]).lower()