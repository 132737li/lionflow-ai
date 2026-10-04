import os
import sys

from app import create_app
from app.extensions import db
from app.models.user import User


def main():
    email = (os.getenv("ADMIN_EMAIL") or "").strip().lower()
    password = os.getenv("ADMIN_PASSWORD") or ""

    if not email or not password:
        print("ADMIN_EMAIL ou ADMIN_PASSWORD non configuré.")
        print("Aucun compte admin automatique ne sera créé.")
        return 0

    if len(password) < 8:
        print("ADMIN_PASSWORD doit contenir au moins 8 caractères.")
        return 1

    app = create_app("production")

    with app.app_context():
        user = User.query.filter_by(email=email).first()

        if user:
            user.role = "admin"
            user.is_active = True
            db.session.commit()

            print(f"Compte administrateur confirmé : {email}")
            return 0

        user = User(
            email=email,
            first_name="Léon",
            last_name="Corazón",
            role="admin",
            is_active=True,
            is_verified=True,
        )

        user.set_password(password)

        db.session.add(user)
        db.session.commit()

        print(f"Compte administrateur créé : {email}")
        return 0


if __name__ == "__main__":
    sys.exit(main())