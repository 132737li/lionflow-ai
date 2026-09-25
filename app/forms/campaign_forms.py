"""
Formulaires WTForms pour les campagnes.
"""
from flask_wtf import FlaskForm
from wtforms import (
    StringField, TextAreaField, SelectField, DateTimeLocalField,
    SelectMultipleField, SubmitField,
)
from wtforms.validators import DataRequired, Length, Optional, ValidationError
from wtforms.widgets import CheckboxInput, ListWidget


class MultiCheckboxField(SelectMultipleField):
    """SelectMultipleField affiché en cases à cocher."""
    widget = ListWidget(prefix_label=False)
    option_widget = CheckboxInput()


class CampaignForm(FlaskForm):
    name = StringField(
        "Nom de la campagne",
        validators=[DataRequired(message="Le nom est requis."), Length(max=200)],
    )
    template_id = SelectField(
        "Modèle de message",
        coerce=int,
        validators=[Optional()],
    )
    whatsapp_account_id = SelectField(
        "Compte WhatsApp",
        coerce=int,
        validators=[Optional()],
    )
    message = TextAreaField(
        "Message personnalisé (optionnel si modèle sélectionné)",
        validators=[Optional(), Length(max=4096)],
    )
    scheduled_at = DateTimeLocalField(
        "Programmer l'envoi (optionnel)",
        format="%Y-%m-%dT%H:%M",
        validators=[Optional()],
    )
    timezone = SelectField(
        "Fuseau horaire",
        choices=[
            ("UTC", "UTC"),
            ("Europe/Paris", "Europe/Paris"),
            ("Africa/Casablanca", "Africa/Casablanca"),
            ("Africa/Dakar", "Africa/Dakar"),
            ("Africa/Abidjan", "Africa/Abidjan"),
            ("America/New_York", "America/New_York"),
            ("America/Montreal", "America/Montreal"),
        ],
        default="UTC",
    )
    contact_ids = MultiCheckboxField(
        "Contacts ciblés",
        coerce=int,
        validators=[Optional()],
    )
    submit = SubmitField("Enregistrer")

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators):
            return False
        # Au moins un message OU un template
        if not self.template_id.data and not (self.message.data or "").strip():
            self.message.errors.append(
                "Sélectionnez un modèle ou saisissez un message."
            )
            return False
        return True