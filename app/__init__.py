"""
Application factory de LionFlow AI.
"""
import os
import logging
from logging.handlers import RotatingFileHandler

from flask import Flask, render_template, jsonify, request
from config import get_config

from app.extensions import (
    db, migrate, login_manager, csrf, bcrypt, jwt,
)


def create_app(env: str | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object(get_config(env))

    # Créer le dossier d'upload si absent
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    # --- Init extensions ---
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    bcrypt.init_app(app)
    jwt.init_app(app)

    # --- Chargement des modèles (indispensable pour Alembic) ---
    from app import models  # noqa: F401

    # --- User loader Flask-Login ---
    from app.models.user import User

    @login_manager.user_loader
    def load_user(user_id: str):
        return db.session.get(User, int(user_id))

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

    app.register_blueprint(api_keys_bp, url_prefix="/api-keys")
    app.register_blueprint(logs_bp, url_prefix="/logs")
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
    from app.api.api_api_keys import api_keys_bp
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
    app.register_blueprint(api_keys_bp, url_prefix="/api/api_keys")
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
    csrf.exempt(api_keys_bp)
    csrf.exempt(api_logs_bp)

    # --- Handlers d'erreurs ---
    from app.errors import register_error_handlers
    register_error_handlers(app)
    
    # --- Handlers d'erreurs JWT ---
    from app.extensions import jwt as _jwt

    @_jwt.unauthorized_loader
    def _jwt_missing(reason):
        from flask import jsonify
        return jsonify(success=False, message="Authentification requise.",
                    data=None, errors=[reason]), 401

    @_jwt.invalid_token_loader
    def _jwt_invalid(reason):
        from flask import jsonify
        return jsonify(success=False, message="Token invalide.",
                    data=None, errors=[reason]), 401

    @_jwt.expired_token_loader
    def _jwt_expired(jwt_header, jwt_payload):
        from flask import jsonify
        return jsonify(success=False, message="Token expiré.",
                    data=None, errors=["Token expiré."]), 401

    @_jwt.revoked_token_loader
    def _jwt_revoked(jwt_header, jwt_payload):
        from flask import jsonify
        return jsonify(success=False, message="Token révoqué.",
                    data=None, errors=["Token révoqué."]), 401

    # --- CLI ---
    from app.cli import register_cli
    register_cli(app)

    # --- Logging ---
    _configure_logging(app)

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