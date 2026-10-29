"""
LionFlow AI — Client bas niveau WhatsApp Cloud API.
Gère : upload média, récupération URL média, téléchargement, envoi de message.
"""

from __future__ import annotations

import os
from typing import Optional

import requests
from flask import current_app


class WhatsAppAPIError(Exception):
    """Erreur renvoyée par l'API Graph."""

    def __init__(self, message: str, status_code: int = 0, payload: Optional[dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload or {}


class WhatsAppClient:
    """Client HTTP minimal pour l'API WhatsApp Cloud (Meta Graph)."""

    def __init__(self, phone_number_id: str, access_token: str):
        self.phone_number_id = phone_number_id
        self.access_token = access_token
        self.api_version = current_app.config.get("WHATSAPP_API_VERSION", "v20.0")
        self.base_url = f"https://graph.facebook.com/{self.api_version}"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _headers(self, json_mode: bool = True) -> dict:
        headers = {"Authorization": f"Bearer {self.access_token}"}
        if json_mode:
            headers["Content-Type"] = "application/json"
        return headers

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------
    def send_text(self, to: str, body: str) -> dict:
        """Envoie un message texte simple."""
        url = f"{self.base_url}/{self.phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {"preview_url": False, "body": body},
        }
        resp = requests.post(url, headers=self._headers(), json=payload, timeout=20)
        if not resp.ok:
            raise WhatsAppAPIError(
                f"send_text failed: {resp.text[:300]}",
                status_code=resp.status_code,
                payload=self._safe_json(resp),
            )
        return resp.json()

    def send_audio_voice(self, to: str, media_id: str, voice: bool = True) -> dict:
        """Envoie une note vocale (audio OPUS déjà uploadé)."""
        url = f"{self.base_url}/{self.phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "audio",
            "audio": {"id": media_id, "voice": voice},
        }
        resp = requests.post(url, headers=self._headers(), json=payload, timeout=20)
        if not resp.ok:
            raise WhatsAppAPIError(
                f"send_audio_voice failed: {resp.text[:300]}",
                status_code=resp.status_code,
                payload=self._safe_json(resp),
            )
        return resp.json()

    # ------------------------------------------------------------------
    # Médias
    # ------------------------------------------------------------------
    def upload_audio(self, file_path: str, mime_type: str = "audio/ogg") -> str:
        """
        Upload un fichier audio sur l'API Media.
        Retourne le media_id.
        """
        url = f"{self.base_url}/{self.phone_number_id}/media"
        if not os.path.isfile(file_path):
            raise WhatsAppAPIError(f"Fichier introuvable : {file_path}")

        with open(file_path, "rb") as fh:
            files = {
                "file": (os.path.basename(file_path), fh, mime_type),
            }
            data = {
                "messaging_product": "whatsapp",
                "type": mime_type,
            }
            resp = requests.post(
                url,
                headers={"Authorization": f"Bearer {self.access_token}"},
                files=files,
                data=data,
                timeout=60,
            )
        if not resp.ok:
            raise WhatsAppAPIError(
                f"upload_audio failed: {resp.text[:300]}",
                status_code=resp.status_code,
                payload=self._safe_json(resp),
            )
        return resp.json()["id"]

    def get_media_url(self, media_id: str) -> str:
        """Récupère l'URL temporaire (5 min) d'un média."""
        url = f"{self.base_url}/{media_id}"
        resp = requests.get(url, headers=self._headers(json_mode=False), timeout=20)
        if not resp.ok:
            raise WhatsAppAPIError(
                f"get_media_url failed: {resp.text[:300]}",
                status_code=resp.status_code,
                payload=self._safe_json(resp),
            )
        data = resp.json()
        return data["url"]

    def download_media(self, media_id: str) -> bytes:
        """
        Télécharge un média en 2 étapes :
        1) GET /{media_id} → URL temporaire
        2) GET URL temporaire avec Bearer token (obligatoire)
        """
        signed_url = self.get_media_url(media_id)
        resp = requests.get(
            signed_url,
            headers={"Authorization": f"Bearer {self.access_token}"},
            timeout=60,
        )
        if not resp.ok:
            raise WhatsAppAPIError(
                f"download_media failed: {resp.text[:300]}",
                status_code=resp.status_code,
            )
        return resp.content

    def get_media_metadata(self, media_id: str) -> dict:
        """Retourne les métadonnées d'un média (mime_type, file_size, sha256…)."""
        url = f"{self.base_url}/{media_id}"
        resp = requests.get(url, headers=self._headers(json_mode=False), timeout=20)
        if not resp.ok:
            raise WhatsAppAPIError(
                f"get_media_metadata failed: {resp.text[:300]}",
                status_code=resp.status_code,
            )
        return resp.json()

    # ------------------------------------------------------------------
    # Util
    # ------------------------------------------------------------------
    @staticmethod
    def _safe_json(resp) -> dict:
        try:
            return resp.json()
        except ValueError:
            return {}