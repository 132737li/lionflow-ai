"""
Routes 2FA (TOTP).
"""
from flask import (
    Blueprint, render_template, redirect, url_for, flash,
    request, session, current_app,
)
from flask_login import login_required, current_user, login_user

from app.extensions import db
from app.models.user import User
from app.services.top_service import TotpService
from app.utils.security import log_activity


two_factor_bp = Blueprint("two_factor", __name__, template_folder="../templates/auth")


# ==================================================
# ÉTAPE 1 — CONFIGURATION
# ==================================================
@two_factor_bp.route("/setup", methods=["GET", "POST"])
@login_required
def setup():
    """Page de configuration 2FA avec QR code."""
    if current_user.totp_enabled:
        flash("La 2FA est déjà activée sur votre compte.", "info")
        return redirect(url_for("auth.profile"))

    # Générer un secret temporaire (stocké en session)
    if "totp_setup_secret" not in session:
        session["totp_setup_secret"] = TotpService.generate_secret()

    secret = session["totp_setup_secret"]
    qr_code = TotpService.generate_qr_code(current_user, secret)

    if request.method == "POST":
        code = (request.form.get("code") or "").strip()
        if not code:
            flash("Veuillez entrer le code à 6 chiffres.", "danger")
        else:
            ok, backup_codes, error = TotpService.enable_for_user(
                current_user, secret, code
            )
            if ok:
                session.pop("totp_setup_secret", None)
                # Stocker les codes en session pour affichage unique
                session["totp_backup_codes"] = backup_codes
                return redirect(url_for("two_factor.show_backup_codes"))
            else:
                flash(error, "danger")

    return render_template(
        "auth/2fa_setup.html",
        secret=secret,
        qr_code=qr_code,
    )


# ==================================================
# ÉTAPE 2 — AFFICHAGE DES CODES DE SECOURS (une seule fois)
# ==================================================
@two_factor_bp.route("/backup-codes")
@login_required
def show_backup_codes():
    """Affiche les codes de secours (une seule fois)."""
    codes = session.pop("totp_backup_codes", None)
    if not codes:
        return redirect(url_for("auth.profile"))
    return render_template("auth/2fa_backup_codes.html", codes=codes)


# ==================================================
# VÉRIFICATION AU LOGIN
# ==================================================
@two_factor_bp.route("/verify", methods=["GET", "POST"])
def verify():
    """Vérification du code 2FA pendant le login."""
    # Récupérer l'utilisateur en attente
    pending_user_id = session.get("2fa_user_id")
    if not pending_user_id:
        return redirect(url_for("auth.login"))

    user = db.session.get(User, pending_user_id)
    if not user:
        session.pop("2fa_user_id", None)
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        code = (request.form.get("code") or "").strip()

        # Vérifier le code TOTP
        valid = TotpService.verify_code(user.totp_secret, code)

        # Si le code ne passe pas, essayer comme code de secours
        if not valid:
            valid = TotpService.verify_backup_code(user, code)

        if valid:
            # Connexion réussie
            session.pop("2fa_user_id", None)
            session.pop("2fa_remember", None)
            remember = session.pop("2fa_remember", False)
            login_user(user, remember=remember)
            user.last_login_at = __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ).replace(tzinfo=None)
            db.session.commit()

            log_activity(
                action="login_2fa",
                description=f"Connexion 2FA réussie : {user.email}",
                user_id=user.id,
            )

            flash("Connexion réussie.", "success")
            return redirect(url_for("dashboard.index"))

        flash("Code incorrect. Réessayez.", "danger")

    return render_template("auth/2fa_verify.html", user=user)


# ==================================================
# ANNULER LA VÉRIFICATION
# ==================================================
@two_factor_bp.route("/cancel")
def cancel():
    """Annule la vérification 2FA et retourne au login."""
    session.pop("2fa_user_id", None)
    session.pop("2fa_remember", None)
    flash("Vérification annulée.", "info")
    return redirect(url_for("auth.login"))


# ==================================================
# DÉSACTIVER LA 2FA
# ==================================================
@two_factor_bp.route("/disable", methods=["POST"])
@login_required
def disable():
    """Désactive la 2FA (nécessite le mot de passe)."""
    password = request.form.get("password") or ""
    ok, error = TotpService.disable_for_user(current_user, password)

    if ok:
        flash("La 2FA a été désactivée.", "success")
    else:
        flash(error, "danger")

    return redirect(url_for("auth.profile"))


# ==================================================
# REGÉNÉRER LES CODES DE SECOURS
# ==================================================
@two_factor_bp.route("/regenerate-backup-codes", methods=["POST"])
@login_required
def regenerate_backup_codes():
    """Regénère les codes de secours."""
    if not current_user.totp_enabled:
        flash("La 2FA doit être activée d'abord.", "warning")
        return redirect(url_for("auth.profile"))

    password = request.form.get("password") or ""
    if not current_user.check_password(password):
        flash("Mot de passe incorrect.", "danger")
        return redirect(url_for("auth.profile"))

    codes = TotpService.regenerate_backup_codes(current_user)
    session["totp_backup_codes"] = codes
    return redirect(url_for("two_factor.show_backup_codes"))