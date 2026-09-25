"""
Formulaires WTForms pour les modèles de messages (templates).
"""
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, SubmitField
from wtforms.validators import DataRequired, Length, Optional

TEMPLATE_CATEGORIES = [
    ("general", "Général"),
    ("bienvenue", "Bienvenue"),
    ("promotion", "Promotion"),
    ("rappel", "Rappel"),
    ("confirmation", "Confirmation de commande"),
    ("anniversaire", "Anniversaire"),
    ("relance", "Relance"),
    ("autre", "Autre"),
]


class TemplateForm(FlaskForm):
    name = StringField(
        "Nom du modèle",
        validators=[DataRequired(message="Le nom est requis."), Length(max=150)],
    )
    category = SelectField(
        "Catégorie",
        choices=TEMPLATE_CATEGORIES,
        default="general",
    )
    language = SelectField(
        "Langue",
        choices=[("fr", "Français"), ("en", "Anglais"), ("ar", "Arabe")],
        default="fr",
    )
    content = TextAreaField(
        "Contenu du message",
        validators=[DataRequired(message="Le contenu est requis."), Length(max=4096)],
    )
    submit = SubmitField("Enregistrer")