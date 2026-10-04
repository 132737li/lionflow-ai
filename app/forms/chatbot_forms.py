"""
Formulaires WTForms pour le chatbot.
"""
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, IntegerField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Length, Optional, NumberRange, ValidationError


MATCH_TYPE_CHOICES = [
    ("contains", "Contient (recommandé)"),
    ("exact", "Correspondance exacte"),
    ("starts_with", "Commence par"),
]


class ChatbotRuleForm(FlaskForm):
    name = StringField(
        "Nom de la règle (interne)",
        validators=[DataRequired(message="Le nom est requis."), Length(max=200)],
    )
    keywords = StringField(
        "Mots-clés déclencheurs (séparés par des virgules)",
        validators=[DataRequired(message="Au moins un mot-clé est requis."), Length(max=1000)],
    )
    response = TextAreaField(
        "Réponse automatique",
        validators=[DataRequired(message="La réponse est requise."), Length(max=4096)],
    )
    match_type = SelectField(
        "Type de correspondance",
        choices=MATCH_TYPE_CHOICES,
        default="contains",
    )
    priority = IntegerField(
        "Priorité (1 = haute, 100 = basse)",
        validators=[Optional(), NumberRange(min=1, max=100)],
        default=50,
    )
    send_menu = BooleanField("Envoyer aussi un menu (à venir)")
    is_active = BooleanField("Activer cette règle", default=True)
    submit = SubmitField("Enregistrer")

    def validate_keywords(self, field):
        """Vérifie qu'il y a au moins un mot-clé non vide."""
        keywords = [k.strip() for k in (field.data or "").split(",") if k.strip()]
        if not keywords:
            raise ValidationError("Au moins un mot-clé valide est requis.")