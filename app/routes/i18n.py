"""Routes pour changer la langue."""
from flask import Blueprint, redirect, request, flash
from flask_login import current_user

from app.i18n import I18nService, LANGUAGES


i18n_bp = Blueprint("i18n", __name__, url_prefix="/i18n")


@i18n_bp.route("/set/<lang>")
def set_language(lang: str):
    """Change la langue active et redirige."""
    referrer = request.referrer or "/"

    if lang not in LANGUAGES:
        flash("Langue non supportée.", "warning")
        return redirect(referrer)

    if I18nService.set_language(lang):
        name = LANGUAGES[lang]["name"]
        flash(f"Langue changée : {name}", "success")

    return redirect(referrer)