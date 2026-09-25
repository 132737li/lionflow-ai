"""
Configuration centrale de LionFlow AI.
Trois profils : Development, Testing, Production.
"""
import os
from datetime import timedelta
from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))


class Config:
    """Configuration commune à tous les environnements."""
    WHATSAPP_APP_SECRET = os.getenv("WHATSAPP_APP_SECRET", "")

    # --- Flask ---
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
    APP_NAME = os.getenv("APP_NAME", "LionFlow AI")
    APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:5000")

    # --- Base de données ---
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "mysql+pymysql://lionflow_user:password@localhost:3306/lionflow_ai",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
    }

    # --- Sessions ---
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False  # True en prod HTTPS
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_DURATION = timedelta(days=14)

    # --- JWT ---
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "jwt-dev-secret")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(
        seconds=int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES", "3600"))
    )
    JWT_TOKEN_LOCATION = ["headers"]
    JWT_HEADER_NAME = "Authorization"
    JWT_HEADER_TYPE = "Bearer"

    # --- CSRF ---
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None  # lié à la session

    # --- Upload ---
    UPLOAD_FOLDER = os.path.join(BASE_DIR, os.getenv("UPLOAD_FOLDER", "app/static/uploads"))
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH_MB", "5")) * 1024 * 1024
    ALLOWED_UPLOAD_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
    ALLOWED_IMPORT_EXTENSIONS = {"csv", "xlsx", "xls"}

    # --- WhatsApp ---
    WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
    WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    WHATSAPP_BUSINESS_ACCOUNT_ID = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID", "")
    WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "lionflow-verify-token")
    WHATSAPP_API_VERSION = os.getenv("WHATSAPP_API_VERSION", "v20.0")
    WHATSAPP_DEV_MODE = os.getenv("WHATSAPP_DEV_MODE", "1") == "1"

    # --- Stripe ---
    STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
    STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
    STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

    # --- Email ---
    MAIL_SERVER = os.getenv("MAIL_SERVER", "localhost")
    MAIL_PORT = int(os.getenv("MAIL_PORT", "1025"))
    MAIL_USE_TLS = os.getenv("MAIL_USE_TLS", "0") == "1"
    MAIL_USERNAME = os.getenv("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER", "noreply@lionflow.ai")

    # --- Scheduler ---
    SCHEDULER_ENABLED = os.getenv("SCHEDULER_ENABLED", "1") == "1"

    # --- Pagination ---
    ITEMS_PER_PAGE = 20

    # --- Plans d'abonnement (limites configurables) ---
    PLANS = {
        "free": {
            "label": "Free",
            "price_eur": 0,
            "max_contacts": 100,
            "max_messages_month": 500,
            "max_whatsapp_accounts": 1,
            "max_campaigns": 5,
            "advanced_stats": False,
        },
        "pro": {
            "label": "Pro",
            "price_eur": 29,
            "max_contacts": 5000,
            "max_messages_month": 25000,
            "max_whatsapp_accounts": 3,
            "max_campaigns": 100,
            "advanced_stats": True,
        },
        "business": {
            "label": "Business",
            "price_eur": 99,
            "max_contacts": 50000,
            "max_messages_month": 250000,
            "max_whatsapp_accounts": 10,
            "max_campaigns": 1000,
            "advanced_stats": True,
        },
    }


class DevelopmentConfig(Config):
    DEBUG = True
    TESTING = False


class TestingConfig(Config):
    TESTING = True
    DEBUG = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {}
    SCHEDULER_ENABLED = False
    JWT_SECRET_KEY = "test-jwt-secret-key-with-minimum-32-bytes-for-hmac-sha256"
    SECRET_KEY = "test-secret-key-with-minimum-32-bytes-for-hmac-sha256"


class ProductionConfig(Config):
    DEBUG = False
    TESTING = False
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True


CONFIG_MAP = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(env: str | None = None):
    env = env or os.getenv("FLASK_ENV", "development")
    return CONFIG_MAP.get(env, DevelopmentConfig)