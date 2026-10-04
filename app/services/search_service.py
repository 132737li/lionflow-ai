"""
Service de recherche globale.
Recherche dans toutes les ressources de l'entreprise active.
"""
from sqlalchemy import or_

from app.extensions import db
from app.models.contact import Contact
from app.models.campaign import Campaign
from app.models.template import Template
from app.models.message import Message
from app.models.chatbot_conversation import ChatbotConversation


class SearchService:

    @staticmethod
    def search(business, query: str, limit_per_type: int = 5) -> dict:
        """
        Recherche globale dans toutes les ressources d'une entreprise.
        Retourne un dict groupé par type.
        """
        if not query or len(query.strip()) < 2:
            return {
                "contacts": [],
                "campaigns": [],
                "templates": [],
                "messages": [],
                "conversations": [],
                "total": 0,
            }

        q = query.strip()
        like = f"%{q}%"

        # ---- Contacts ----
        contacts = (
            Contact.query
            .filter(
                Contact.business_id == business.id,
                or_(
                    Contact.first_name.ilike(like),
                    Contact.last_name.ilike(like),
                    Contact.phone.ilike(like),
                    Contact.email.ilike(like),
                    Contact.company.ilike(like),
                ),
            )
            .limit(limit_per_type)
            .all()
        )

        # ---- Campagnes ----
        campaigns = (
            Campaign.query
            .filter(
                Campaign.business_id == business.id,
                Campaign.name.ilike(like),
            )
            .order_by(Campaign.created_at.desc())
            .limit(limit_per_type)
            .all()
        )

        # ---- Modèles ----
        templates = (
            Template.query
            .filter(
                Template.business_id == business.id,
                or_(
                    Template.name.ilike(like),
                    Template.content.ilike(like),
                ),
            )
            .limit(limit_per_type)
            .all()
        )

        # ---- Messages ----
        messages = (
            Message.query
            .join(Campaign, Message.campaign_id == Campaign.id)
            .filter(
                Campaign.business_id == business.id,
                Message.content.ilike(like),
            )
            .order_by(Message.created_at.desc())
            .limit(limit_per_type)
            .all()
        )

        # ---- Conversations chatbot ----
        conversations = (
            ChatbotConversation.query
            .filter(
                ChatbotConversation.business_id == business.id,
                ChatbotConversation.trigger_message.ilike(like),
            )
            .order_by(ChatbotConversation.created_at.desc())
            .limit(limit_per_type)
            .all()
        )

        # ---- Formatage des résultats ----
        results = {
            "contacts": [
                {
                    "id": c.id,
                    "title": c.full_name,
                    "subtitle": c.phone,
                    "url": f"/contacts/{c.id}",
                    "type": "contact",
                    "icon": "bi-person",
                }
                for c in contacts
            ],
            "campaigns": [
                {
                    "id": c.id,
                    "title": c.name,
                    "subtitle": f"Statut : {c.status} · {c.total_contacts} contacts",
                    "url": f"/campaigns/{c.id}",
                    "type": "campaign",
                    "icon": "bi-megaphone",
                }
                for c in campaigns
            ],
            "templates": [
                {
                    "id": t.id,
                    "title": t.name,
                    "subtitle": (t.content or "")[:80],
                    "url": f"/templates/{t.id}/edit",
                    "type": "template",
                    "icon": "bi-file-text",
                }
                for t in templates
            ],
            "messages": [
                {
                    "id": m.id,
                    "title": (m.content or "")[:60],
                    "subtitle": f"→ {m.contact.full_name if m.contact else '—'}",
                    "url": f"/messages/?campaign_id={m.campaign_id}",
                    "type": "message",
                    "icon": "bi-envelope",
                }
                for m in messages
            ],
            "conversations": [
                {
                    "id": c.id,
                    "title": (c.trigger_message or "")[:60],
                    "subtitle": f"{c.contact.full_name if c.contact else 'Contact inconnu'} · {c.status}",
                    "url": f"/chatbot/conversations/{c.id}",
                    "type": "conversation",
                    "icon": "bi-robot",
                }
                for c in conversations
            ],
        }

        results["total"] = sum(len(v) for v in results.values() if isinstance(v, list))

        return results