"""
Formulaires WTForms pour les campagnes.
"""
from flask_wtf import FlaskForm
from wtforms import (
    StringField, TextAreaField, SelectField, DateTimeLocalField,
    SelectMultipleField, SubmitField, BooleanField, IntegerField,
)
from wtforms.validators import DataRequired, Length, Optional, ValidationError, NumberRange
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
        validators=[Optional()],choices=[]
    )
    whatsapp_account_id = SelectField(
        "Compte WhatsApp",
        coerce=int,
        validators=[Optional()],choices=[]
    )
    telegram_account_id = SelectField(
        "Compte Telegram",
        coerce=int,
        validators=[Optional()],choices=[]
    )
    media_file_id = SelectField(
        "Média (image, PDF, vidéo)",
        coerce=int,
        validators=[Optional()],choices=[]
    )
    message = TextAreaField(
        "Message personnalisé (optionnel si modèle sélectionné)",
        validators=[Optional(), Length(max=4096)],
    )
    is_ab_test = BooleanField("Activer l'A/B Testing", default=False)
    message_b = TextAreaField(
        "Message B (Variante)",
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

    # ✅ NOUVEAU : Relances automatiques
    follow_up_enabled = BooleanField(
        "Activer les relances automatiques",
        default=False
    )
    follow_up_delay_hours = IntegerField(
        "Délai avant relance (heures)",
        default=24,
        validators=[Optional(), NumberRange(min=1, max=720, message="Le délai doit être entre 1 et 720 heures (30 jours).")]
    )
    follow_up_template_id = SelectField(
        "Template de relance (optionnel)",
        coerce=int,
        validators=[Optional()],
    )
    follow_up_message = TextAreaField(
        "Message de relance personnalisé",
        validators=[Optional(), Length(max=4096)],
    )

    submit = SubmitField("Enregistrer")

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators):
            return False
            
        # Au moins un message OU un template pour le message initial
        if not self.template_id.data and not (self.message.data or "").strip():
            self.message.errors.append(
                "Sélectionnez un modèle ou saisissez un message."
            )
            return False

        # Validation pour les relances
        if self.follow_up_enabled.data:
            has_followup_template = self.follow_up_template_id.data and self.follow_up_template_id.data > 0
            has_followup_text = (self.follow_up_message.data or "").strip()
            
            if not has_followup_template and not has_followup_text:
                self.follow_up_message.errors.append(
                    "Veuillez sélectionner un template de relance ou écrire un message."
                )
                return False

        return True