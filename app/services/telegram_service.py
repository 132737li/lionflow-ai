"""
Service d'envoi de messages via l'API Telegram Bot.
"""
import requests
from flask import current_app

class TelegramService:
    @staticmethod
    def send_message(account, chat_id: str, text: str) -> dict:
        token = account.get_bot_token()
        if not token:
            return {"success": False, "error": "Token Telegram invalide ou manquant"}

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML"
        }

        try:
            resp = requests.post(url, json=payload, timeout=10)
            data = resp.json()
            if resp.status_code == 200 and data.get("ok"):
                return {"success": True, "external_id": str(data["result"]["message_id"])}
            return {"success": False, "error": data.get("description", "Erreur Telegram inconnue")}
        except Exception as e:
            current_app.logger.error(f"[Telegram] Erreur API: {e}")
            return {"success": False, "error": str(e)}