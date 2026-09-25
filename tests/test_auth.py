"""
Tests du système d'authentification.
"""
import pytest
from app.extensions import db
from app.models.user import User


class TestRegister:
    def test_register_success(self, client, db):
        resp = client.post("/auth/register", data={
            "first_name": "Marie",
            "last_name": "Martin",
            "email": "marie@test.com",
            "password": "Password123",
            "confirm_password": "Password123",
            "accept_terms": "y",
        }, follow_redirects=True)
        assert resp.status_code == 200
        user = User.query.filter_by(email="marie@test.com").first()
        assert user is not None
        assert user.first_name == "Marie"

    def test_register_duplicate_email(self, client, user, db):
        resp = client.post("/auth/register", data={
            "first_name": "Test",
            "last_name": "Dup",
            "email": "user@test.com",
            "password": "Password123",
            "confirm_password": "Password123",
            "accept_terms": "y",
        })
        assert User.query.filter_by(email="user@test.com").count() == 1

    def test_register_weak_password(self, client, db):
        resp = client.post("/auth/register", data={
            "first_name": "Test",
            "last_name": "Dup",
            "email": "new@test.com",
            "password": "abc",
            "confirm_password": "abc",
            "accept_terms": "y",
        })
        assert User.query.filter_by(email="new@test.com").first() is None

    def test_register_mismatched_passwords(self, client, db):
        resp = client.post("/auth/register", data={
            "first_name": "Test",
            "last_name": "Dup",
            "email": "new@test.com",
            "password": "Password123",
            "confirm_password": "Password456",
            "accept_terms": "y",
        })
        assert User.query.filter_by(email="new@test.com").first() is None


class TestLogin:
    def test_login_success(self, client, user, db):
        resp = client.post("/auth/login", data={
            "email": "user@test.com",
            "password": "Password123",
        }, follow_redirects=False)
        assert resp.status_code in (302, 200)

    def test_login_wrong_password(self, client, user, db):
        resp = client.post("/auth/login", data={
            "email": "user@test.com",
            "password": "WrongPassword1",
        }, follow_redirects=True)
        assert resp.status_code == 200

    def test_login_unknown_email(self, client, db):
        resp = client.post("/auth/login", data={
            "email": "unknown@test.com",
            "password": "Password123",
        })
        assert resp.status_code == 200

    def test_login_inactive_user(self, client, db):
        u = User(email="inactive@test.com", is_active=False)
        u.set_password("Password123")
        db.session.add(u)
        db.session.commit()

        resp = client.post("/auth/login", data={
            "email": "inactive@test.com",
            "password": "Password123",
        }, follow_redirects=True)
        assert resp.status_code == 200


class TestLogout:
    def test_logout(self, logged_client, db):
        resp = logged_client.post("/auth/logout", follow_redirects=True)
        assert resp.status_code == 200


class TestPasswordChange:
    def test_change_password_success(self, logged_client, user, db):
        resp = logged_client.post("/auth/change-password", data={
            "current_password": "Password123",
            "new_password": "NewPassword123",
            "confirm_password": "NewPassword123",
        }, follow_redirects=True)
        db.session.refresh(user)
        assert user.check_password("NewPassword123")

    def test_change_password_wrong_current(self, logged_client, user, db):
        logged_client.post("/auth/change-password", data={
            "current_password": "WrongPassword",
            "new_password": "NewPassword123",
            "confirm_password": "NewPassword123",
        })
        db.session.refresh(user)
        assert user.check_password("Password123")


class TestPasswordReset:
    def test_reset_token_flow(self, client, user, db):
        from app.services.auth_service import AuthService
        u, raw = AuthService.create_reset_token("user@test.com")
        assert u is not None and raw is not None

        resp = client.post(f"/auth/reset-password/{raw}", data={
            "password": "NewPass123",
            "confirm_password": "NewPass123",
        }, follow_redirects=True)
        db.session.refresh(user)
        assert user.check_password("NewPass123")

    def test_reset_invalid_token(self, client, db):
        resp = client.post("/auth/reset-password/invalidtoken123", data={
            "password": "NewPass123",
            "confirm_password": "NewPass123",
        }, follow_redirects=True)
        assert resp.status_code == 200