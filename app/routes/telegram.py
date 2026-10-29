"""
Routes UI pour la gestion des Bots Telegram.
"""
import requests
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required

from app.extensions import db
from app.models.telegram_account import TelegramAccount
from app.utils.decorators import require_business, get_current_business
from app.utils.security import log_activity

telegram_bp = Blueprint("telegram", __name__, template_folder="../templates/telegram")

@telegram_bp.route("/")
@login_required
@require_business
def list_accounts():
    business = get_current_business()
    accounts = TelegramAccount.query.filter_by(business_id=business.id).order_by(TelegramAccount.created_at.desc()).all()
    return render_template("telegram/list.html", accounts=accounts, business=business)

@telegram_bp.route("/new", methods=["GET", "POST"])
@login_required
@require_business
def create_account():
    business = get_current_business()
    
    if request.method == "POST":
        name = request.form.get("name")
        token = request.form.get("bot_token")
        
        if not name or not token:
            flash("Tous les champs sont requis.", "danger")
            return redirect(url_for("telegram.create_account"))

        try:
            res = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10).json()
            if not res.get("ok"):
                flash("Token invalide. Vérifiez le token fourni par BotFather.", "danger")
                return redirect(url_for("telegram.create_account"))
            username = res["result"]["username"]
        except Exception:
            flash("Impossible de contacter les serveurs Telegram. Vérifiez le token.", "danger")
            return redirect(url_for("telegram.create_account"))

        account = TelegramAccount(business_id=business.id, name=name, bot_username=username)
        account.set_bot_token(token)
        db.session.add(account)
        db.session.commit()

        log_activity(action="telegram_add", description=f"Bot Telegram ajouté : @{username}")
        flash(f"Bot Telegram @{username} ajouté avec succès !", "success")
        return redirect(url_for("telegram.list_accounts"))

    return render_template("telegram/form.html", account=None)

@telegram_bp.route("/<int:account_id>/delete", methods=["POST"])
@login_required
@require_business
def delete_account(account_id):
    business = get_current_business()
    account = TelegramAccount.query.filter_by(id=account_id, business_id=business.id).first_or_404()
    
    username = account.bot_username
    db.session.delete(account)
    db.session.commit()
    
    log_activity(action="telegram_delete", description=f"Bot Telegram supprimé : @{username}")
    flash(f"Bot @{username} supprimé.", "info")
    return redirect(url_for("telegram.list_accounts"))