"""
Service d'envoi WhatsApp Cloud API (Meta).

Supporte :
- Messages texte
- Images (avec légende)
- Documents PDF (avec légende)
- Vidéos (avec légende)

En mode DEBUG (WHATSAPP_DEV_MODE=1) : aucune API réelle n'est appelée.
"""
import uuid
import requests
from flask import current_app


class WhatsAppService:

    GRAPH_URL = "https://graph.facebook.com"

    # ==================================================
    # ENVOI DE MESSAGE TEXTE
    # ==================================================
    @staticmethod
    def send_text(account, to: str, text: str) -> dict:
        """
        Envoie un message texte.
        Retourne {'success': bool, 'external_id': str|None, 'error': str|None}.
        """
        return WhatsAppService._send(
            account=account,
            to=to,
            payload_type="text",
            payload_content={"preview_url": False, "body": text or ""},
            log_content=f"TEXTE: {(text or '')[:60]}...",
        )

    # ==================================================
    # ENVOI D'IMAGE
    # ==================================================
    @staticmethod
    def send_image(account, to: str, image_url: str, caption: str = "") -> dict:
        """
        Envoie une image depuis une URL publique.
        Formats supportés : JPG, PNG, WEBP (max 5 Mo).
        """
        if not image_url:
            return {"success": False, "external_id": None,
                    "error": "URL image manquante."}

        payload = {
            "link": image_url,
            "caption": (caption or "")[:1024],
        }
        return WhatsAppService._send(
            account=account,
            to=to,
            payload_type="image",
            payload_content=payload,
            log_content=f"IMAGE: {image_url[:60]}...",
        )

    # ==================================================
    # ENVOI DE DOCUMENT (PDF)
    # ==================================================
    @staticmethod
    def send_document(account, to: str, doc_url: str,
                      filename: str = "document.pdf",
                      caption: str = "") -> dict:
        """
        Envoie un document PDF depuis une URL publique.
        Formats supportés : PDF (max 100 Mo).
        """
        if not doc_url:
            return {"success": False, "external_id": None,
                    "error": "URL document manquante."}

        payload = {
            "link": doc_url,
            "filename": filename or "document.pdf",
            "caption": (caption or "")[:1024],
        }
        return WhatsAppService._send(
            account=account,
            to=to,
            payload_type="document",
            payload_content=payload,
            log_content=f"DOCUMENT: {filename}",
        )

    # ==================================================
    # ENVOI DE VIDÉO
    # ==================================================
    @staticmethod
    def send_video(account, to: str, video_url: str, caption: str = "") -> dict:
        """
        Envoie une vidéo depuis une URL publique.
        Formats supportés : MP4, 3GP (max 16 Mo).
        """
        if not video_url:
            return {"success": False, "external_id": None,
                    "error": "URL vidéo manquante."}

        payload = {
            "link": video_url,
            "caption": (caption or "")[:1024],
        }
        return WhatsAppService._send(
            account=account,
            to=to,
            payload_type="video",
            payload_content=payload,
            log_content=f"VIDEO: {video_url[:60]}...",
        )

    # ==================================================
    # DISPATCHER GÉNÉRIQUE
    # ==================================================
    @staticmethod
    def send_media(account, to: str, media_file, caption: str = "") -> dict:
        """
        Envoie un média (image, document ou vidéo) selon son type.
        `media_file` est un objet MediaFile.
        """
        if not media_file:
            # Fallback : message texte
            return WhatsAppService.send_text(account, to, caption)

        # Utiliser public_url ou construire depuis APP_BASE_URL
        media_url = media_file.public_url
        if not media_url:
            base_url = current_app.config.get("APP_BASE_URL", "").rstrip("/")
            if not base_url:
                return {"success": False, "external_id": None,
                        "error": "APP_BASE_URL non configuré."}
            media_url = f"{base_url}/static/{media_file.file_path}"

        # Caption : celle passée en paramètre ou celle du média
        final_caption = caption or media_file.caption or ""

        if media_file.media_type == "image":
            return WhatsAppService.send_image(account, to, media_url, final_caption)
        elif media_file.media_type == "document":
            return WhatsAppService.send_document(
                account, to, media_url,
                filename=media_file.original_name,
                caption=final_caption,
            )
        elif media_file.media_type == "video":
            return WhatsAppService.send_video(account, to, media_url, final_caption)
        else:
            return {"success": False, "external_id": None,
                    "error": f"Type de média inconnu : {media_file.media_type}"}

    # ==================================================
    # MÉTHODE INTERNE — Envoi via l'API Graph
    # ==================================================
    @staticmethod
    def _send(account, to: str, payload_type: str,
              payload_content: dict, log_content: str = "") -> dict:
        """
        Envoie un payload à l'API WhatsApp Cloud.
        Gère automatiquement le mode DEV.
        """
        if not account:
            return {"success": False, "external_id": None,
                    "error": "Aucun compte WhatsApp fourni."}

        if not account.is_connected:
            return {"success": False, "external_id": None,
                    "error": "Compte WhatsApp non connecté."}

        # ----- MODE DEV (simulation) -----
        if current_app.config.get("WHATSAPP_DEV_MODE"):
            fake_id = f"dev_{uuid.uuid4().hex[:16]}"
            current_app.logger.info(
                f"[WA-DEV] Envoi simulé → {to} | {log_content}"
            )
            return {"success": True, "external_id": fake_id, "error": None}

        # ----- MODE PRODUCTION -----
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
            "type": payload_type,
            payload_type: payload_content,
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=30)
            data = resp.json() if resp.content else {}

            if resp.status_code == 200 and data.get("messages"):
                ext_id = data["messages"][0].get("id")
                current_app.logger.info(
                    f"[WA] Envoi réussi → {to} | {log_content}"
                )
                return {"success": True, "external_id": ext_id, "error": None}

            err = data.get("error", {}).get("message") or f"HTTP {resp.status_code}"
            current_app.logger.warning(
                f"[WA] Échec envoi → {to} | {err}"
            )
            return {"success": False, "external_id": None, "error": err[:500]}

        except requests.RequestException as e:
            return {"success": False, "external_id": None, "error": str(e)[:500]}

    # ==================================================
    # WEBHOOK — VÉRIFICATION
    # ==================================================
    @staticmethod
    def verify_webhook(mode: str, token: str, challenge: str) -> tuple[bool, str]:
        """Vérification du webhook Meta (hub.verify_token)."""
        expected = current_app.config.get("WHATSAPP_VERIFY_TOKEN")
        if mode == "subscribe" and token == expected:
            return True, challenge
        return False, ""

    # ==================================================
    # TEST DE CONNEXION
    # ==================================================
    @staticmethod
    def test_connection(account) -> dict:
        """Vérifie que le token est valide et le phone_number_id accessible."""
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