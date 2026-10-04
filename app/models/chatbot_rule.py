"""
Modèle ChatbotRule — règle de réponse automatique du chatbot.
"""
from datetime import datetime, timezone
from app.extensions import db


def _utcnow():
    """Heure UTC naïve (compatible MySQL DATETIME)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ChatbotRule(db.Model):
    __tablename__ = "chatbot_rules"

    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(
        db.Integer,
        db.ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = db.Column(db.String(200), nullable=False)  # Nom de la règle (interne)

    # 🔑 Déclencheurs (CSV : "bonjour,salut,hello")
    keywords = db.Column(db.String(1000), nullable=False)

    # 📝 Réponse automatique
    response = db.Column(db.Text, nullable=False)

    # ⚙️ Type de correspondance
    # exact : "bonjour" uniquement
    # contains : "bonjour tout le monde" contient "bonjour"
    # starts_with : "bonjour, j'ai une question" commence par "bonjour"
    match_type = db.Column(
        db.Enum("exact", "contains", "starts_with", name="chatbot_match_type"),
        nullable=False,
        default="contains",
    )

    # 🎯 Priorité (1 = haute, 100 = basse)
    priority = db.Column(db.Integer, nullable=False, default=50, index=True)

    # 📌 Options
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    send_menu = db.Column(db.Boolean, nullable=False, default=False)  # Renvoyer aussi un menu

    # 📊 Statistiques
    usage_count = db.Column(db.Integer, nullable=False, default=0)
    last_used_at = db.Column(db.DateTime)

    # 🕒 Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    # ----- Relations -----
    business = db.relationship("Business", backref=db.backref("chatbot_rules", lazy="dynamic"))

    # ----- Propriétés -----
    @property
    def keywords_list(self) -> list:
        """Retourne les mots-clés sous forme de liste."""
        if not self.keywords:
            return []
        return [k.strip().lower() for k in self.keywords.split(",") if k.strip()]

    def set_keywords(self, keywords: list) -> None:
        """Enregistre une liste de mots-clés en CSV."""
        self.keywords = ",".join(k.strip() for k in keywords if k and k.strip())

    def matches(self, message: str) -> bool:
        """Vérifie si le message correspond à cette règle."""
        if not self.is_active or not message:
            return False

        message_lower = message.lower().strip()
        keywords = self.keywords_list

        for kw in keywords:
            if self.match_type == "exact":
                if message_lower == kw:
                    return True
            elif self.match_type == "starts_with":
                if message_lower.startswith(kw):
                    return True
            else:  # contains (défaut)
                if kw in message_lower:
                    return True
        return False

    def increment_usage(self) -> None:
        """Incrémente le compteur d'utilisation."""
        self.usage_count += 1
        self.last_used_at = _utcnow()

    def __repr__(self) -> str:
        return f"<ChatbotRule {self.id} {self.name} [{self.match_type}]>"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "business_id": self.business_id,
            "name": self.name,
            "keywords": self.keywords_list,
            "response": self.response,
            "match_type": self.match_type,
            "priority": self.priority,
            "is_active": self.is_active,
            "send_menu": self.send_menu,
            "usage_count": self.usage_count,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }