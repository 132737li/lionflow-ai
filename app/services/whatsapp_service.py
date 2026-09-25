"""
Service d'envoi WhatsApp Cloud API (Meta).

En mode DEBUG (WHATSAPP_DEV_MODE=1) : aucune API réelle n'est appelée.
En production : requête HTTP vers graph.facebook.com.
"""
import uuid
import requests
from flask import current_app


class WhatsAppService:

    GRAPH_URL = "https://graph.facebook.com"

    # ==================================================
    # ENVOI DE MESSAGE
    # ==================================================
    @staticmethod
    def send_text(account, to: str, text: str) -> dict:
        """
        Envoie un message texte.
        Retourne {'success': bool, 'external_id': str|None, 'error': str|None}.
        """
        if not account:
            return {"success": False, "external_id": None,
                    "error": "Aucun compte WhatsApp fourni."}

        if not account.is_connected:
            return {"success": False, "external_id": None,
                    "error": "Compte WhatsApp non connecté."}

        if current_app.config.get("WHATSAPP_DEV_MODE"):
            fake_id = f"dev_{uuid.uuid4().hex[:16]}"
            current_app.logger.info(
                f"[WA-DEV] Envoi simulé → {to} : {text[:80]}..."
            )
            return {"success": True, "external_id": fake_id, "error": None}

        token = account.get_access_token()
        if not token:
            return {"success": False, "external_id": None,
                    "error": "Token d'accès manquant ou invalide."}

        phone_number_id = account.phone_number_id or current_app.config.get(
            "WHATSAPP_PHONE_NUMBER_ID"
        )
        if not phone_number_id:
            return {"success": False, "external_id": None,
                    "error": "Phone Number ID non configuré."}

        version = current_app.config.get("WHATSAPP_API_VERSION", "v20.0")
        url = f"{WhatsAppService.GRAPH_URL}/{version}/{phone_number_id}/messages"

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to.lstrip("+"),
            "type": "text",
            "text": {"preview_url": False, "body": text},
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=15)
            data = resp.json() if resp.content else {}
            if resp.status_code == 200 and data.get("messages"):
                ext_id = data["messages"][0].get("id")
                return {"success": True, "external_id": ext_id, "error": None}
            err = data.get("error", {}).get("message") or f"HTTP {resp.status_code}"
            return {"success": False, "external_id": None, "error": err[:500]}
        except requests.RequestException as e:
            return {"success": False, "external_id": None, "error": str(e)[:500]}

    # ==================================================
    # TEST DE CONNEXION
    # ==================================================
    @staticmethod
    def test_connection(account) -> dict:
        """
        Vérifie que le token est valide et que le phone_number_id est accessible.
        En dev, on considère la connexion OK si un token est présent.

        Retourne {'success': bool, 'message': str, 'error': str|None}.
        """
        if not account:
            return {"success": False, "message": "", "error": "Compte introuvable."}

        if not account.has_token:
            return {"success": False, "message": "",
                    "error": "Aucun access token configuré."}

        if current_app.config.get("WHATSAPP_DEV_MODE"):
            return {
                "success": True,
                "message": "Mode développement : connexion simulée réussie.",
                "error": None,
            }

        token = account.get_access_token()
        phone_number_id = account.phone_number_id or current_app.config.get(
            "WHATSAPP_PHONE_NUMBER_ID"
        )
        if not phone_number_id:
            return {"success": False, "message": "",
                    "error": "Phone Number ID manquant."}

        version = current_app.config.get("WHATSAPP_API_VERSION", "v20.0")
        url = f"{WhatsAppService.GRAPH_URL}/{version}/{phone_number_id}"
        headers = {"Authorization": f"Bearer {token}"}

        try:
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "success": True,
                    "message": f"Compte accessible : {data.get('display_phone_number', 'N/A')}",
                    "error": None,
                }
            data = resp.json() if resp.content else {}
            err = data.get("error", {}).get("message") or f"HTTP {resp.status_code}"
            return {"success": False, "message": "", "error": err[:500]}
        except requests.RequestException as e:
            return {"success": False, "message": "", "error": str(e)[:500]}

    # ==================================================
    # WEBHOOK
    # ==================================================
    @staticmethod
    def verify_webhook(mode: str, token: str, challenge: str) -> tuple[bool, str]:
        """Vérification du webhook Meta (hub.verify_token)."""
        expected = current_app.config.get("WHATSAPP_VERIFY_TOKEN")
        if mode == "subscribe" and token == expected:
            return True, challenge
        return False, ""