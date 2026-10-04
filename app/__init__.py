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

    # --- Chargement des modèles (indispensable pour Alembic) ---
    from app import models  # noqa: F401

    # --- User loader Flask-Login ---
    from app.models.user import User

    @login_manager.user_loader
    def load_user(user_id: str):
        return db.session.get(User, int(user_id))
    
    # --- Routes pour la PWA (Service Worker + Manifest) ---
    from flask import send_from_directory

    @app.route("/sw.js")
    def service_worker():
        return send_from_directory(
             app.static_folder + "/js",
             "sw.js",
           mimetype="application/javascript",
        )

    @app.route("/manifest.json")
    def manifest():
        return send_from_directory(
             app.static_folder,
             "manifest.json",
            mimetype="application/manifest+json",
        )
    

    # --- Handlers d'erreurs JWT ---
    from app.extensions import jwt as _jwt

    @_jwt.unauthorized_loader
    def _jwt_missing(reason):
        return jsonify(success=False, message="Authentification requise.",
                       data=None, errors=[reason]), 401

    @_jwt.invalid_token_loader
    def _jwt_invalid(reason):
        return jsonify(success=False, message="Token invalide.",
                       data=None, errors=[reason]), 401

    @_jwt.expired_token_loader
    def _jwt_expired(jwt_header, jwt_payload):
        return jsonify(success=False, message="Token expiré.",
                       data=None, errors=["Token expiré."]), 401

    @_jwt.revoked_token_loader
    def _jwt_revoked(jwt_header, jwt_payload):
        return jsonify(success=False, message="Token révoqué.",
                       data=None, errors=["Token révoqué."]), 401

    # --- Blueprints UI ---
    from app.routes.auth import auth_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.businesses import businesses_bp
    from app.routes.contacts import contacts_bp
    from app.routes.campaigns import campaigns_bp
    from app.routes.messages import messages_bp
    from app.routes.templates import templates_bp
    from app.routes.whatsapp import whatsapp_bp
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

    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(dashboard_bp, url_prefix="/")
    app.register_blueprint(businesses_bp, url_prefix="/businesses")
    app.register_blueprint(contacts_bp, url_prefix="/contacts")
    app.register_blueprint(campaigns_bp, url_prefix="/campaigns")
    app.register_blueprint(messages_bp, url_prefix="/messages")
    app.register_blueprint(templates_bp, url_prefix="/templates")
    app.register_blueprint(whatsapp_bp, url_prefix="/whatsapp")
    app.register_blueprint(subscriptions_bp, url_prefix="/subscriptions")
    app.register_blueprint(payments_bp, url_prefix="/payments")
    app.register_blueprint(notifications_bp, url_prefix="/notifications")
    app.register_blueprint(api_keys_bp, url_prefix="/api-keys")
    app.register_blueprint(logs_bp, url_prefix="/logs")
    app.register_blueprint(chatbot_bp, url_prefix="/chatbot")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(push_bp, url_prefix="/push")
    app.register_blueprint(search_bp, url_prefix="/search")
    app.register_blueprint(two_factor_bp, url_prefix="/2fa")
    app.register_blueprint(media_bp, url_prefix="/media")
    app.register_blueprint(i18n_bp, url_prefix="/i18n")
    app.register_blueprint(ai_bp, url_prefix="/ai")
    app.register_blueprint(campaign_templates_bp)
    
    # --- Blueprints API ---
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

    app.register_blueprint(api_auth_bp, url_prefix="/api/auth")
    app.register_blueprint(api_businesses_bp, url_prefix="/api/businesses")
    app.register_blueprint(api_contacts_bp, url_prefix="/api/contacts")
    app.register_blueprint(api_campaigns_bp, url_prefix="/api/campaigns")
    app.register_blueprint(api_messages_bp, url_prefix="/api/messages")
    app.register_blueprint(api_templates_bp, url_prefix="/api/templates")
    app.register_blueprint(api_waba_bp, url_prefix="/api/whatsapp_accounts")
    app.register_blueprint(api_subscriptions_bp, url_prefix="/api/subscriptions")
    app.register_blueprint(api_payments_bp, url_prefix="/api/payments")
    app.register_blueprint(api_notifications_bp, url_prefix="/api/notifications")
    app.register_blueprint(api_api_keys_bp, url_prefix="/api/api_keys")
    app.register_blueprint(api_logs_bp, url_prefix="/api/logs")

    # Exempter tous les endpoints /api du CSRF
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

    # --- Handlers d'erreurs ---
    from app.errors import register_error_handlers
    register_error_handlers(app)

    # --- CLI ---
    from app.cli import register_cli
    register_cli(app)

    # --- Logging ---
    _configure_logging(app)
    
    # --- Context processor i18n ---
    from app.i18n import t, I18nService, LANGUAGES

    @app.context_processor
    def inject_i18n():
        return {
            "t": t,
            "current_language": I18nService.get_current_language(),
            "available_languages": LANGUAGES,
        }
    

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
    )
    handler.setFormatter(logging.Formatter(
        "[%(asctime)s] %(levelname)s in %(module)s: %(message)s"
    ))
    handler.setLevel(logging.INFO)
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)