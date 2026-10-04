"""
Routes d'authentification (UI Jinja2).
Sessions gérées par Flask-Login, CSRF par Flask-WTF.
"""
import os
import secrets
from datetime import datetime
from urllib.parse import urlparse, urljoin

from flask import (
    Blueprint, render_template, redirect, url_for, flash,
    request, session, current_app, abort,
)
from flask_login import login_user, logout_user, login_required, current_user

from app.forms.auth_forms import (
    RegisterForm, LoginForm, ForgotPasswordForm,
    ResetPasswordForm, ChangePasswordForm, ProfileForm,
)
from app.services.auth_service import AuthService, AuthError
from app.extensions import db
from app.utils.validators import allowed_file
from app.utils.security import log_activity


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

            # 🔐 2FA activée → demander la vérification
            if user.totp_enabled and user.totp_secret:
                session["2fa_user_id"] = user.id
                session["2fa_remember"] = bool(form.remember.data)
                session["2fa_next"] = request.args.get("next")
                return redirect(url_for("two_factor.verify"))

            # Connexion normale
            login_user(user, remember=bool(form.remember.data))
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

        flash(
            "Si un compte existe avec cet email, un lien de réinitialisation "
            "vient d'être envoyé.",
            "info",
        )

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
# CHANGER MOT DE PASSE
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
# PROFIL (lecture)
# ==================================================
@auth_bp.route("/profile")
@login_required
def profile():
    return render_template("auth/profile.html")


# ==================================================
# ÉDITER LE PROFIL (nom, prénom, avatar)
# ==================================================
def _save_avatar(file_storage, user_id: int) -> str | None:
    """Sauvegarde la photo de profil et retourne le chemin relatif."""
    if not file_storage or not file_storage.filename:
        return None
    if not allowed_file(file_storage.filename,
                        current_app.config["ALLOWED_UPLOAD_EXTENSIONS"]):
        flash("Format d'image non autorisé.", "warning")
        return None

    ext = file_storage.filename.rsplit(".", 1)[1].lower()
    filename = f"avatar_{user_id}_{secrets.token_hex(6)}.{ext}"
    folder = os.path.join(current_app.config["UPLOAD_FOLDER"], "avatars")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, filename)
    file_storage.save(path)
    return f"uploads/avatars/{filename}"


@auth_bp.route("/profile/edit", methods=["GET", "POST"])
@login_required
def edit_profile():
    form = ProfileForm(obj=current_user)
    if form.validate_on_submit():
        current_user.first_name = (form.first_name.data or "").strip() or None
        current_user.last_name = (form.last_name.data or "").strip() or None

        # Sauvegarder l'avatar si un fichier est fourni
        avatar_path = _save_avatar(form.avatar.data, current_user.id)
        if avatar_path:
            # Supprimer l'ancien avatar du disque
            if current_user.avatar_path:
                old_path = os.path.join(
                    current_app.config["UPLOAD_FOLDER"],
                    current_user.avatar_path.replace("uploads/", "")
                )
                try:
                    if os.path.exists(old_path):
                        os.remove(old_path)
                except OSError:
                    pass
            current_user.avatar_path = avatar_path

        db.session.commit()

        log_activity(
            action="profile_update",
            description=f"Profil modifié : {current_user.email}",
        )
        flash("Profil mis à jour.", "success")
        return redirect(url_for("auth.profile"))

    return render_template("auth/edit_profile.html", form=form)


# ==================================================
# SUPPRIMER L'AVATAR
# ==================================================
@auth_bp.route("/profile/avatar/delete", methods=["POST"])
@login_required
def delete_avatar():
    if current_user.avatar_path:
        old_path = os.path.join(
            current_app.config["UPLOAD_FOLDER"],
            current_user.avatar_path.replace("uploads/", "")
        )
        try:
            if os.path.exists(old_path):
                os.remove(old_path)
        except OSError:
            pass
        current_user.avatar_path = None
        db.session.commit()

        log_activity(
            action="avatar_delete",
            description=f"Avatar supprimé : {current_user.email}",
        )
        flash("Photo de profil supprimée.", "info")

    return redirect(url_for("auth.profile"))