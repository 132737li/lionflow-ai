"""
Service Chatbot — moteur de règles + IA fallback.
Traite les messages entrants et génère les réponses automatiques.

Ordre de priorité :
1. Règles (rapide, gratuit, personnalisé)
2. IA (si activée, pour les cas non couverts)
3. Message fallback standard
"""
import re
from datetime import datetime, timezone

from flask import current_app

from app.extensions import db
from app.models.chatbot_rule import ChatbotRule
from app.models.chatbot_conversation import ChatbotConversation
from app.models.contact import Contact
from app.models.ai_config import AiConfig
from app.services.whatsapp_service import WhatsAppService
from app.services.notification_service import NotificationService
from app.utils.security import log_activity


def _utcnow():
    """Heure UTC naïve (compatible MySQL DATETIME)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# Réglages par défaut du chatbot
DEFAULT_SETTINGS = {
    "welcome_message": (
        "Bonjour 👋 Bienvenue !\n\n"
        "Je suis un assistant automatique. "
        "Comment puis-je vous aider ?"
    ),
    "fallback_message": (
        "Je n'ai pas bien compris votre message. 😅\n\n"
        "Un membre de notre équipe va vous répondre bientôt."
    ),
    "transfer_message": (
        "Un membre de notre équipe va prendre le relais dans quelques instants. "
        "Merci de patienter ⏳"
    ),
    "max_auto_replies": 5,
    "escalate_keywords": "agent,humain,parler,responsable,patron",
}


class ChatbotService:
    """Service principal du chatbot."""

    # ==================================================
    # TRAITEMENT D'UN MESSAGE ENTRANT
    # ==================================================
    @staticmethod
    def process_incoming_message(
        business,
        contact: Contact | None,
        message_text: str,
        whatsapp_account=None,
        sender_phone: str = None,
    ) -> dict:
        """
        Traite un message entrant et envoie la réponse automatique si possible.

        Retourne un dict :
        {
            "handled": bool,
            "action": str,      # "rule" | "ai" | "escalate" | "ignored" | "fallback"
            "response": str,
            "conversation_id": int,
            "source": str,      # "rule" | "ai" | "fallback"
        }
        """
        if not business or not message_text:
            return {
                "handled": False, "action": "ignored",
                "response": None, "conversation_id": None,
                "source": None,
            }

        text = message_text.strip()

        # 1. Chercher ou créer la conversation active
        conversation = None
        if contact:
            conversation = (
                ChatbotConversation.query
                .filter_by(
                    business_id=business.id,
                    contact_id=contact.id,
                    status="active",
                )
                .order_by(ChatbotConversation.created_at.desc())
                .first()
            )

        if not conversation:
            conversation = ChatbotConversation(
                business_id=business.id,
                contact_id=contact.id if contact else None,
                status="active",
                trigger_message=text[:500],
            )
            db.session.add(conversation)
            db.session.flush()

        # 2. Vérifier si le message demande un humain
        if ChatbotService._is_escalation_request(text, business):
            conversation.escalate()
            conversation.auto_replies_count += 1
            db.session.commit()

            transfer_msg = ChatbotService._get_setting(business, "transfer_message")
            ChatbotService._send_whatsapp(
                business, contact, sender_phone, transfer_msg, whatsapp_account
            )

            log_activity(
                action="chatbot_escalate",
                description=(
                    f"Chatbot → transfert humain (contact "
                    f"{contact.full_name if contact else sender_phone})"
                ),
                user_id=business.owner_id,
            )

            NotificationService.notify(
                user_id=business.owner_id,
                title="Chatbot — Transfert demandé",
                message=(
                    f"Le client {contact.full_name if contact else sender_phone} "
                    f"a demandé à parler à un humain : {text[:100]}"
                ),
                type="warning",
                link=f"/chatbot/conversations/{conversation.id}",
            )

            return {
                "handled": True,
                "action": "escalate",
                "response": transfer_msg,
                "conversation_id": conversation.id,
                "source": "rule",
            }

        # 3. Chercher une règle correspondante (PRIORITÉ 1)
        matching_rule = ChatbotService._find_matching_rule(business, text)

        if matching_rule:
            response_text = ChatbotService._render_response(
                matching_rule, contact, business
            )
            ChatbotService._send_whatsapp(
                business, contact, sender_phone, response_text, whatsapp_account
            )

            matching_rule.increment_usage()
            conversation.auto_replies_count += 1
            db.session.commit()

            log_activity(
                action="chatbot_auto_reply",
                description=(
                    f"Chatbot (règle) — « {text[:60]} » via « {matching_rule.name} »"
                ),
                user_id=business.owner_id,
            )

            return {
                "handled": True,
                "action": "rule",
                "response": response_text,
                "conversation_id": conversation.id,
                "rule_id": matching_rule.id,
                "source": "rule",
            }

        # 4. Pas de règle → essayer l'IA (PRIORITÉ 2)
        ai_config = AiConfig.query.filter_by(business_id=business.id).first()
        ai_enabled = (
            ai_config is not None
            and ai_config.is_enabled
            and not ai_config.quota_exceeded
            and (ai_config.has_api_key or ai_config.provider == "custom")
        )

        if ai_enabled:
            ai_result = ChatbotService._try_ai(
                business=business,
                ai_config=ai_config,
                contact=contact,
                user_message=text,
                conversation=conversation,
            )

            if ai_result.get("success"):
                response_text = ai_result["reply"]
                ChatbotService._send_whatsapp(
                    business, contact, sender_phone, response_text, whatsapp_account
                )

                conversation.auto_replies_count += 1
                db.session.commit()

                log_activity(
                    action="chatbot_ai_reply",
                    description=(
                        f"Chatbot (IA {ai_config.provider}) — « {text[:60]} »"
                    ),
                    user_id=business.owner_id,
                )

                return {
                    "handled": True,
                    "action": "ai",
                    "response": response_text,
                    "conversation_id": conversation.id,
                    "source": "ai",
                    "tokens_used": ai_result.get("tokens_used", 0),
                }
            else:
                current_app.logger.warning(
                    f"[Chatbot] Erreur IA pour business {business.id} : "
                    f"{ai_result.get('error')}"
                )

        # 5. Vérifier si max_auto_replies atteint → transférer à un humain
        max_replies = ChatbotService._get_setting(business, "max_auto_replies", 5)
        if conversation.auto_replies_count >= max_replies:
            conversation.escalate()
            db.session.commit()

            transfer_msg = ChatbotService._get_setting(business, "transfer_message")
            ChatbotService._send_whatsapp(
                business, contact, sender_phone, transfer_msg, whatsapp_account
            )

            NotificationService.notify(
                user_id=business.owner_id,
                title="Chatbot — Transfert automatique",
                message=(
                    f"Le client {contact.full_name if contact else sender_phone} "
                    f"n'a pas trouvé de réponse après {max_replies} tentatives."
                ),
                type="warning",
                link=f"/chatbot/conversations/{conversation.id}",
            )

            return {
                "handled": True,
                "action": "escalate",
                "response": transfer_msg,
                "conversation_id": conversation.id,
                "source": "rule",
            }

        # 6. Fallback message standard
        fallback_msg = ChatbotService._get_setting(business, "fallback_message")
        ChatbotService._send_whatsapp(
            business, contact, sender_phone, fallback_msg, whatsapp_account
        )

        conversation.auto_replies_count += 1
        db.session.commit()

        return {
            "handled": True,
            "action": "fallback",
            "response": fallback_msg,
            "conversation_id": conversation.id,
            "source": "fallback",
        }

    # ==================================================
    # INTÉGRATION IA
    # ==================================================
    @staticmethod
    def _try_ai(business, ai_config, contact, user_message: str,
                conversation) -> dict:
        """
        Appelle l'IA avec le contexte de la conversation.
        Récupère les derniers messages pour donner du contexte au modèle.
        """
        from app.services.ai_service import AiService

        # Récupérer l'historique récent de la conversation
        history = ChatbotService._get_conversation_history(
            business=business,
            contact=contact,
            limit=6,
        )

        contact_name = None
        if contact and contact.first_name:
            contact_name = contact.first_name

        return AiService.chat(
            business=business,
            user_message=user_message,
            history=history,
            contact_name=contact_name,
        )

    @staticmethod
    def _get_conversation_history(business, contact, limit: int = 6) -> list:
        """
        Récupère les derniers messages échangés avec ce contact.
        Format : [{'role': 'user'|'assistant', 'content': '...'}]
        """
        if not contact:
            return []

        from app.models.message import Message
        from app.models.campaign import Campaign

        # Messages sortants (envoyés au contact) via le join ORM
        outgoing = (
            Message.query
            .join(Campaign, Message.campaign_id == Campaign.id)
            .filter(
                Campaign.business_id == business.id,
                Message.contact_id == contact.id,
            )
            .order_by(Message.created_at.desc())
            .limit(limit)
            .all()
        )

        # Construire un historique simple (assistant uniquement)
        history = []
        for m in reversed(outgoing):
            if m.content:
                history.append({
                    "role": "assistant",
                    "content": m.content[:500],
                })

        return history

    # ==================================================
    # RECHERCHE DE RÈGLE
    # ==================================================
    @staticmethod
    def _find_matching_rule(business, message: str):
        rules = (
            ChatbotRule.query
            .filter_by(business_id=business.id, is_active=True)
            .order_by(ChatbotRule.priority.asc(), ChatbotRule.id.asc())
            .all()
        )
        for rule in rules:
            if rule.matches(message):
                return rule
        return None

    # ==================================================
    # RENDU DE LA RÉPONSE
    # ==================================================
    @staticmethod
    def _render_response(rule: ChatbotRule, contact: Contact | None, business) -> str:
        text = rule.response or ""
        replacements = {
            "{{prenom}}": (contact.first_name if contact else "") or "",
            "{{nom}}": (contact.last_name if contact else "") or "",
            "{{entreprise}}": business.name if business else "",
            "{{telephone}}": (contact.phone if contact else "") or "",
        }
        for k, v in replacements.items():
            text = text.replace(k, v)
        return text

    # ==================================================
    # DÉTECTION DE DEMANDE DE TRANSFERT
    # ==================================================
    @staticmethod
    def _is_escalation_request(message: str, business) -> bool:
        keywords_str = ChatbotService._get_setting(business, "escalate_keywords", "")
        if not keywords_str:
            return False
        keywords = [k.strip().lower() for k in keywords_str.split(",") if k.strip()]
        text = message.lower()
        return any(kw in text for kw in keywords)

    # ==================================================
    # ENVOI WHATSAPP
    # ==================================================
    @staticmethod
    def _send_whatsapp(business, contact, sender_phone: str | None,
                       text: str, whatsapp_account):
        if not text:
            return

        to = None
        if contact and contact.phone:
            to = contact.phone
        elif sender_phone:
            to = sender_phone if sender_phone.startswith("+") else f"+{sender_phone}"

        if not to:
            return

        account = whatsapp_account
        if not account:
            from app.models.whatsapp_account import WhatsAppAccount
            account = (
                WhatsAppAccount.query
                .filter_by(business_id=business.id, status="connected")
                .first()
            )

        if not account:
            current_app.logger.warning(
                f"[Chatbot] Aucun compte WhatsApp pour envoyer la réponse à {to}"
            )
            return

        try:
            WhatsAppService.send_text(account=account, to=to, text=text)
        except Exception:
            current_app.logger.exception("[Chatbot] Erreur d'envoi WhatsApp")

    # ==================================================
    # RÉGLAGES
    # ==================================================
    @staticmethod
    def _get_setting(business, key: str, default=None):
        return DEFAULT_SETTINGS.get(key, default)

    @staticmethod
    def get_settings(business) -> dict:
        return {
            "welcome_message": ChatbotService._get_setting(business, "welcome_message"),
            "fallback_message": ChatbotService._get_setting(business, "fallback_message"),
            "transfer_message": ChatbotService._get_setting(business, "transfer_message"),
            "max_auto_replies": ChatbotService._get_setting(business, "max_auto_replies"),
            "escalate_keywords": ChatbotService._get_setting(business, "escalate_keywords"),
        }