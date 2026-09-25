"""
Formulaires WTForms pour l'authentification.
Validation côté serveur + CSRF.
"""
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import (
    DataRequired, Email, Length, EqualTo, Regexp, ValidationError,
)

from app.models.user import User


class RegisterForm(FlaskForm):
    first_name = StringField(
        "Prénom",
        validators=[DataRequired(message="Le prénom est requis."), Length(max=100)],
    )
    last_name = StringField(
        "Nom",
        validators=[DataRequired(message="Le nom est requis."), Length(max=100)],
    )
    email = StringField(
        "Email",
        validators=[
            DataRequired(message="L'email est requis."),
            Email(message="Email invalide."),
            Length(max=255),
        ],
    )
    password = PasswordField(
        "Mot de passe",
        validators=[
            DataRequired(message="Le mot de passe est requis."),
            Length(min=8, message="Au moins 8 caractères."),
            Regexp(r".*[A-Za-z].*", message="Doit contenir une lettre."),
            Regexp(r".*\d.*", message="Doit contenir un chiffre."),
        ],
    )
    confirm_password = PasswordField(
        "Confirmer le mot de passe",
        validators=[
            DataRequired(message="La confirmation est requise."),
            EqualTo("password", message="Les mots de passe ne correspondent pas."),
        ],
    )
    accept_terms = BooleanField(
        "J'accepte les conditions d'utilisation",
        validators=[DataRequired(message="Vous devez accepter les conditions.")],
    )
    submit = SubmitField("Créer mon compte")

    def validate_email(self, field):
        if User.query.filter_by(email=field.data.lower().strip()).first():
            raise ValidationError("Cet email est déjà utilisé.")


class LoginForm(FlaskForm):
    email = StringField(
        "Email",
        validators=[DataRequired(), Email(), Length(max=255)],
    )
    password = PasswordField(
        "Mot de passe",
        validators=[DataRequired()],
    )
    remember = BooleanField("Se souvenir de moi")
    submit = SubmitField("Se connecter")


class ForgotPasswordForm(FlaskForm):
    email = StringField(
        "Email",
        validators=[DataRequired(), Email(), Length(max=255)],
    )
    submit = SubmitField("Envoyer le lien de réinitialisation")


class ResetPasswordForm(FlaskForm):
    password = PasswordField(
        "Nouveau mot de passe",
        validators=[
            DataRequired(),
            Length(min=8),
            Regexp(r".*[A-Za-z].*", message="Doit contenir une lettre."),
            Regexp(r".*\d.*", message="Doit contenir un chiffre."),
        ],
    )
    confirm_password = PasswordField(
        "Confirmer",
        validators=[DataRequired(), EqualTo("password")],
    )
    submit = SubmitField("Réinitialiser le mot de passe")


class ChangePasswordForm(FlaskForm):
    current_password = PasswordField(
        "Mot de passe actuel",
        validators=[DataRequired()],
    )
    new_password = PasswordField(
        "Nouveau mot de passe",
        validators=[
            DataRequired(),
            Length(min=8),
            Regexp(r".*[A-Za-z].*", message="Doit contenir une lettre."),
            Regexp(r".*\d.*", message="Doit contenir un chiffre."),
        ],
    )
    confirm_password = PasswordField(
        "Confirmer",
        validators=[DataRequired(), EqualTo("new_password")],
    )
    submit = SubmitField("Changer le mot de passe")