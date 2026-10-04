"""
Service IA pour le chatbot.
Supporte plusieurs providers :
- OpenAI (GPT-4o mini, GPT-4o, etc.)
- Groq (Llama 3.3 70B, Mixtral, etc.) — API compatible OpenAI
- Anthropic (Claude 3.5 Haiku, Sonnet)
- Custom (n'importe quelle API OpenAI-compatible)

Gère le chiffrement des clés, les quotas et les erreurs.
"""
import json
import time

import requests
from flask import current_app

from app.extensions import db
from app.models.ai_config import AiConfig


# ==================================================
# PROMPT SYSTÈME PAR DÉFAUT
# ==================================================
DEFAULT_SYSTEM_PROMPT = """Tu es un assistant virtuel professionnel et courtois pour l'entreprise {business_name}.

Ton rôle :
- Répondre poliment et de manière concise aux questions des clients sur WhatsApp
- Aider avec les informations disponibles (horaires, tarifs, services, disponibilités)
- Si tu ne sais pas, propose de mettre le client en relation avec un agent humain
- Ne jamais inventer d'informations

Règles importantes :
- Réponses courtes (2-3 phrases max, style WhatsApp)
- Ton chaleureux et professionnel
- Utilise des emojis avec parcimonie (1 max par message)
- Termine toujours par une question ouverte ou une proposition d'aide
"""

# ==================================================
# CONFIGURATION DES PROVIDERS
# ==================================================
PROVIDER_CONFIG = {
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "default_model": "llama-3.3-70b-versatile",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
    },
    "anthropic": {
        "base_url": "https://api.anthropic.com/v1",
        "default_model": "claude-3-5-haiku-20241022",
        "auth_header": "x-api-key",
        "auth_prefix": "",
    },
    "custom": {
        "base_url": None,  # Doit être fourni dans api_base_url
        "default_model": "default",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
    },
}


class AiServiceError(Exception):
    """Erreur métier du service IA."""
    def __init__(self, message: str, code: str = "ai_error"):
        super().__init__(message)
        self.message = message
        self.code = code


class AiService:

    # ==================================================
    # POINT D'ENTRÉE PRINCIPAL
    # ==================================================
    @staticmethod
    def chat(
        business,
        user_message: str,
        history: list = None,
        contact_name: str = None,
    ) -> dict:
        """
        Génère une réponse IA pour un message client.

        Args:
            business : objet Business
            user_message : message du client
            history : liste de messages précédents [{role, content}]
            contact_name : nom du contact (pour personnalisation)

        Returns:
            {
                "success": bool,
                "reply": str | None,
                "tokens_used": int,
                "provider": str,
                "error": str | None
            }
        """
        # 1. Vérifier la config
        config = AiConfig.query.filter_by(business_id=business.id).first()
        if not config:
            return {
                "success": False, "reply": None, "tokens_used": 0,
                "provider": None,
                "error": "Aucune configuration IA. Activez l'IA dans les paramètres.",
            }

        if not config.is_enabled:
            return {
                "success": False, "reply": None, "tokens_used": 0,
                "provider": config.provider,
                "error": "IA désactivée.",
            }

        if config.quota_exceeded:
            return {
                "success": False, "reply": None, "tokens_used": 0,
                "provider": config.provider,
                "error": f"Quota mensuel atteint ({config.max_requests_per_month} requêtes).",
            }

        if config.provider != "custom" and not config.has_api_key:
            return {
                "success": False, "reply": None, "tokens_used": 0,
                "provider": config.provider,
                "error": "Clé API manquante.",
            }

        # 2. Construire les messages
        messages = AiService._build_messages(
            config=config,
            business=business,
            user_message=user_message,
            history=history or [],
            contact_name=contact_name,
        )

        # 3. Appeler le provider
        try:
            if config.provider == "anthropic":
                result = AiService._call_anthropic(config, messages)
            else:
                result = AiService._call_openai_compatible(config, messages)
        except AiServiceError as e:
            # Enregistrer l'erreur
            config.last_error = e.message[:500]
            db.session.commit()
            return {
                "success": False, "reply": None, "tokens_used": 0,
                "provider": config.provider, "error": e.message,
            }
        except Exception as e:
            current_app.logger.exception("[AI] Erreur inattendue")
            config.last_error = str(e)[:500]
            db.session.commit()
            return {
                "success": False, "reply": None, "tokens_used": 0,
                "provider": config.provider,
                "error": f"Erreur : {str(e)[:200]}",
            }

        # 4. Succès
        config.last_error = None
        config.increment_usage(tokens=result.get("tokens_used", 0))
        db.session.commit()

        return {
            "success": True,
            "reply": result["reply"],
            "tokens_used": result.get("tokens_used", 0),
            "provider": config.provider,
            "error": None,
        }

    # ==================================================
    # CONSTRUCTION DES MESSAGES
    # ==================================================
    @staticmethod
    def _build_messages(
        config: AiConfig,
        business,
        user_message: str,
        history: list,
        contact_name: str = None,
    ) -> list:
        """
        Construit la liste de messages pour l'API.
        [{'role': 'system', 'content': ...}, {'role': 'user', 'content': ...}]
        """
        # Prompt système
        system = config.system_prompt or DEFAULT_SYSTEM_PROMPT
        system = system.replace("{business_name}", business.name or "notre entreprise")

        if contact_name:
            system += f"\n\nLe client s'appelle {contact_name}. Utilise son prénom quand c'est naturel."

        # Contexte additionnel (infos entreprise)
        if config.context:
            system += f"\n\nInformations sur l'entreprise :\n{config.context}"

        # Langue
        if config.reply_language and config.reply_language != "auto":
            lang_map = {
                "fr": "français",
                "en": "anglais",
                "rn": "kirundi",
                "sw": "swahili",
                "es": "espagnol",
                "pt": "portugais",
                "ar": "arabe",
            }
            lang_name = lang_map.get(config.reply_language, config.reply_language)
            system += f"\n\nRéponds toujours en {lang_name}."
        else:
            system += "\n\nRéponds dans la même langue que le message du client."

        # Assembler
        messages = [{"role": "system", "content": system}]

        # Historique (max 10 derniers messages)
        for msg in history[-10:]:
            if msg.get("role") in ("user", "assistant") and msg.get("content"):
                messages.append({
                    "role": msg["role"],
                    "content": str(msg["content"])[:1000],
                })

        # Message actuel
        messages.append({"role": "user", "content": user_message[:2000]})

        return messages

    # ==================================================
    # APPEL — OpenAI-compatible (OpenAI, Groq, Custom)
    # ==================================================
    @staticmethod
    def _call_openai_compatible(config: AiConfig, messages: list) -> dict:
        """Appel via l'API /chat/completions (format OpenAI)."""
        provider_conf = PROVIDER_CONFIG.get(config.provider, {})

        # Base URL
        if config.provider == "custom":
            base_url = (config.api_base_url or "").rstrip("/")
            if not base_url:
                raise AiServiceError("URL de base manquante pour le provider 'custom'.")
        else:
            base_url = provider_conf.get("base_url")

        url = f"{base_url}/chat/completions"

        # Auth
        api_key = config.get_api_key() or ""
        headers = {
            "Content-Type": "application/json",
            provider_conf.get("auth_header", "Authorization"):
                f"{provider_conf.get('auth_prefix', 'Bearer ')}{api_key}",
        }

        # Payload
        payload = {
            "model": config.model_name or provider_conf.get("default_model"),
            "messages": messages,
            "temperature": config.temperature if config.temperature is not None else 0.7,
            "max_tokens": config.max_tokens or 300,
        }

        try:
            timeout = current_app.config.get("AI_REQUEST_TIMEOUT", 30)
            resp = requests.post(
                url, json=payload, headers=headers, timeout=timeout,
            )
        except requests.Timeout:
            raise AiServiceError("Le service IA n'a pas répondu à temps.")
        except requests.RequestException as e:
            raise AiServiceError(f"Erreur réseau : {str(e)[:200]}")

        # Parser la réponse
        try:
            data = resp.json()
        except ValueError:
            raise AiServiceError(f"Réponse invalide (HTTP {resp.status_code}).")

        if resp.status_code != 200:
            err = (
                data.get("error", {}).get("message")
                if isinstance(data.get("error"), dict)
                else str(data.get("error") or data.get("message") or "")
            )
            if not err:
                err = f"HTTP {resp.status_code}"
            raise AiServiceError(f"{err[:250]}")

        # Extraire le texte
        try:
            reply = data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, AttributeError):
            raise AiServiceError("Réponse IA vide ou malformée.")

        # Tokens
        tokens_used = 0
        usage = data.get("usage") or {}
        if usage:
            tokens_used = int(usage.get("total_tokens") or 0)

        return {"reply": reply, "tokens_used": tokens_used}

    # ==================================================
    # APPEL — Anthropic Claude
    # ==================================================
    @staticmethod
    def _call_anthropic(config: AiConfig, messages: list) -> dict:
        """Appel via l'API /messages (format Anthropic)."""
        provider_conf = PROVIDER_CONFIG["anthropic"]
        url = f"{provider_conf['base_url']}/messages"

        # Anthropic sépare system des messages
        system_content = ""
        conversation = []
        for m in messages:
            if m["role"] == "system":
                system_content = m["content"]
            else:
                conversation.append(m)

        headers = {
            "Content-Type": "application/json",
            "x-api-key": config.get_api_key() or "",
            "anthropic-version": "2023-06-01",
        }

        payload = {
            "model": config.model_name or provider_conf["default_model"],
            "max_tokens": config.max_tokens or 300,
            "temperature": config.temperature if config.temperature is not None else 0.7,
            "system": system_content,
            "messages": conversation,
        }

        try:
            timeout = current_app.config.get("AI_REQUEST_TIMEOUT", 30)
            resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
        except requests.Timeout:
            raise AiServiceError("Le service IA n'a pas répondu à temps.")
        except requests.RequestException as e:
            raise AiServiceError(f"Erreur réseau : {str(e)[:200]}")

        try:
            data = resp.json()
        except ValueError:
            raise AiServiceError(f"Réponse invalide (HTTP {resp.status_code}).")

        if resp.status_code != 200:
            err = (
                data.get("error", {}).get("message")
                if isinstance(data.get("error"), dict)
                else str(data.get("error") or "")
            )
            if not err:
                err = f"HTTP {resp.status_code}"
            raise AiServiceError(f"{err[:250]}")

        # Extraire le texte
        try:
            reply = data["content"][0]["text"].strip()
        except (KeyError, IndexError, AttributeError):
            raise AiServiceError("Réponse IA vide ou malformée.")

        tokens_used = 0
        usage = data.get("usage") or {}
        if usage:
            tokens_used = int(
                (usage.get("input_tokens") or 0) + (usage.get("output_tokens") or 0)
            )

        return {"reply": reply, "tokens_used": tokens_used}

    # ==================================================
    # TEST DE CONNEXION
    # ==================================================
    @staticmethod
    def test_connection(config: AiConfig) -> dict:
        """
        Teste la clé API et la connexion au provider.
        Retourne {'success': bool, 'message': str, 'error': str}.
        """
        if config.provider != "custom" and not config.has_api_key:
            return {
                "success": False, "message": "",
                "error": "Aucune clé API configurée.",
            }

        try:
            result = AiService._call_openai_compatible(
                config=config,
                messages=[
                    {"role": "system", "content": "Tu es un assistant."},
                    {"role": "user", "content": "Réponds exactement : PONG"},
                ],
            ) if config.provider != "anthropic" else AiService._call_anthropic(
                config=config,
                messages=[
                    {"role": "system", "content": "Tu es un assistant."},
                    {"role": "user", "content": "Réponds exactement : PONG"},
                ],
            )

            reply = result.get("reply", "")
            return {
                "success": True,
                "message": (
                    f"Connexion réussie ! Réponse : « {reply[:80]} » "
                    f"({result.get('tokens_used', 0)} tokens)"
                ),
                "error": None,
            }
        except AiServiceError as e:
            return {"success": False, "message": "", "error": e.message}
        except Exception as e:
            return {"success": False, "message": "", "error": str(e)[:300]}

    # ==================================================
    # GETTER / CREATEUR DE CONFIG
    # ==================================================
    @staticmethod
    def get_or_create_config(business) -> AiConfig:
        """Retourne la config IA de l'entreprise, ou la crée."""
        config = AiConfig.query.filter_by(business_id=business.id).first()
        if not config:
            config = AiConfig(
                business_id=business.id,
                provider="openai",
                model_name="gpt-4o-mini",
                is_enabled=False,
                temperature=0.7,
                max_tokens=300,
                reply_language="auto",
                max_requests_per_month=current_app.config.get(
                    "AI_DEFAULT_MAX_REQUESTS_MONTH", 1000
                ),
            )
            db.session.add(config)
            db.session.commit()
        return config

    @staticmethod
    def reset_all_monthly_quotas() -> int:
        """
        Remet à zéro tous les quotas mensuels.
        À appeler par un scheduler au début de chaque mois.
        """
        count = AiConfig.query.update({
            "requests_this_month": 0,
            "reset_quota_at": datetime.now(timezone.utc).replace(tzinfo=None),
        })
        db.session.commit()
        return count


# Import nécessaire pour reset_all_monthly_quotas
from datetime import datetime, timezone