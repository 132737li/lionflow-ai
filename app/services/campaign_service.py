"""
Service d'orchestration des campagnes.
Gère les transitions de statut, la génération de messages et l'envoi.

Supporte les médias (image, PDF, vidéo).
En mode développement : l'envoi est simulé (pas d'appel réel à Meta).
"""
from datetime import datetime, timezone

from flask import current_app

from app.extensions import db
from app.models.campaign import Campaign, campaign_contacts
from app.models.contact import Contact
from app.models.message import Message
from app.models.whatsapp_account import WhatsAppAccount
from app.services.notification_service import NotificationService
from app.utils.security import log_activity


def _utcnow():
    """Heure UTC naïve (compatible MySQL DATETIME)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class CampaignService:

    # ==================================================
    # TRANSITIONS DE STATUT
    # ==================================================
    @staticmethod
    def start(campaign: Campaign) -> None:
        """Démarre une campagne (draft, scheduled ou paused)."""
        if campaign.status not in ("draft", "scheduled", "paused"):
            raise ValueError(
                f"Impossible de démarrer une campagne au statut '{campaign.status}'."
            )

        if not campaign.whatsapp_account:
            raise ValueError("Aucun compte WhatsApp associé à cette campagne.")

        if not campaign.target_contacts.count() and not campaign.total_contacts:
            raise ValueError("Aucun contact ciblé par cette campagne.")

        campaign.status = "running"
        campaign.started_at = _utcnow()
        db.session.commit()

        log_activity(
            action="campaign_start",
            description=f"Campagne lancée : {campaign.name} (id={campaign.id})",
            user_id=campaign.business.owner_id,
        )

        try:
            CampaignService._process(campaign)
        except Exception as e:
            current_app.logger.exception("Erreur exécution campagne")
            campaign.status = "paused"
            db.session.commit()
            raise ValueError(f"Erreur lors de l'exécution : {e}")

    @staticmethod
    def pause(campaign: Campaign) -> None:
        if campaign.status != "running":
            raise ValueError("Seule une campagne en cours peut être mise en pause.")
        campaign.status = "paused"
        db.session.commit()
        log_activity(
            action="campaign_pause",
            description=f"Campagne mise en pause : {campaign.name}",
            user_id=campaign.business.owner_id,
        )

    @staticmethod
    def resume(campaign: Campaign) -> None:
        if campaign.status != "paused":
            raise ValueError("Seule une campagne en pause peut être reprise.")
        campaign.status = "running"
        db.session.commit()
        log_activity(
            action="campaign_resume",
            description=f"Campagne reprise : {campaign.name}",
            user_id=campaign.business.owner_id,
        )
        try:
            CampaignService._process(campaign)
        except Exception as e:
            current_app.logger.exception("Erreur reprise campagne")
            campaign.status = "paused"
            db.session.commit()
            raise ValueError(f"Erreur lors de la reprise : {e}")

    @staticmethod
    def cancel(campaign: Campaign) -> None:
        if campaign.status in ("completed", "cancelled"):
            raise ValueError("Cette campagne est déjà terminée ou annulée.")
        campaign.status = "cancelled"
        campaign.finished_at = _utcnow()
        db.session.commit()
        log_activity(
            action="campaign_cancel",
            description=f"Campagne annulée : {campaign.name}",
            user_id=campaign.business.owner_id,
        )

    # ==================================================
    # CŒUR : GÉNÉRATION ET ENVOI
    # ==================================================
    @staticmethod
    def _process(campaign: Campaign) -> None:
        from app.services.whatsapp_service import WhatsAppService

        # Récupérer les contacts ciblés
        contact_ids = [
            row[0] for row in
            db.session.query(campaign_contacts.c.contact_id)
            .filter(campaign_contacts.c.campaign_id == campaign.id)
            .all()
        ]
        contacts = Contact.query.filter(Contact.id.in_(contact_ids)).all() if contact_ids else []

        if not contacts:
            campaign.status = "completed"
            campaign.finished_at = _utcnow()
            db.session.commit()
            return

        campaign.total_contacts = len(contacts)

        # Messages existants indexés par contact
        existing = {
            m.contact_id: m for m in
            Message.query.filter_by(campaign_id=campaign.id).all()
        }

        # 📎 Vérifier si la campagne a un média
        has_media = campaign.media_file_id is not None and campaign.media_file is not None
        media_info = ""
        if has_media:
            media_info = f" [{campaign.media_file.media_type.upper()}]"

        # Création des messages manquants
        for contact in contacts:
            if contact.id in existing:
                continue
            content = CampaignService._render_message(campaign, contact)
            msg = Message(
                campaign_id=campaign.id,
                contact_id=contact.id,
                whatsapp_account_id=campaign.whatsapp_account_id,
                content=content,
                status="pending",
            )
            db.session.add(msg)
        db.session.commit()

        # Envoi des messages en attente
        pending = (
            Message.query
            .filter_by(campaign_id=campaign.id, status="pending")
            .all()
        )
        for msg in pending:
            # Si la campagne a été mise en pause entre-temps → on stoppe
            db.session.refresh(campaign)
            if campaign.status != "running":
                break

            try:
                # 📎 Si la campagne a un média → envoyer le média
                if has_media:
                    result = WhatsAppService.send_media(
                        account=campaign.whatsapp_account,
                        to=msg.contact.phone,
                        media_file=campaign.media_file,
                        caption=msg.content or "",
                    )
                else:
                    # Sinon → message texte classique
                    result = WhatsAppService.send_text(
                        account=campaign.whatsapp_account,
                        to=msg.contact.phone,
                        text=msg.content or "",
                    )

                if result.get("success"):
                    msg.mark_sent(external_id=result.get("external_id"))
                else:
                    msg.mark_failed(result.get("error", "Erreur inconnue"))
            except Exception as e:
                msg.mark_failed(str(e)[:500])
            db.session.commit()

        # Recalcul & statut final
        campaign.recalc_counters()
        remaining = Message.query.filter_by(
            campaign_id=campaign.id, status="pending"
        ).count()
        if remaining == 0:
            campaign.status = "completed"
            campaign.finished_at = _utcnow()
            db.session.commit()

            notif_msg = (
                f"La campagne « {campaign.name} »{media_info} est terminée : "
                f"{campaign.sent_count} envoyés, "
                f"{campaign.failed_count} échecs."
            )

            NotificationService.notify(
                user_id=campaign.business.owner_id,
                title="Campagne terminée",
                message=notif_msg,
                type="success" if campaign.failed_count == 0 else "warning",
                link=f"/campaigns/{campaign.id}",
            )

    # ==================================================
    # RENDU DU MESSAGE
    # ==================================================
    @staticmethod
    def _render_message(campaign: Campaign, contact: Contact) -> str:
        """Retourne le contenu final : via template ou message brut."""
        if campaign.template:
            return campaign.template.render(contact)
        # Message brut avec substitutions
        text = campaign.message or ""
        replacements = {
            "{{prenom}}": contact.first_name or "",
            "{{nom}}": contact.last_name or "",
            "{{entreprise}}": contact.company or (campaign.business.name if campaign.business else ""),
            "{{telephone}}": contact.phone or "",
            "{{email}}": contact.email or "",
        }
        for k, v in replacements.items():
            text = text.replace(k, v)
        return text

    # ==================================================
    # TRAITEMENT AUTOMATIQUE (scheduler)
    # ==================================================
    @staticmethod
    def process_due_campaigns() -> None:
        """
        Appelé périodiquement par le scheduler.
        Démarre les campagnes programmées dont l'heure est arrivée.
        Reprend les campagnes 'running' interrompues.
        """
        # ⚠️ MySQL stocke des DATETIME naïfs → on retire le tzinfo
        now_utc = _utcnow()

        # Campagnes programmées dont l'heure est passée
        due = (
            Campaign.query
            .filter(
                Campaign.status == "scheduled",
                Campaign.scheduled_at.isnot(None),
                Campaign.scheduled_at <= now_utc,
            )
            .all()
        )
        for c in due:
            try:
                CampaignService.start(c)
            except Exception:
                current_app.logger.exception(
                    f"Erreur démarrage campagne planifiée id={c.id}"
                )

        # Campagnes 'running' avec messages en attente (reprise)
        running = Campaign.query.filter_by(status="running").all()
        for c in running:
            pending_count = Message.query.filter_by(
                campaign_id=c.id, status="pending"
            ).count()
            if pending_count > 0:
                try:
                    CampaignService._process(c)
                except Exception:
                    current_app.logger.exception(
                        f"Erreur reprise campagne id={c.id}"
                    )