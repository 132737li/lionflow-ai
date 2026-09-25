"""
Formulaires WTForms pour les comptes WhatsApp Cloud API.
Pays par défaut : Burundi. Tous les pays acceptés.
"""
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SelectField, SubmitField
from wtforms.validators import DataRequired, Length, Optional, ValidationError

from app.utils.validators import normalize_phone


# 🌍 Liste des pays (Burundi par défaut)
COUNTRY_CHOICES = [
    ("BI", "🇧🇮 Burundi (+257)"),
    ("CD", "🇨🇩 RD Congo (+243)"),
    ("RW", "🇷🇼 Rwanda (+250)"),
    ("TZ", "🇹🇿 Tanzanie (+255)"),
    ("KE", "🇰🇪 Kenya (+254)"),
    ("UG", "🇺🇬 Ouganda (+256)"),
    ("FR", "🇫🇷 France (+33)"),
    ("BE", "🇧🇪 Belgique (+32)"),
    ("CH", "🇨🇭 Suisse (+41)"),
    ("CA", "🇨🇦 Canada (+1)"),
    ("US", "🇺🇸 États-Unis (+1)"),
    ("GB", "🇬🇧 Royaume-Uni (+44)"),
    ("DE", "🇩🇪 Allemagne (+49)"),
    ("ES", "🇪🇸 Espagne (+34)"),
    ("IT", "🇮🇹 Italie (+39)"),
    ("MA", "🇲🇦 Maroc (+212)"),
    ("DZ", "🇩🇿 Algérie (+213)"),
    ("TN", "🇹🇳 Tunisie (+216)"),
    ("SN", "🇸🇳 Sénégal (+221)"),
    ("CI", "🇨🇮 Côte d'Ivoire (+225)"),
    ("CM", "🇨🇲 Cameroun (+237)"),
    ("ML", "🇲🇱 Mali (+223)"),
    ("BF", "🇧🇫 Burkina Faso (+226)"),
    ("BJ", "🇧🇯 Bénin (+229)"),
    ("TG", "🇹🇬 Togo (+228)"),
    ("NE", "🇳🇪 Niger (+227)"),
    ("GN", "🇬🇳 Guinée (+224)"),
    ("NG", "🇳🇬 Nigeria (+234)"),
    ("ZA", "🇿🇦 Afrique du Sud (+27)"),
    ("OTHER", "🌍 Autre pays"),
]


class WhatsAppAccountForm(FlaskForm):
    name = StringField(
        "Nom du compte",
        validators=[DataRequired(message="Le nom est requis."), Length(max=150)],
    )
    country_code = SelectField(
        "Indicatif pays",
        choices=COUNTRY_CHOICES,
        default="BI",
    )
    phone_number = StringField(
        "Numéro WhatsApp",
        validators=[DataRequired(message="Le numéro est requis."), Length(max=30)],
    )
    phone_number_id = StringField(
        "Phone Number ID (Meta)",
        validators=[Optional(), Length(max=80)],
    )
    business_account_id = StringField(
        "WhatsApp Business Account ID",
        validators=[Optional(), Length(max=80)],
    )
    access_token = PasswordField(
        "Access Token (laisser vide pour ne pas modifier)",
        validators=[Optional(), Length(max=1024)],
    )
    status = SelectField(
        "Statut",
        choices=[
            ("disconnected", "Déconnecté"),
            ("connected", "Connecté"),
            ("error", "Erreur"),
        ],
        default="disconnected",
    )
    submit = SubmitField("Enregistrer")

    def validate_phone_number(self, field):
        region = self.country_code.data if self.country_code.data else "BI"
        if region == "OTHER":
            region = "BI"
        normalized = normalize_phone(field.data, default_region=region)
        if not normalized:
            raise ValidationError(
                "Numéro invalide. Entrez un numéro international "
                "(ex: +257 79 123 456 pour le Burundi)."
            )
        self.phone_number.data = normalized