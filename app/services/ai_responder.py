"""
LionFlow AI — Adaptateur IA.

Enveloppe `AiService.chat()` dans une interface simple retournant une string.
Gère :
- le chargement de l'objet Business depuis business_id ;
- l'extraction de `reply` depuis le dict de retour ;
- les erreurs (retourne un fallback lisible, ne plante jamais) ;
- l'historique conversationnel (optionnel).

Utilisé par :
- app/routes/voice.py (chat vocal web)
- app/services/whatsapp_voice_service.py (webhook WhatsApp voix)
"""

from __future__ import annotations

import logging
from typing import Optional

from flask import current_app

logger = logging.getLogger(__name__)


# ===========================================================================
# Fallback multilingue
# ===========================================================================
_FALLBACK_MESSAGES = {
    "fr": "Désolé, je ne peux pas répondre pour le moment. Veuillez réessayer plus tard.",
    "en": "Sorry, I cannot answer right now. Please try again later.",
    "ar": "عذرًا، لا أستطيع الرد الآن. يرجى المحاولة لاحقًا.",
    "es": "Lo siento, no puedo responder ahora. Inténtalo más tarde.",
    "pt": "Desculpe, não posso responder agora. Tente novamente mais tarde.",
    "rn": "Ndababaye, sinshobora gusubiza ubu. Mugerageze nyuma.",
    "sw": "Samahani, siwezi kujibu sasa. Tafadhali jaribu tena baadaye.",
}


def _fallback(language: str) -> str:
    return _FALLBACK_MESSAGES.get(language, _FALLBACK_MESSAGES["fr"])


# ===========================================================================
# Chargement de l'objet Business
# ===========================================================================
def _load_business(business_id: int):
    """Charge l'objet Business depuis son ID."""
    if not business_id:
        return None
    try:
        from app.models.business import Business
        from app.extensions import db
        return db.session.get(Business, int(business_id))
    except Exception as exc:
        logger.exception("[ai_responder] Erreur chargement Business: %s", exc)
        return None


# ===========================================================================
# Point d'entrée public
# ===========================================================================
def generate_reply(
    prompt: str,
    business_id: int,
    user_id: Optional[int] = None,
    language: str = "fr",
    history: Optional[list] = None,
    contact_name: Optional[str] = None,
) -> str:
    """
    Génère une réponse IA via `AiService.chat()`.

    Args:
        prompt       : message de l'utilisateur
        business_id  : ID du business courant
        user_id      : ID utilisateur (info, non utilisé par AiService.chat)
        language     : code langue (fallback uniquement)
        history      : historique conversationnel
                       [{"role": "user"|"assistant", "content": str}, ...]
        contact_name : nom du contact (personnalisation, optionnel)

    Retourne toujours une string non vide.
    """
    if not prompt or not prompt.strip():
        return _fallback(language)

    business = _load_business(business_id)
    if business is None:
        logger.warning(
            "[ai_responder] Business introuvable (id=%s)", business_id
        )
        return _fallback(language)

    # Import tardif pour éviter les imports circulaires
    try:
        from app.services.ai_service import AiService, AiServiceError
    except Exception as exc:
        logger.exception("[ai_responder] Import AiService échoué: %s", exc)
        return _fallback(language)

    try:
        result = AiService.chat(
            business=business,
            user_message=prompt.strip(),
            history=history or [],
            contact_name=contact_name,
        )
    except AiServiceError as exc:
        logger.warning("[ai_responder] AiServiceError: %s", exc.message)
        return _fallback(language)
    except Exception as exc:
        logger.exception("[ai_responder] Erreur inattendue IA: %s", exc)
        return _fallback(language)

    # AiService.chat retourne un dict
    if not isinstance(result, dict):
        logger.warning("[ai_responder] Retour IA non-dict: %r", type(result))
        return _fallback(language)

    if result.get("success") and result.get("reply"):
        return str(result["reply"]).strip()

    err = result.get("error") or "réponse vide"
    logger.info("[ai_responder] IA non disponible: %s", err)
    return _fallback(language)