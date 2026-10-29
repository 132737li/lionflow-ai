from flask import Blueprint, render_template, redirect, url_for
from flask_login import current_user

landing_bp = Blueprint("landing", __name__)

@landing_bp.route("/")
def index():
    # ✅ Si l'utilisateur est déjà connecté, on l'envoie vers le dashboard
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))
    
    # ✅ Sinon, on affiche la landing page
    return render_template("landing/index.html")