"""
Formulaires pour la configuration IA du chatbot.
"""
from flask_wtf import FlaskForm
from wtforms import (
    StringField, TextAreaField, SelectField, IntegerField,
    DecimalField, PasswordField, BooleanField, SubmitField,
)
from wtforms.validators import (
    DataRequired, Length, Optional, NumberRange, ValidationError,
)


PROVIDER_CHOICES = [
    ("openai", "OpenAI (GPT-4o mini, GPT-4o)"),
    ("anthropic", "Anthropic Claude (3.5 Haiku, Sonnet)"),
    ("groq", "Groq (Llama 3.3 70B — très rapide)"),
    ("custom", "Custom (API OpenAI-compatible)"),
]

LANGUAGE_CHOICES = [
    ("auto", "Automatique (même langue que le client)"),
    ("fr", "Français"),
    ("en", "Anglais"),
    ("rn", "Kirundi"),
    ("sw", "Swahili"),
    ("es", "Espagnol"),
    ("pt", "Portugais"),
    ("ar", "Arabe"),
]

MODEL_PRESETS = {
    "openai": [
        ("gpt-4o-mini", "GPT-4o mini (économique, rapide)"),
        ("gpt-4o", "GPT-4o (puissant)"),
        ("gpt-4-turbo", "GPT-4 Turbo"),
    ],
    "anthropic": [
        ("claude-3-5-haiku-20241022", "Claude 3.5 Haiku (rapide)"),
        ("claude-3-5-sonnet-20241022", "Claude 3.5 Sonnet (puissant)"),
    ],
    "groq": [
        ("openai/gpt-oss-120b", "GPT-OSS 120B (recommandé)"),
        ("openai/gpt-oss-20b", "GPT-OSS 20B (rapide)"),
        ("qwen/qwen3.6-27b", "Qwen 3.6 27B (preview, vision)"),
    ],
    "custom": [],
}


class AiConfigForm(FlaskForm):
    is_enabled = BooleanField("Activer l'IA pour ce chatbot")

    provider = SelectField(
        "Fournisseur",
        choices=PROVIDER_CHOICES,
        default="openai",
    )

    model_name = StringField(
        "Modèle",
        validators=[Optional(), Length(max=100)],
        default="gpt-4o-mini",
    )

    api_key = PasswordField(
        "Clé API (laisser vide pour conserver l'actuelle)",
        validators=[Optional(), Length(max=500)],
    )

    api_base_url = StringField(
        "URL de base (uniquement pour 'Custom')",
        validators=[Optional(), Length(max=500)],
        description="Ex: https://api.mon-provider.com/v1",
    )

    system_prompt = TextAreaField(
        "Prompt système (personnalité de l'assistant)",
        validators=[Optional(), Length(max=4000)],
    )

    context = TextAreaField(
        "Contexte additionnel (infos entreprise)",
        validators=[Optional(), Length(max=4000)],
        description="Horaires, tarifs, adresse, services…",
    )

    temperature = DecimalField(
        "Créativité (0 = précis, 1 = créatif)",
        validators=[Optional(), NumberRange(min=0, max=2)],
        default=0.7,
        places=2,
    )

    max_tokens = IntegerField(
        "Longueur max de la réponse (tokens)",
        validators=[Optional(), NumberRange(min=50, max=2000)],
        default=300,
    )

    reply_language = SelectField(
        "Langue des réponses",
        choices=LANGUAGE_CHOICES,
        default="auto",
    )

    max_requests_per_month = IntegerField(
        "Quota mensuel (nombre de réponses IA max)",
        validators=[Optional(), NumberRange(min=0, max=1000000)],
        default=1000,
    )

    submit = SubmitField("Enregistrer la configuration")

    def validate_api_base_url(self, field):
        if self.provider.data == "custom" and not (field.data or "").strip():
            raise ValidationError(
                "L'URL de base est obligatoire pour le provider 'Custom'."
            )