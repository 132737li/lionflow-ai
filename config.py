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

    # --- Flask ---
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
    APP_NAME = os.getenv("APP_NAME", "LionFlow AI")
    APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:5000")

    # --- Base de données ---
    SQLALCHEMY_DATABASE_URI = os.getenv(
    "DATABASE_URL",
    "sqlite:///lionflow_ai.db",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
    }

    # --- Sessions ---
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False
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
    WTF_CSRF_TIME_LIMIT = None

    # --- Upload ---
    UPLOAD_FOLDER = os.path.join(BASE_DIR, os.getenv("UPLOAD_FOLDER", "app/static/uploads"))
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH_MB", "5")) * 1024 * 1024
    ALLOWED_UPLOAD_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
    ALLOWED_IMPORT_EXTENSIONS = {"csv", "xlsx", "xls"}

    # --- Médias (campagnes WhatsApp) ---
    ALLOWED_MEDIA_IMAGE_EXT = {"jpg", "jpeg", "png", "webp"}
    ALLOWED_MEDIA_DOC_EXT = {"pdf"}
    ALLOWED_MEDIA_VIDEO_EXT = {"mp4", "3gp"}

    MAX_MEDIA_SIZE_MB = int(os.getenv("MAX_MEDIA_SIZE_MB", "16"))   # WhatsApp : 16 Mo
    MAX_MEDIA_SIZE_IMAGE_MB = 5
    MAX_MEDIA_SIZE_VIDEO_MB = 16
    MAX_MEDIA_SIZE_DOC_MB = 100

    MEDIA_UPLOAD_FOLDER = os.path.join(BASE_DIR, "app/static/uploads/media")

    # --- WhatsApp ---
    WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
    WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    WHATSAPP_BUSINESS_ACCOUNT_ID = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID", "")
    WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "lionflow-verify-token")
    WHATSAPP_API_VERSION = os.getenv("WHATSAPP_API_VERSION", "v20.0")
    WHATSAPP_DEV_MODE = os.getenv("WHATSAPP_DEV_MODE", "1") == "1"
    WHATSAPP_APP_SECRET = os.getenv("WHATSAPP_APP_SECRET", "")
    
    # --- Paiement ---
    PAYMENT_PROVIDER = os.getenv("PAYMENT_PROVIDER", "")
    PAYMENT_API_URL = os.getenv("PAYMENT_API_URL", "")
    PAYMENT_API_KEY = os.getenv("PAYMENT_API_KEY", "")
    PAYMENT_WEBHOOK_SECRET = os.getenv("PAYMENT_WEBHOOK_SECRET", "")
    PAYMENT_SUCCESS_URL = os.getenv("PAYMENT_SUCCESS_URL", "")
    STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
    STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
    STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

    # --- Email (Gmail SMTP) ---
    MAIL_SERVER = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.getenv("MAIL_PORT", "587"))
    MAIL_USE_TLS = os.getenv("MAIL_USE_TLS", "1") == "1"
    MAIL_USE_SSL = os.getenv("MAIL_USE_SSL", "0") == "1"
    MAIL_USERNAME = os.getenv("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER", "")
    MAIL_SUPPRESS_SEND = False
    MAIL_DEBUG = False
    MAIL_MAX_EMAILS = None
    MAIL_ASCII_ATTACHMENTS = False
    
    # --- Notifications Push (VAPID) ---
    VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "")
    VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "")
    VAPID_CLAIMS_EMAIL = os.getenv("VAPID_CLAIMS_EMAIL", "mailto:admin@lionflow.ai")


    # --- Scheduler ---
    SCHEDULER_ENABLED = os.getenv("SCHEDULER_ENABLED", "1") == "1"

    # --- Pagination ---
    ITEMS_PER_PAGE = 20
    
    # --- IA (chatbot) ---
    # Limite globale par défaut (si non configurée par entreprise)
    AI_DEFAULT_MAX_REQUESTS_MONTH = int(os.getenv("AI_DEFAULT_MAX_REQUESTS_MONTH", "1000"))
    # Timeout des appels API IA
    AI_REQUEST_TIMEOUT = int(os.getenv("AI_REQUEST_TIMEOUT", "30"))

    # --- Plans d'abonnement ---
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
    MAIL_SUPPRESS_SEND = True


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