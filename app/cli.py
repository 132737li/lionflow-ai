"""
Commandes Flask CLI personnalisées.
Usage :
  flask create-admin --email admin@lionflow.ai --password secret
  flask seed-plans
  flask seed-demo
  flask send-update
"""
import click
from flask.cli import with_appcontext
from flask import current_app

from app.extensions import db
from app.models.user import User


def register_cli(app):

    @app.cli.command("create-admin")
    @click.option("--email", prompt=True)
    @click.option("--password", prompt=True, hide_input=True,
                  confirmation_prompt=True)
    @click.option("--first-name", default="Admin")
    @click.option("--last-name", default="LionFlow")
    @with_appcontext
    def create_admin(email, password, first_name, last_name):
        """Crée un compte administrateur."""
        if User.query.filter_by(email=email.lower()).first():
            click.echo(f"❌ L'utilisateur {email} existe déjà.")
            return
        user = User(
            email=email.lower(),
            first_name=first_name,
            last_name=last_name,
            role="admin",
            is_active=True,
            is_verified=True,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f"✅ Admin créé : {user.email} (id={user.id})")

    @app.cli.command("list-users")
    @with_appcontext
    def list_users():
        """Liste tous les utilisateurs."""
        for u in User.query.order_by(User.id).all():
            click.echo(f"[{u.id}] {u.email} — rôle={u.role} actif={u.is_active}")

    @app.cli.command("seed-demo")
    @with_appcontext
    def seed_demo():
        """Crée un jeu de données de démonstration (admin + entreprise)."""
        from app.models.business import Business
        from app.models.subscription import Subscription

        admin_email = "admin@lionflow.ai"
        user = User.query.filter_by(email=admin_email).first()
        if not user:
            user = User(
                email=admin_email,
                first_name="Admin",
                last_name="Demo",
                role="admin",
                is_active=True,
                is_verified=True,
            )
            user.set_password("Admin1234!")
            db.session.add(user)
            db.session.flush()
            click.echo(f"✅ Admin créé : {admin_email} / Admin1234!")

        biz = Business.query.filter_by(owner_id=user.id).first()
        if not biz:
            biz = Business(
                owner_id=user.id,
                name="Demo Company",
                email="contact@demo.com",
                phone="+33612345678",
                country="FR",
            )
            db.session.add(biz)
            db.session.flush()
            click.echo(f"✅ Business créé : {biz.name}")

        if not biz.subscription:
            sub = Subscription(
                business_id=biz.id,
                plan="free",
                status="active",
            )
            db.session.add(sub)
            click.echo("✅ Abonnement Free activé")

        db.session.commit()
        click.echo("🎉 Seed terminé.")

    # ==================================================
    # ✅ NOUVELLE COMMANDE : Envoi d'annonces / mises à jour
    # ==================================================
    @app.cli.command("send-update")
    @click.option("--title", prompt="Titre de l'annonce", help="Ex: Nouvelle fonctionnalité d'export PDF")
    @click.option("--message", prompt="Message de l'annonce", help="Détails de la mise à jour")
    @click.option("--cta-text", default="Découvrir", prompt="Texte du bouton", help="Ex: Voir les nouveautés")
    @click.option("--cta-url", default="http://localhost:5000", prompt="Lien du bouton", help="Où mène le bouton ?")
    @with_appcontext
    def send_update(title, message, cta_text, cta_url):
        """Envoie un email d'annonce de mise à jour à tous les utilisateurs actifs."""
        from app.services.email_service import EmailService
        
        users = User.query.filter_by(is_active=True).all()
        total = len(users)
        
        if total == 0:
            click.echo("❌ Aucun utilisateur actif trouvé.")
            return
            
        click.echo(f"⏳ Envoi de l'annonce '{title}' à {total} utilisateur(s)...")
        
        success = 0
        errors = 0
        
        # ✅ CORRECTION : Création d'un contexte de requête factice
        # Cela permet à render_template de fonctionner sans navigateur
        with current_app.test_request_context():
            for u in users:
                try:
                    if EmailService.send_update_notification(u, title, message, cta_text, cta_url):
                        success += 1
                    else:
                        errors += 1
                except Exception as e:
                    click.echo(f"❌ Erreur pour {u.email} : {e}")
                    errors += 1
                
        click.echo(f"\n✅ Terminé ! {success} email(s) envoyé(s) avec succès, {errors} échec(s).")