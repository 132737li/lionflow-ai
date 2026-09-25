"""
Fixtures pytest partagées par tous les tests.
Utilise un fichier SQLite temporaire (persistant entre requêtes).
"""
import os
import tempfile
import pytest

from app import create_app
from app.extensions import db as _db
from app.models.user import User
from app.models.business import Business
from app.models.contact import Contact
from app.models.subscription import Subscription
from app.models.whatsapp_account import WhatsAppAccount
from app.models.template import Template
from app.models.campaign import Campaign


@pytest.fixture(scope="session")
def app():
    """Instance Flask de test."""
    os.environ["FLASK_ENV"] = "testing"

    tmpdir = tempfile.mkdtemp(prefix="lionflow_test_")
    db_path = os.path.join(tmpdir, "test.db")

    app = create_app("testing")
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
    app.config["UPLOAD_FOLDER"] = tmpdir
    app.config["SERVER_NAME"] = "localhost"
    app.config["WTF_CSRF_ENABLED"] = False
    app.config["SCHEDULER_ENABLED"] = False

    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()
        try:
            os.unlink(db_path)
        except OSError:
            pass


@pytest.fixture(scope="function")
def db(app):
    """Base de données propre entre chaque test."""
    with app.app_context():
        _db.create_all()
        yield _db
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def client(app):
    """Client de test HTTP."""
    return app.test_client()


@pytest.fixture
def runner(app):
    """Runner CLI Flask."""
    return app.test_cli_runner()


# ==================================================
# FACTORIES
# ==================================================
def _make_user(email="user@test.com", password="Password123", role="user"):
    user = User(
        email=email.lower(),
        first_name="Test",
        last_name="User",
        role=role,
        is_active=True,
        is_verified=True,
    )
    user.set_password(password)
    _db.session.add(user)
    _db.session.commit()
    return user


@pytest.fixture
def user(db):
    return _make_user("user@test.com", "Password123", "user")


@pytest.fixture
def admin_user(db):
    return _make_user("admin@test.com", "Admin1234", "admin")


@pytest.fixture
def other_user(db):
    return _make_user("other@test.com", "Password123", "user")


@pytest.fixture
def business(db, user):
    biz = Business(
        owner_id=user.id,
        name="Test Business",
        email="biz@test.com",
        phone="+33612345678",
        country="BI",
    )
    _db.session.add(biz)
    _db.session.flush()
    sub = Subscription(business_id=biz.id, plan="free", status="active")
    _db.session.add(sub)
    _db.session.commit()
    return biz


@pytest.fixture
def other_business(db, other_user):
    biz = Business(
        owner_id=other_user.id,
        name="Other Business",
    )
    _db.session.add(biz)
    _db.session.flush()
    _db.session.add(Subscription(business_id=biz.id, plan="free", status="active"))
    _db.session.commit()
    return biz


@pytest.fixture
def waba_account(db, business):
    acc = WhatsAppAccount(
        business_id=business.id,
        name="Test WABA",
        phone_number="+33600000000",
        phone_number_id="123456789",
        business_account_id="987654321",
        status="connected",
    )
    acc.set_access_token("fake-token-for-tests")
    _db.session.add(acc)
    _db.session.commit()
    return acc


@pytest.fixture
def contact(db, business):
    c = Contact(
        business_id=business.id,
        first_name="Jean",
        last_name="Dupont",
        phone="+33611111111",
        email="jean@test.com",
        status="active",
    )
    _db.session.add(c)
    _db.session.commit()
    return c


@pytest.fixture
def template(db, business):
    t = Template(
        business_id=business.id,
        name="Bienvenue",
        content="Bonjour {{prenom}}, bienvenue chez {{entreprise}} !",
        category="bienvenue",
        language="fr",
    )
    _db.session.add(t)
    _db.session.commit()
    return t


# ==================================================
# LOGGED CLIENT — CORRIGÉ
# ==================================================
@pytest.fixture
def logged_client(app, user, business):
    """
    Client connecté via un vrai POST /auth/login.
    Garantit que la session Flask-Login est correctement initialisée
    ET que active_business_id est bien défini.
    """
    client = app.test_client()

    # 1. Vrai login via le formulaire
    resp = client.post("/auth/login", data={
        "email": user.email,
        "password": "Password123",
    }, follow_redirects=False)

    # 2. Définir explicitement l'entreprise active dans la session
    with client.session_transaction() as sess:
        sess["active_business_id"] = business.id

    return client

@pytest.fixture
def logged_client(app, user, business):
    """
    Client connecté via un VRAI POST /auth/login.
    L'entreprise active est définie explicitement après le login.
    """
    client = app.test_client()

    # 1. Vrai login
    resp = client.post("/auth/login", data={
        "email": user.email,
        "password": "Password123",
    }, follow_redirects=False)

    # 2. Définir l'entreprise active
    with client.session_transaction() as sess:
        sess["active_business_id"] = business.id

    # 3. Vérifier que ça marche
    assert resp.status_code in (302, 200), f"Login échoué : {resp.status_code}"

    return client


@pytest.fixture
def api_token(app, user):
    """Token JWT pour user."""
    with app.app_context():
        from flask_jwt_extended import create_access_token
        return create_access_token(
            identity=str(user.id),
            additional_claims={"role": user.role},
        )


@pytest.fixture
def api_headers(api_token):
    """Headers JWT prêts à l'emploi."""
    return {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }