"""
Routes pour les notifications push PWA.
"""
from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user

from app.services.push_service import PushService
from app.utils.security import log_activity


push_bp = Blueprint("push", __name__, url_prefix="/push")


@push_bp.route("/vapid-public-key")
@login_required
def vapid_public_key():
    """Retourne la clé publique VAPID au client."""
    key = current_app.config.get("VAPID_PUBLIC_KEY", "")
    return jsonify(success=True, public_key=key)


@push_bp.route("/subscribe", methods=["POST"])
@login_required
def subscribe():
    """Enregistre un abonnement push pour l'utilisateur connecté."""
    data = request.get_json(silent=True) or {}
    if not data.get("endpoint"):
        return jsonify(success=False, message="Endpoint manquant"), 400

    try:
        sub = PushService.subscribe(
            user_id=current_user.id,
            subscription_data=data,
            user_agent=request.headers.get("User-Agent", ""),
        )
        log_activity(
            action="push_subscribe",
            description=f"Nouvel abonnement push ({sub.user_agent or 'inconnu'})",
        )
        return jsonify(success=True, message="Abonnement enregistré.")
    except Exception as e:
        current_app.logger.exception("[Push] Erreur subscribe")
        return jsonify(success=False, message=str(e)), 400


@push_bp.route("/unsubscribe", methods=["POST"])
@login_required
def unsubscribe():
    """Désabonne un appareil."""
    data = request.get_json(silent=True) or {}
    endpoint = data.get("endpoint")
    if not endpoint:
        return jsonify(success=False, message="Endpoint manquant"), 400

    PushService.unsubscribe(current_user.id, endpoint)
    return jsonify(success=True, message="Désabonné.")


@push_bp.route("/test", methods=["POST"])
@login_required
def test_notification():
    """Envoie une notification de test."""
    count = PushService.send_to_user(
        user_id=current_user.id,
        title="🦁 Test LionFlow AI",
        body="Les notifications fonctionnent parfaitement !",
        url="/",
    )
    return jsonify(
        success=count > 0,
        message=f"{count} notification(s) envoyée(s).",
    )