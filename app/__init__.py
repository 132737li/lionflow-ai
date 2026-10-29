"""
Application factory de LionFlow AI.
Support ngrok via ProxyFix.
"""
import os
import logging
from logging.handlers import RotatingFileHandler

from flask import Flask, render_template, jsonify, request
from werkzeug.middleware.proxy_fix import ProxyFix
from config import get_config

from app.extensions import (
    db, migrate, login_manager, csrf, bcrypt, jwt, mail,
)


def _safe_register(app: Flask, blueprint, **kwargs) -> None:
    """
    Enregistre un blueprint en ignorant silencieusement les doublons.
    """
    name = kwargs.get("name", blueprint.name)
    if name in app.blueprints:
        app.logger.warning(
            "[blueprints] '%s' deja enregistre - doublon ignore", name
        )
        return
    app.register_blueprint(blueprint, **kwargs)


def create_app(env: str | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object(get_config(env))

    # ✅ ProxyFix : nécessaire pour ngrok et reverse proxies
    app.wsgi_app = ProxyFix(
        app.wsgi_app,
        x_for=1,
        x_proto=1,
        x_host=1,
        x_port=1,
        x_prefix=1,
    )

    # Créer le dossier d'upload si absent
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    # --- Init extensions ---
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    bcrypt.init_app(app)
    jwt.init_app(app)
    mail.init_app(app)

    # --- Init Celery (optionnel) ---
    try:
        from app.celery_app import init_celery
        init_celery(app)
        app.logger.info(
            "[celery] Celery initialise (enabled=%s, broker=%s)",
            app.config.get("CELERY_ENABLED", False),
            app.config.get("CELERY_BROKER_URL", "?"),
        )
    except ImportError:
        app.logger.warning(
            "[celery] Package celery non installe - mode synchrone uniquement."
        )
    except Exception:
        app.logger.exception("[celery] Erreur initialisation Celery")

    # --- Chargement des modèles ---
    from app import models  # noqa: F401

    # --- User loader Flask-Login ---
    from app.models.user import User

    @login_manager.user_loader
    def load_user(user_id: str):
        return db.session.get(User, int(user_id))

    # --- Routes PWA ---
    from flask import send_from_directory

    @app.route("/sw.js")
    def service_worker():
        return send_from_directory(app.static_folder + "/js", "sw.js", mimetype="application/javascript")

    @app.route("/manifest.json")
    def manifest():
        return send_from_directory(app.static_folder, "manifest.json", mimetype="application/manifest+json")

    # --- Handlers d'erreurs JWT ---
    from app.extensions import jwt as _jwt

    @_jwt.unauthorized_loader
    def _jwt_missing(reason):
        return jsonify(success=False, message="Authentification requise.", data=None, errors=[reason]), 401

    @_jwt.invalid_token_loader
    def _jwt_invalid(reason):
        return jsonify(success=False, message="Token invalide.", data=None, errors=[reason]), 401

    @_jwt.expired_token_loader
    def _jwt_expired(jwt_header, jwt_payload):
        return jsonify(success=False, message="Token expire.", data=None, errors=["Token expire."]), 401

    @_jwt.revoked_token_loader
    def _jwt_revoked(jwt_header, jwt_payload):
        return jsonify(success=False, message="Token revoque.", data=None, errors=["Token revoque."]), 401

    # =====================================================================
    # Blueprints UI
    # =====================================================================
    from app.routes.landing import landing_bp
    from app.routes.auth import auth_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.businesses import businesses_bp
    from app.routes.contacts import contacts_bp
    from app.routes.campaigns import campaigns_bp
    from app.routes.messages import messages_bp
    from app.routes.templates import templates_bp
    from app.routes.whatsapp import whatsapp_bp
    from app.routes.telegram import telegram_bp
    from app.routes.subscriptions import subscriptions_bp
    from app.routes.payments import payments_bp
    from app.routes.notifications import notifications_bp
    from app.routes.api_keys import api_keys_bp
    from app.routes.logs import logs_bp
    from app.routes.chatbot import chatbot_bp
    from app.routes.admin import admin_bp
    from app.routes.push import push_bp
    from app.routes.search import search_bp
    from app.routes.two_factor import two_factor_bp
    from app.routes.media import media_bp
    from app.routes.i18n import i18n_bp
    from app.routes.ai import ai_bp
    from app.routes.campaign_templates import campaign_templates_bp
    from app.routes.calendar import calendar_bp
    from app.routes.voice import voice_bp
    from app.routes.whatsapp_voice_webhook import whatsapp_voice_bp
    from app.routes.webhooks import webhooks_bp
    
    _safe_register(app, landing_bp, url_prefix="/")
    _safe_register(app, auth_bp, url_prefix="/auth")
    _safe_register(app, dashboard_bp, url_prefix="/dashboard")
    _safe_register(app, businesses_bp, url_prefix="/businesses")
    _safe_register(app, contacts_bp, url_prefix="/contacts")
    _safe_register(app, campaigns_bp, url_prefix="/campaigns")
    _safe_register(app, messages_bp, url_prefix="/messages")
    _safe_register(app, templates_bp, url_prefix="/templates")
    _safe_register(app, whatsapp_bp, url_prefix="/whatsapp")
    _safe_register(app, telegram_bp, url_prefix="/telegram")
    _safe_register(app, subscriptions_bp, url_prefix="/subscriptions")
    _safe_register(app, payments_bp, url_prefix="/payments")
    _safe_register(app, notifications_bp, url_prefix="/notifications")
    _safe_register(app, api_keys_bp, url_prefix="/api-keys")
    _safe_register(app, logs_bp, url_prefix="/logs")
    _safe_register(app, chatbot_bp, url_prefix="/chatbot")
    _safe_register(app, admin_bp, url_prefix="/admin")
    _safe_register(app, push_bp, url_prefix="/push")
    _safe_register(app, search_bp, url_prefix="/search")
    _safe_register(app, two_factor_bp, url_prefix="/2fa")
    _safe_register(app, media_bp, url_prefix="/media")
    _safe_register(app, i18n_bp, url_prefix="/i18n")
    _safe_register(app, ai_bp, url_prefix="/ai")
    _safe_register(app, campaign_templates_bp, url_prefix="/campaign-templates")
    _safe_register(app, calendar_bp, url_prefix="/calendar")
    _safe_register(app, voice_bp, url_prefix="/voice")
    _safe_register(app, whatsapp_voice_bp)
    _safe_register(app, webhooks_bp, url_prefix="/webhooks")

    # =====================================================================
    # Blueprints API
    # =====================================================================
    from app.api.auth import api_auth_bp
    from app.api.businesses import api_businesses_bp
    from app.api.contacts import api_contacts_bp
    from app.api.campaigns import api_campaigns_bp
    from app.api.messages import api_messages_bp
    from app.api.templates import api_templates_bp
    from app.api.whatsapp_accounts import api_waba_bp
    from app.api.subscriptions import api_subscriptions_bp
    from app.api.payments import api_payments_bp
    from app.api.notifications import api_notifications_bp
    from app.api.api_keys import api_keys_bp as api_api_keys_bp
    from app.api.logs import api_logs_bp

    _safe_register(app, api_auth_bp, url_prefix="/api/auth")
    _safe_register(app, api_businesses_bp, url_prefix="/api/businesses")
    _safe_register(app, api_contacts_bp, url_prefix="/api/contacts")
    _safe_register(app, api_campaigns_bp, url_prefix="/api/campaigns")
    _safe_register(app, api_messages_bp, url_prefix="/api/messages")
    _safe_register(app, api_templates_bp, url_prefix="/api/templates")
    _safe_register(app, api_waba_bp, url_prefix="/api/whatsapp_accounts")
    _safe_register(app, api_subscriptions_bp, url_prefix="/api/subscriptions")
    _safe_register(app, api_payments_bp, url_prefix="/api/payments")
    _safe_register(app, api_notifications_bp, url_prefix="/api/notifications")
    _safe_register(app, api_api_keys_bp, url_prefix="/api/api_keys")
    _safe_register(app, api_logs_bp, url_prefix="/api/logs")

    # =====================================================================
    # CSRF exemptions
    # =====================================================================
    csrf.exempt(api_auth_bp)
    csrf.exempt(api_businesses_bp)
    csrf.exempt(api_contacts_bp)
    csrf.exempt(api_campaigns_bp)
    csrf.exempt(api_messages_bp)
    csrf.exempt(api_templates_bp)
    csrf.exempt(api_waba_bp)
    csrf.exempt(api_subscriptions_bp)
    csrf.exempt(api_payments_bp)
    csrf.exempt(api_notifications_bp)
    csrf.exempt(api_api_keys_bp)
    csrf.exempt(api_logs_bp)
    
    # Exempter le webhook WhatsApp du CSRF (Meta ne fournit pas de token)
    csrf.exempt(whatsapp_voice_bp)
    
    # Exempter le webhook de paiement du CSRF (UltraNer ne fournit pas de token)
    csrf.exempt(payments_bp)

    # =====================================================================
    # Handlers d'erreurs & CLI
    # =====================================================================
    from app.errors import register_error_handlers
    register_error_handlers(app)

    from app.cli import register_cli
    register_cli(app)

    _configure_logging(app)

    # =====================================================================
    # Context Processors
    # =====================================================================
    from app.i18n import t, I18nService, LANGUAGES

    @app.context_processor
    def inject_i18n():
        return {
            "t": t,
            "current_language": I18nService.get_current_language(),
            "available_languages": LANGUAGES,
        }

    @app.context_processor
    def inject_pending_role_requests():
        from flask_login import current_user
        from app.models.role_change_request import RoleChangeRequest
        count = 0
        if current_user.is_authenticated and getattr(current_user, "role", None) == "admin":
            count = RoleChangeRequest.query.filter_by(status="pending").count()
        return {"pending_role_requests_count": count}

    return app


def _configure_logging(app: Flask) -> None:
    """Log dans un fichier rotatif + console."""
    if app.config.get("TESTING"):
        return
    log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
    os.makedirs(log_dir, exist_ok=True)

    handler = RotatingFileHandler(
        os.path.join(log_dir, "lionflow.log"),
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(
        "[%(asctime)s] %(levelname)s in %(module)s: %(message)s"
    ))
    handler.setLevel(logging.INFO)
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)