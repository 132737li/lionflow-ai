"""
Formulaires WTForms pour les contacts.
Pays par défaut : Burundi (+257). Tous les pays acceptés.
"""
from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, FileField, SubmitField
from wtforms.validators import DataRequired, Length, Optional, ValidationError

from app.utils.validators import is_valid_email, normalize_phone


CONTACT_STATUS_CHOICES = [
    ("active", "Actif"),
    ("inactive", "Inactif"),
    ("blocked", "Bloqué"),
]

# 🌍 Liste des pays avec indicatif (Burundi par défaut, tous les pays acceptés)
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


class ContactForm(FlaskForm):
    first_name = StringField(
        "Prénom",
        validators=[Optional(), Length(max=120)],
    )
    last_name = StringField(
        "Nom",
        validators=[Optional(), Length(max=120)],
    )
    country_code = SelectField(
        "Indicatif pays",
        choices=COUNTRY_CHOICES,
        default="BI",
    )
    phone = StringField(
        "Numéro WhatsApp",
        validators=[DataRequired(message="Le numéro est requis."), Length(max=30)],
    )
    email = StringField(
        "Email",
        validators=[Optional(), Length(max=255)],
    )
    company = StringField(
        "Entreprise du contact",
        validators=[Optional(), Length(max=200)],
    )
    tags = StringField(
        "Tags (séparés par des virgules)",
        validators=[Optional(), Length(max=500)],
    )
    status = SelectField(
        "Statut",
        choices=CONTACT_STATUS_CHOICES,
        default="active",
    )
    submit = SubmitField("Enregistrer")

    def validate_phone(self, field):
        # Utilise le pays sélectionné comme région par défaut
        region = self.country_code.data if self.country_code.data else "BI"
        if region == "OTHER":
            region = "BI"  # fallback
        normalized = normalize_phone(field.data, default_region=region)
        if not normalized:
            raise ValidationError(
                "Numéro WhatsApp invalide. Entrez un numéro international "
                "(ex: +257 79 123 456 pour le Burundi, "
                "+33 6 12 34 56 78 pour la France)."
            )
        self.phone.data = normalized

    def validate_email(self, field):
        if field.data and not is_valid_email(field.data):
            raise ValidationError("Email invalide.")


class ImportContactsForm(FlaskForm):
    file = FileField(
        "Fichier CSV ou Excel (.csv, .xlsx, .xls)",
        validators=[DataRequired(message="Veuillez sélectionner un fichier.")],
    )
    submit = SubmitField("Importer")


class ContactSearchForm(FlaskForm):
    """Formulaire de recherche (GET)."""
    class Meta:
        csrf = False

    q = StringField("Recherche")
    status = SelectField(
        "Statut",
        choices=[("", "Tous")] + CONTACT_STATUS_CHOICES,
        default="",
    )
    tag = StringField("Tag")