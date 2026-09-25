
---

## 2️⃣ `Makefile` (à la racine du projet)

⚠️ **Important** : le Makefile utilise des **tabulations** (Tab) pour l'indentation, pas des espaces. Si tu copies-colles depuis le navigateur, tu risques de perdre les tabulations. Vérifie avec un éditeur comme VS Code qu'il y a bien des `→` (tabulations) au début des lignes de commandes.

```makefile
# LionFlow AI — Raccourcis de développement
.PHONY: help install install-dev init-db migrate upgrade run shell test test-cov lint clean seed reset

help:
	@echo "Commandes disponibles :"
	@echo "  make install      Installer les dépendances"
	@echo "  make init-db      Initialiser Alembic"
	@echo "  make migrate      Générer une migration"
	@echo "  make upgrade      Appliquer les migrations"
	@echo "  make run          Lancer le serveur"
	@echo "  make shell        Ouvrir un shell Flask"
	@echo "  make test         Lancer les tests"
	@echo "  make test-cov     Tests + couverture HTML"
	@echo "  make seed         Jeu de données démo"
	@echo "  make clean        Nettoyer les fichiers temporaires"

install:
	pip install -r requirements.txt

init-db:
	flask db init

migrate:
	flask db migrate -m "auto"

upgrade:
	flask db upgrade

run:
	python run.py

shell:
	flask shell

test:
	pytest -v

test-cov:
	pytest --cov=app --cov-report=html --cov-report=term

seed:
	flask seed-demo

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache .coverage htmlcov/ 2>/dev/null || true