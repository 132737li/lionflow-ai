"""
Routes d'authentification (UI Jinja2).
Sessions gérées par Flask-Login, CSRF par Flask-WTF.
"""
from datetime import datetime
from urllib.parse import urlparse, urljoin

from flask import (
    Blueprint, render_template, redirect, url_for, flash,
    request, session, current_app, abort,
)
from flask_login import login_user, logout_user, login_required, current_user

from app.forms.auth_forms import (
    RegisterForm, LoginForm, ForgotPasswordForm,
    ResetPasswordForm, ChangePasswordForm,
)
from app.services.auth_service import AuthService, AuthError
from app.extensions import db


auth_bp = Blueprint("auth", __name__, template_folder="../templates/auth")


# --------------------------------------------------
# Anti open-redirect
# --------------------------------------------------
def _is_safe_url(target: str) -> bool:
    if not target:
        return False
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ("http", "https") and ref_url.netloc == test_url.netloc


# ==================================================
# INSCRIPTION
# ==================================================
@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    form = RegisterForm()
    if form.validate_on_submit():
        try:
            user = AuthService.register(
                {
                    "email": form.email.data,
                    "password": form.password.data,
                    "first_name": form.first_name.data,
                    "last_name": form.last_name.data,
                }
            )
            flash("Votre compte a été créé avec succès. Connectez-vous.", "success")
            return redirect(url_for("auth.login"))
        except AuthError as e:
            flash(e.message, "danger")

    return render_template("auth/register.html", form=form)


# ==================================================
# CONNEXION
# ==================================================
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    form = LoginForm()
    if form.validate_on_submit():
        try:
            user = AuthService.authenticate(form.email.data, form.password.data)
            login_user(user, remember=bool(form.remember.data))

            # Redirection vers la page demandée si safe
            nxt = request.args.get("next")
            if nxt and _is_safe_url(nxt):
                return redirect(nxt)
            return redirect(url_for("dashboard.index"))
        except AuthError as e:
            flash(e.message, "danger")

    return render_template("auth/login.html", form=form)


# ==================================================
# DÉCONNEXION
# ==================================================
@auth_bp.route("/logout", methods=["GET", "POST"])
@login_required
def logout():
    AuthService.log_logout(current_user)
    logout_user()
    session.clear()
    flash("Vous êtes déconnecté.", "info")
    return redirect(url_for("auth.login"))


# ==================================================
# MOT DE PASSE OUBLIÉ
# ==================================================
@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    form = ForgotPasswordForm()
    reset_link = None

    if form.validate_on_submit():
        user, raw = AuthService.create_reset_token(form.email.data)
        if user and raw:
            reset_link = AuthService.send_reset_email(user, raw)

        # Anti-énumération : message identique même si email inconnu
        flash(
            "Si un compte existe avec cet email, un lien de réinitialisation "
            "vient d'être envoyé.",
            "info",
        )

        # En mode DEBUG, on affiche le lien pour permettre le test local
        if current_app.config.get("DEBUG") and reset_link:
            flash(f"[DEV] Lien direct : {reset_link}", "warning")

        return redirect(url_for("auth.login"))

    return render_template("auth/forgot_password.html", form=form)


# ==================================================
# RÉINITIALISER MOT DE PASSE
# ==================================================
@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token: str):
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    # Validation préalable du token
    user = AuthService.validate_reset_token(token)
    if not user:
        flash("Lien invalide ou expiré. Demandez un nouveau lien.", "danger")
        return redirect(url_for("auth.forgot_password"))

    form = ResetPasswordForm()
    if form.validate_on_submit():
        try:
            AuthService.reset_password(token, form.password.data)
            flash("Mot de passe réinitialisé. Connectez-vous.", "success")
            return redirect(url_for("auth.login"))
        except AuthError as e:
            flash(e.message, "danger")

    return render_template("auth/reset_password.html", form=form, token=token)


# ==================================================
# CHANGER MOT DE PASSE (connecté)
# ==================================================
@auth_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        try:
            AuthService.change_password(
                current_user,
                form.current_password.data,
                form.new_password.data,
            )
            flash("Mot de passe modifié avec succès.", "success")
            return redirect(url_for("auth.profile"))
        except AuthError as e:
            flash(e.message, "danger")

    return render_template("auth/change_password.html", form=form)


# ==================================================
# PROFIL
# ==================================================
@auth_bp.route("/profile")
@login_required
def profile():
    return render_template("auth/profile.html")