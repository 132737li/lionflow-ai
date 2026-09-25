"""
Point d'entrée de LionFlow AI.
Usage : python run.py
"""
import os
from app import create_app
from app.extensions import db
from app.scheduler import init_scheduler

app = create_app(os.getenv("FLASK_ENV", "development"))

# Démarre le scheduler si activé (uniquement en dev / monoprocess)
if app.config.get("SCHEDULER_ENABLED") and not app.config.get("TESTING"):
    init_scheduler(app)


if __name__ == "__main__":
    with app.app_context():
        # En dev, on peut créer les tables automatiquement si besoin
        # (en prod, utiliser flask db upgrade)
        if app.config.get("DEBUG"):
            db.create_all()

    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000")),
        debug=app.config.get("DEBUG", False),
        use_reloader=app.config.get("DEBUG", False),
    )