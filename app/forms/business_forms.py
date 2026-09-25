"""
Formulaires WTForms pour les entreprises.
Pays par défaut : Burundi. Tous les pays acceptés.
"""
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, FileField, SelectField
from wtforms.validators import DataRequired, Optional, Length, ValidationError

from app.utils.validators import is_valid_email, normalize_phone


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


class BusinessForm(FlaskForm):
    name = StringField(
        "Nom de l'entreprise",
        validators=[DataRequired(message="Le nom est requis."), Length(max=200)],
    )
    email = StringField(
        "Email",
        validators=[Optional(), Length(max=255)],
    )
    phone = StringField(
        "Téléphone",
        validators=[Optional(), Length(max=30)],
    )
    address = StringField(
        "Adresse",
        validators=[Optional(), Length(max=500)],
    )
    country = SelectField(
        "Pays",
        choices=COUNTRY_CHOICES,
        default="BI",
    )
    logo = FileField("Logo (png, jpg, jpeg, gif, webp — max 5 Mo)")
    submit = SubmitField("Enregistrer")

    def validate_email(self, field):
        if field.data and not is_valid_email(field.data):
            raise ValidationError("Email invalide.")

    def validate_phone(self, field):
        if field.data:
            region = self.country.data if self.country.data else "BI"
            if region == "OTHER":
                region = "BI"
            normalized = normalize_phone(field.data, default_region=region)
            if not normalized:
                raise ValidationError(
                    "Numéro invalide. Entrez un numéro international "
                    "(ex: +257 79 123 456 pour le Burundi)."
                )
            self.phone.data = normalized