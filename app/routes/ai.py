"""
Routes de configuration IA du chatbot.
"""
from flask import (
    Blueprint, render_template, redirect, url_for, flash,
    request, jsonify,
)
from flask_login import login_required, current_user

from app.extensions import db
from app.forms.ai_forms import AiConfigForm, MODEL_PRESETS
from app.models.ai_config import AiConfig
from app.services.ai_service import AiService, DEFAULT_SYSTEM_PROMPT
from app.utils.decorators import require_business, get_current_business
from app.utils.security import log_activity


ai_bp = Blueprint("ai", __name__, url_prefix="/ai", template_folder="../templates/ai")


# ==================================================
# PAGE DE CONFIGURATION
# ==================================================
@ai_bp.route("/", methods=["GET", "POST"])
@login_required
@require_business
def settings():
    business = get_current_business()
    config = AiService.get_or_create_config(business)

    form = AiConfigForm(obj=config)

    # Valeurs par défaut à la création
    if request.method == "GET":
        if not config.system_prompt:
            form.system_prompt.data = DEFAULT_SYSTEM_PROMPT.replace(
                "{business_name}", business.name or "notre entreprise"
            )
        form.api_key.data = ""  # Ne jamais pré-remplir

    if form.validate_on_submit():
        # Mise à jour
        config.is_enabled = bool(form.is_enabled.data)
        config.provider = form.provider.data
        config.model_name = (form.model_name.data or "").strip() or None
        config.api_base_url = (form.api_base_url.data or "").strip() or None
        config.system_prompt = (form.system_prompt.data or "").strip() or None
        config.context = (form.context.data or "").strip() or None
        config.temperature = float(form.temperature.data or 0.7)
        config.max_tokens = int(form.max_tokens.data or 300)
        config.reply_language = form.reply_language.data or "auto"
        config.max_requests_per_month = int(form.max_requests_per_month.data or 1000)

        # Mettre à jour la clé uniquement si fournie
        if form.api_key.data:
            config.set_api_key(form.api_key.data)

        # Reset erreur si tout va bien
        config.last_error = None

        db.session.commit()

        log_activity(
            action="ai_config_update",
            description=(
                f"Config IA mise à jour : {config.provider} "
                f"({'activée' if config.is_enabled else 'désactivée'})"
            ),
        )
        flash("Configuration IA enregistrée.", "success")
        return redirect(url_for("ai.settings"))

    return render_template(
        "ai/settings.html",
        business=business,
        config=config,
        form=form,
        model_presets=MODEL_PRESETS,
        default_prompt=DEFAULT_SYSTEM_PROMPT,
    )


# ==================================================
# TEST DE CONNEXION
# ==================================================
@ai_bp.route("/test", methods=["POST"])
@login_required
@require_business
def test_connection():
    business = get_current_business()
    config = AiConfig.query.filter_by(business_id=business.id).first()

    if not config:
        return jsonify(success=False, message="Aucune configuration trouvée."), 404

    result = AiService.test_connection(config)

    log_activity(
        action="ai_test",
        description=(
            f"Test IA ({config.provider}) : "
            f"{'succès' if result['success'] else 'échec'}"
        ),
    )

    return jsonify(
        success=result["success"],
        message=result.get("message") or result.get("error") or "",
        error=result.get("error"),
    )


# ==================================================
# RESET DU QUOTA
# ==================================================
@ai_bp.route("/reset-quota", methods=["POST"])
@login_required
@require_business
def reset_quota():
    business = get_current_business()
    config = AiConfig.query.filter_by(business_id=business.id).first()

    if not config:
        flash("Aucune configuration IA.", "warning")
        return redirect(url_for("ai.settings"))

    config.reset_monthly_quota()
    db.session.commit()

    log_activity(
        action="ai_quota_reset",
        description="Quota IA mensuel remis à zéro",
    )
    flash("Quota IA remis à zéro.", "success")
    return redirect(url_for("ai.settings"))