"""
Service de gestion des templates de campagnes.
Fournit :
- Les presets globaux (Noël, Black Friday, Bienvenue…)
- La création auto des templates globaux en BDD
- Le rendu d'un template pour l'affichage
"""
from app.extensions import db
from app.models.campaign_template import CampaignTemplate


# ==================================================
# PRESETS GLOBAUX (fournis par LionFlow AI)
# ==================================================
GLOBAL_PRESETS = [
    {
        "name": "Promo Noël 🎄",
        "description": "Offrez une promotion spéciale à vos clients pour Noël.",
        "icon": "🎄",
        "category": "evenement",
        "default_message": (
            "🎄 Bonjour {{prenom}} !\n\n"
            "Toute l'équipe de {{entreprise}} vous souhaite de joyeuses fêtes !\n\n"
            "Profitez de -20% sur toutes nos offres jusqu'au 31 décembre. 🎁\n\n"
            "Répondez OUI pour en profiter !"
        ),
    },
    {
        "name": "Black Friday 🖤",
        "description": "Campagne de promotion agressive pour le Black Friday.",
        "icon": "🖤",
        "category": "promotion",
        "default_message": (
            "🖤 BLACK FRIDAY chez {{entreprise}} !\n\n"
            "Bonjour {{prenom}}, une offre exceptionnelle rien que pour vous :\n"
            "→ -50% sur toute la boutique (24h seulement) !\n\n"
            "Répondez VITE pour en profiter ⏰"
        ),
    },
    {
        "name": "Bienvenue nouveaux clients 👋",
        "description": "Message de bienvenue à envoyer aux nouveaux clients.",
        "icon": "👋",
        "category": "bienvenue",
        "default_message": (
            "Bonjour {{prenom}} 👋\n\n"
            "Bienvenue chez {{entreprise}} ! Nous sommes ravis de vous compter "
            "parmi nos clients.\n\n"
            "Une question ? Répondez à ce message, nous serons ravis de vous aider."
        ),
    },
    {
        "name": "Relance panier abandonné 🛒",
        "description": "Relancez les clients qui n'ont pas finalisé leur commande.",
        "icon": "🛒",
        "category": "relance",
        "default_message": (
            "Bonjour {{prenom}} 👋\n\n"
            "Vous avez laissé des articles dans votre panier chez {{entreprise}} 🛒\n\n"
            "Votre commande est toujours disponible. Finalisez-la quand vous voulez !\n\n"
            "Besoin d'aide ? Répondez à ce message."
        ),
    },
    {
        "name": "Anniversaire client 🎂",
        "description": "Souhaitez un joyeux anniversaire à vos clients.",
        "icon": "🎂",
        "category": "anniversaire",
        "default_message": (
            "🎉 Joyeux anniversaire {{prenom}} ! 🎂\n\n"
            "Toute l'équipe de {{entreprise}} vous souhaite une merveilleuse journée.\n\n"
            "Pour fêter ça, profitez de -15% cette semaine avec le code BDAY15 🎁"
        ),
    },
    {
        "name": "Rappel de rendez-vous 📅",
        "description": "Rappeler un rendez-vous à venir.",
        "icon": "📅",
        "category": "info",
        "default_message": (
            "Bonjour {{prenom}} 👋\n\n"
            "Petit rappel : votre rendez-vous chez {{entreprise}} approche.\n\n"
            "À très bientôt ! Si vous devez reporter, répondez à ce message."
        ),
    },
    {
        "name": "Enquête de satisfaction ⭐",
        "description": "Demander un avis client après une prestation.",
        "icon": "⭐",
        "category": "relance",
        "default_message": (
            "Bonjour {{prenom}} 👋\n\n"
            "Votre avis compte énormément pour {{entreprise}} !\n\n"
            "Comment avez-vous trouvé notre service ? Répondez par une note de 1 à 5 ⭐"
        ),
    },
    {
        "name": "Réengagement client 😊",
        "description": "Relancer les clients inactifs depuis longtemps.",
        "icon": "💌",
        "category": "relance",
        "default_message": (
            "Bonjour {{prenom}} 😊\n\n"
            "Vous nous manquez chez {{entreprise}} !\n\n"
            "Revenez nous voir, nous avons plein de nouveautés à vous montrer.\n\n"
            "À bientôt !"
        ),
    },
    {
        "name": "Promotion flash ⚡",
        "description": "Offre très limitée dans le temps pour créer l'urgence.",
        "icon": "⚡",
        "category": "promotion",
        "default_message": (
            "⚡ PROMO FLASH {{entreprise}} ⚡\n\n"
            "Bonjour {{prenom}}, offre exceptionnelle pendant 24h seulement !\n\n"
            "→ -30% sur tout\n"
            "→ Livraison gratuite\n\n"
            "Répondez VITE, stock limité ! 🔥"
        ),
    },
    {
        "name": "Confirmation de commande ✅",
        "description": "Confirmer une commande passée par un client.",
        "icon": "✅",
        "category": "info",
        "default_message": (
            "Bonjour {{prenom}} 👋\n\n"
            "Votre commande chez {{entreprise}} est bien confirmée ✅\n\n"
            "Nous vous préviendrons dès qu'elle sera prête. Merci pour votre confiance !"
        ),
    },
]


class CampaignTemplateService:
    """Service de gestion des templates de campagnes."""

    # ==================================================
    # S'assurer que les templates globaux existent en BDD
    # ==================================================
    @staticmethod
    def ensure_global_templates() -> int:
        """
        Crée les templates globaux en BDD s'ils n'existent pas.
        Idempotent : peut être appelé plusieurs fois.
        Retourne le nombre de templates créés.
        """
        created = 0
        for preset in GLOBAL_PRESETS:
            exists = CampaignTemplate.query.filter_by(
                business_id=None,
                name=preset["name"],
            ).first()

            if not exists:
                tpl = CampaignTemplate(
                    business_id=None,
                    name=preset["name"],
                    description=preset["description"],
                    icon=preset["icon"],
                    category=preset["category"],
                    default_message=preset["default_message"],
                    is_public=True,
                    is_active=True,
                )
                db.session.add(tpl)
                created += 1

        if created > 0:
            db.session.commit()

        return created

    # ==================================================
    # Récupération pour une entreprise
    # ==================================================
    @staticmethod
    def get_for_business(business, category: str = None):
        """
        Retourne les templates disponibles pour une entreprise :
        - Globaux (business_id = None)
        - Privés de l'entreprise
        """
        from sqlalchemy import or_

        q = CampaignTemplate.query.filter(
            CampaignTemplate.is_active == True,  # noqa: E712
            or_(
                CampaignTemplate.business_id == business.id,
                CampaignTemplate.business_id.is_(None),
            ),
        )

        if category:
            q = q.filter(CampaignTemplate.category == category)

        return q.order_by(
            CampaignTemplate.business_id.is_(None),  # globaux en premier
            CampaignTemplate.usage_count.desc(),
            CampaignTemplate.name,
        ).all()

    @staticmethod
    def get_by_id(template_id: int, business):
        """Retourne un template par ID s'il appartient ou est global."""
        return CampaignTemplate.query.filter(
            CampaignTemplate.id == template_id,
            db.or_(
                CampaignTemplate.business_id == business.id,
                CampaignTemplate.business_id.is_(None),
            ),
        ).first()

    # ==================================================
    # Création manuelle
    # ==================================================
    @staticmethod
    def create(business, data: dict) -> CampaignTemplate:
        """Crée un template privé pour l'entreprise."""
        tpl = CampaignTemplate(
            business_id=business.id,
            name=(data.get("name") or "").strip()[:150],
            description=(data.get("description") or "").strip()[:500] or None,
            icon=(data.get("icon") or "📢").strip()[:10],
            category=data.get("category") or "autre",
            default_message=(data.get("default_message") or "").strip() or None,
            default_timezone=data.get("default_timezone") or "UTC",
            is_public=False,
            is_active=True,
        )
        db.session.add(tpl)
        db.session.commit()
        return tpl

    # ==================================================
    # Catégories disponibles
    # ==================================================
    @staticmethod
    def get_categories() -> list:
        return [
            ("promotion", "Promotion"),
            ("bienvenue", "Bienvenue"),
            ("relance", "Relance"),
            ("evenement", "Événement"),
            ("anniversaire", "Anniversaire"),
            ("info", "Information"),
            ("autre", "Autre"),
        ]

    # ==================================================
    # Statistiques
    # ==================================================
    @staticmethod
    def stats(business) -> dict:
        """Retourne les stats des templates pour le dashboard."""
        templates = CampaignTemplateService.get_for_business(business)
        total = len(templates)
        total_usage = sum(t.usage_count for t in templates)
        most_used = max(templates, key=lambda t: t.usage_count) if templates else None

        return {
            "total": total,
            "total_usage": total_usage,
            "most_used": most_used,
        }