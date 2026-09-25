# 🦁 LionFlow AI

**Plateforme SaaS de gestion et d'automatisation des communications WhatsApp.**

LionFlow AI permet aux entreprises de gérer leurs contacts, créer des campagnes WhatsApp, programmer des envois, suivre les livraisons et gérer leur abonnement — le tout depuis une interface moderne et sécurisée.

---

## 📋 Table des matières

1. [Présentation](#présentation)
2. [Prérequis](#prérequis)
3. [Installation](#installation)
4. [Configuration](#configuration)
5. [Base de données](#base-de-données)
6. [Lancement](#lancement)
7. [Utilisation de l'API](#utilisation-de-lapi)
8. [Tests](#tests)
9. [Configuration WhatsApp Cloud API](#configuration-whatsapp-cloud-api)
10. [Configuration Stripe](#configuration-stripe)
11. [Structure du projet](#structure-du-projet)
12. [Sécurité](#sécurité)
13. [Déploiement](#déploiement)

---

## 🎯 Présentation

### Fonctionnalités principales

- **Authentification sécurisée** : inscription, connexion, mot de passe oublié, rôles (admin/user)
- **Gestion multi-entreprises** : un utilisateur peut posséder plusieurs entreprises
- **Contacts** : CRUD, recherche, filtres, import CSV/Excel avec rapport détaillé
- **Modèles de messages** : variables dynamiques (`{{prenom}}`, `{{nom}}`, `{{entreprise}}`)
- **Campagnes WhatsApp** : ciblage de contacts, programmation (date/heure/fuseau), statuts complets
- **Messages** : suivi individuel (pending → sent → delivered → read / failed)
- **Comptes WhatsApp Cloud API** : multi-comptes, tokens chiffrés, webhook Meta
- **Abonnements** : plans Free / Pro / Business avec quotas configurables
- **Paiements** : Stripe Checkout + simulateur dev
- **Notifications** : temps réel, filtrables par type
- **API REST complète** : JWT, format unifié, documentation `API.md`
- **Journal d'activité** : audit de toutes les actions

### Stack technique

| Couche | Technologie |
|---|---|
| Backend | Python 3.12+, Flask 3, SQLAlchemy, Flask-Migrate |
| Base de données | MySQL 8 (SQLite pour les tests) |
| Auth | Flask-Login (web), Flask-JWT-Extended (API), bcrypt |
| Frontend | Jinja2, Bootstrap 5, Chart.js |
| Import | Pandas, openpyxl |
| Tâches async | APScheduler (dev) → Celery + Redis (prod) |
| Paiement | Stripe |
| Tests | pytest |

---

## ⚙️ Prérequis

- **Python** 3.12 ou supérieur : [python.org](https://www.python.org/downloads/)
- **MySQL** 8.0 ou supérieur : [mysql.com](https://dev.mysql.com/downloads/)
- **pip** (fourni avec Python)
- **git** (optionnel)
- Un éditeur (VS Code recommandé)

### Vérifier les versions

```bash
python --version   # Python 3.12.x
mysql --version    # mysql Ver 8.x
```

---

## 🚀 Installation

### 1. Récupérer le projet

```bash
git clone <votre-repo> lionflow-ai
cd lionflow-ai
```

Ou créez manuellement le dossier et copiez les fichiers.

### 2. Créer un environnement virtuel

**Linux / macOS** :

```bash
python3 -m venv venv
source venv/bin/activate
```

**Windows PowerShell** :

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**Windows CMD** :

```cmd
python -m venv venv
venv\Scripts\activate.bat
```

### 3. Installer les dépendances

```bash
pip install -r requirements.txt
```

---

## 🔧 Configuration

### 1. Créer le fichier `.env`

```bash
cp .env.example .env
```

### 2. Éditer `.env`

Remplissez au minimum :

```env
SECRET_KEY=<chaîne aléatoire de 50+ caractères>
JWT_SECRET_KEY=<autre chaîne aléatoire>

DATABASE_URL=mysql+pymysql://lionflow_user:VOTRE_MDP@localhost:3306/lionflow_ai
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_DATABASE=lionflow_ai
MYSQL_USER=lionflow_user
MYSQL_PASSWORD=VOTRE_MDP
```

Pour générer une clé aléatoire :

```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

---

## 🗄️ Base de données

### 1. Créer la base et l'utilisateur MySQL

```bash
mysql -u root -p < schema.sql
```

Ou manuellement :

```sql
CREATE DATABASE lionflow_ai CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'lionflow_user'@'localhost' IDENTIFIED BY 'VOTRE_MDP';
GRANT ALL PRIVILEGES ON lionflow_ai.* TO 'lionflow_user'@'localhost';
FLUSH PRIVILEGES;
```

### 2. Initialiser Alembic

```bash
flask db init
```

### 3. Créer la première migration

```bash
flask db migrate -m "initial schema"
```

### 4. Appliquer la migration

```bash
flask db upgrade
```

### 5. Créer un compte administrateur

**Option A — Commande dédiée :**

```bash
flask create-admin --email admin@lionflow.ai --password VotreMotDePasse123
```

**Option B — Jeu de démonstration complet :**

```bash
flask seed-demo
# Crée admin@lionflow.ai / Admin1234! + une entreprise + abonnement
```

---

## 🏃 Lancement

### Démarrage simple

```bash
python run.py
```

Le serveur démarre sur **http://localhost:5000**

### Démarrage avec scripts utilitaires

**Linux/macOS** :

```bash
chmod +x run_dev.sh
./run_dev.sh
```

**Windows PowerShell** :

```powershell
.\run_dev.ps1
```

### Avec le Makefile

```bash
make install     # Dépendances
make upgrade     # Migrations
make seed        # Données démo
make run         # Lancer
make test        # Tests
```

---

## 🔌 Utilisation de l'API

Base URL : `http://localhost:5000/api`

### Authentification

```bash
# 1. S'inscrire
curl -X POST http://localhost:5000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@exemple.com",
    "password": "Password123",
    "first_name": "Jean",
    "last_name": "Dupont"
  }'

# 2. Se connecter pour obtenir un token
curl -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "user@exemple.com", "password": "Password123"}'
```

La réponse contient `data.access_token`. Utilisez-le :

```bash
TOKEN="eyJ..."
curl http://localhost:5000/api/contacts \
  -H "Authorization: Bearer $TOKEN"
```

### Format de réponse

```json
{
  "success": true,
  "message": "OK",
  "data": { ... },
  "errors": []
}
```

### Documentation complète

Voir [`API.md`](./API.md) pour tous les endpoints.

---

## 🧪 Tests

### Lancer tous les tests

```bash
pytest
```

### Avec couverture

```bash
pytest --cov=app --cov-report=html
# Ouvre htmlcov/index.html
```

### Tests spécifiques

```bash
pytest tests/test_auth.py -v
pytest tests/test_api.py::TestAPIContacts::test_create_contact -v
```

### Ce qui est testé

- ✅ Inscription, connexion, déconnexion
- ✅ Changement et réinitialisation de mot de passe
- ✅ CRUD contacts complet
- ✅ CRUD campagnes + transitions de statut
- ✅ Isolation multi-tenant (aucune fuite de données)
- ✅ Tous les endpoints REST (JWT, format, pagination)
- ✅ Import CSV (avec détection colonnes françaises)
- ✅ Permissions et quotas du plan

---

## 📱 Configuration WhatsApp Cloud API

### 1. Créer une app Meta

1. Aller sur [developers.facebook.com/apps](https://developers.facebook.com/apps)
2. Créer une app **Business**
3. Ajouter le produit **WhatsApp**

### 2. Récupérer les identifiants

Dans **WhatsApp → API Setup** :
- **Phone Number ID** → `WHATSAPP_PHONE_NUMBER_ID`
- **WhatsApp Business Account ID** → `WHATSAPP_BUSINESS_ACCOUNT_ID`
- **Access Token** (permanent recommandé) → `WHATSAPP_ACCESS_TOKEN`

### 3. Configurer `.env`

```env
WHATSAPP_ACCESS_TOKEN=EAAxxxxx
WHATSAPP_PHONE_NUMBER_ID=123456789
WHATSAPP_BUSINESS_ACCOUNT_ID=987654321
WHATSAPP_VERIFY_TOKEN=lionflow-verify-token
WHATSAPP_API_VERSION=v20.0
WHATSAPP_DEV_MODE=0   # 1 pour simuler en dev
```

### 4. Configurer le webhook

Exposez votre serveur local :

```bash
ngrok http 5000
```

Dans **WhatsApp → Configuration → Webhook** :
- **URL** : `https://VOTRE_NGROK.ngrok.io/whatsapp/webhook`
- **Verify Token** : valeur de `WHATSAPP_VERIFY_TOKEN`
- **Champs abonnés** : `messages`

### 5. Mode développement (sans clé)

```env
WHATSAPP_DEV_MODE=1
```

Les envois sont **simulés** et enregistrés comme réussis. Parfait pour tester sans compte Meta.

---

## 💳 Configuration Stripe

### 1. Créer un compte Stripe (mode Test)

[stripe.com](https://stripe.com) → Developers → API keys

### 2. Configurer `.env`

```env
STRIPE_SECRET_KEY=sk_test_XXXXX
STRIPE_PUBLISHABLE_KEY=pk_test_XXXXX
STRIPE_WEBHOOK_SECRET=whsec_XXXXX
```

### 3. Tester les webhooks localement

```bash
stripe listen --forward-to localhost:5000/payments/webhook
```

### 4. Mode dev sans Stripe

Si `STRIPE_SECRET_KEY` est vide, LionFlow AI utilise automatiquement le **simulateur de paiement** : le clic sur "Passer à Pro" redirige vers une page qui active immédiatement le plan.

---

## 📁 Structure du projet

```
lionflow-ai/
├── app/
│   ├── __init__.py               # App factory
│   ├── extensions.py             # db, jwt, bcrypt, csrf, login_manager
│   ├── errors.py                 # Handlers d'erreurs
│   ├── cli.py                    # Commandes Flask CLI
│   ├── scheduler.py              # APScheduler
│   ├── models/                   # 12 modèles SQLAlchemy
│   ├── routes/                   # 11 blueprints UI
│   ├── api/                      # 12 blueprints API REST
│   ├── services/                 # 8 services métier
│   ├── forms/                    # Formulaires WTForms
│   ├── utils/                    # Helpers (décorateurs, validators, etc.)
│   ├── templates/                # Templates Jinja2
│   └── static/                   # CSS, JS, images
├── migrations/                   # Alembic
├── tests/                        # Tests pytest
├── config.py                     # Config multi-env
├── run.py                        # Point d'entrée
├── requirements.txt
├── schema.sql                    # DDL MySQL + utilisateur
├── .env.example
├── .gitignore
├── API.md                        # Doc API REST
├── Makefile                      # Raccourcis dev
├── run_dev.sh / run_dev.ps1      # Démarrage rapide
└── README.md
```

---

## 🔒 Sécurité

- ✅ **Hashage bcrypt** des mots de passe
- ✅ **CSRF** via Flask-WTF sur toutes les routes UI
- ✅ **JWT** signés avec `JWT_SECRET_KEY` pour l'API
- ✅ **Protection SQL Injection** : SQLAlchemy ORM partout
- ✅ **XSS** : échappement automatique Jinja2
- ✅ **Tokens WhatsApp chiffrés** Fernet (AES-128 + HMAC-SHA256)
- ✅ **Tokens de reset MDP** hashés SHA-256 + TTL 60 min
- ✅ **Anti-énumération d'emails** (messages uniformes)
- ✅ **Multi-tenant strict** : aucune fuite inter-business
- ✅ **Quotas du plan** vérifiés à chaque création
- ✅ **Journal d'audit** complet (`logs`)
- ✅ **Validation stricte** (email, téléphone E.164, uploads)
- ✅ **Limites d'upload** (`MAX_CONTENT_LENGTH`)
- ✅ **Webhook Meta** avec vérification HMAC optionnelle

---

## 🌍 Déploiement

### Recommandations production

| Aspect | Recommandation |
|---|---|
| Serveur WSGI | Gunicorn : `gunicorn -w 4 -b 0.0.0.0:8000 run:app` |
| Reverse proxy | Nginx avec HTTPS (Let's Encrypt) |
| Base de données | MySQL managé (RDS, PlanetScale…) avec sauvegardes |
| Sessions | Redis pour Flask-Session |
| Tâches async | Celery + Redis (remplacer APScheduler) |
| Fichiers statiques | Nginx ou CDN |
| Logs | Sentry + fichiers rotatifs |
| Monitoring | Prometheus + Grafana (optionnel) |
| CI/CD | GitHub Actions ou GitLab CI |

### Variables d'environnement à changer

```env
FLASK_ENV=production
FLASK_DEBUG=0
SESSION_COOKIE_SECURE=True
REMEMBER_COOKIE_SECURE=True
WHATSAPP_DEV_MODE=0
```

### Exemple de service systemd

```ini
[Unit]
Description=LionFlow AI
After=network.target mysql.service

[Service]
User=lionflow
WorkingDirectory=/var/www/lionflow-ai
Environment="PATH=/var/www/lionflow-ai/venv/bin"
ExecStart=/var/www/lionflow-ai/venv/bin/gunicorn -w 4 -b 127.0.0.1:8000 run:app
Restart=always

[Install]
WantedBy=multi-user.target
```

---

## 🤝 Contribution

Les PRs sont bienvenues. Pour les changements majeurs, ouvrez d'abord une issue.

## 📄 Licence

MIT — voir le fichier LICENSE.

## 🆘 Support

- Documentation API : [`API.md`](./API.md)
- Issues : ouvrir une issue GitHub
- Email : support@lionflow.ai

---

**Fait avec 🦁 par l'équipe LionFlow AI**