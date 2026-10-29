"""
Service d'orchestration des campagnes.
Gère les transitions de statut, la génération de messages et l'envoi.

Supporte les médias (image, PDF, vidéo).
En mode développement : l'envoi est simulé (pas d'appel réel à Meta).

✅ Émet des webhooks sortants à chaque transition.
✅ Envoie un email de rapport (avec PDF) à la fin d'une campagne.
"""

from datetime import datetime, timezone

from flask import current_app
from app.services.telegram_service import TelegramService
from app.extensions import db
from app.models import campaign
from app.models.campaign import Campaign, campaign_contacts
from app.models.contact import Contact
from app.models.message import Message
from app.models.whatsapp_account import WhatsAppAccount
from app.services.notification_service import NotificationService
from app.services import webhook_service
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

        # ✅ WEBHOOK : campaign.started
        webhook_service.notify(
            "campaign.started",
            campaign.business_id,
            campaign_id=campaign.id,
            campaign_name=campaign.name,
            total_contacts=campaign.total_contacts or 0,
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

        # ✅ WEBHOOK : campaign.paused
        webhook_service.notify(
            "campaign.paused",
            campaign.business_id,
            campaign_id=campaign.id,
            campaign_name=campaign.name,
            sent=campaign.sent_count,
            failed=campaign.failed_count,
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

        # ✅ WEBHOOK : campaign.resumed
        webhook_service.notify(
            "campaign.resumed",
            campaign.business_id,
            campaign_id=campaign.id,
            campaign_name=campaign.name,
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

        # ✅ WEBHOOK : campaign.cancelled
        webhook_service.notify(
            "campaign.cancelled",
            campaign.business_id,
            campaign_id=campaign.id,
            campaign_name=campaign.name,
            sent=campaign.sent_count,
            failed=campaign.failed_count,
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

            # ✅ WEBHOOK : campaign.completed (0 contact)
            webhook_service.notify(
                "campaign.completed",
                campaign.business_id,
                campaign_id=campaign.id,
                campaign_name=campaign.name,
                total_contacts=0,
                sent=0, delivered=0, failed=0, read=0,
            )
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
        for i, contact in enumerate(contacts):
            if contact.id in existing:
                continue
            
            # ✅ NOUVEAU : Logique A/B Testing
            if campaign.is_ab_test and campaign.message_b:
                is_variant_b = (i % 2 == 1) # Alterne A, B, A, B...
                raw_text = campaign.message_b if is_variant_b else campaign.message
            else:
                is_variant_b = False
                raw_text = campaign.message

            # Rendu du message (avec les variables {{prenom}}, etc.)
            content = CampaignService._render_message(campaign, contact, custom_text=raw_text)
            
            msg = Message(
                campaign_id=campaign.id,
                contact_id=contact.id,
                whatsapp_account_id=campaign.whatsapp_account_id,
                content=content,
                status="pending",
                is_variant_b=is_variant_b # ✅ On sauvegarde la variante
            )
            db.session.add(msg)
        db.session.commit()

        # Remplacer la partie "Envoi des messages en attente" par :
        # Envoi des messages
        pending = Message.query.filter_by(campaign_id=campaign.id, status="pending").all() # ✅ LIGNE MANQUANTE
        for msg in pending:
            db.session.refresh(campaign)
            if campaign.status != "running":
                break

            success = False
            error_msg = None
            try:
                if campaign.telegram_account:
                    # ✅ NOUVEAU : Envoi Telegram
                    result = TelegramService.send_message(
                        account=campaign.telegram_account,
                        chat_id=msg.contact.phone, # Pour Telegram, c'est le chat_id
                        text=msg.content or "",
                    )
                elif campaign.whatsapp_account:
                    # Envoi WhatsApp existant
                    result = WhatsAppService.send_text(
                        account=campaign.whatsapp_account,
                        to=msg.contact.phone,
                        text=msg.content or "",
                    )
                else:
                    result = {"success": False, "error": "Aucun canal configuré"}

                if result.get("success"):
                    msg.mark_sent(external_id=result.get("external_id"))
                    success = True
                else:
                    error_msg = result.get("error", "Erreur inconnue")
                    msg.mark_failed(error_msg)
            except Exception as e:
                error_msg = str(e)[:500]
                msg.mark_failed(error_msg)
            db.session.commit()

            # ✅ WEBHOOK : message.sent / message.failed
            try:
                if success:
                    webhook_service.notify(
                        "message.sent",
                        campaign.business_id,
                        message_id=msg.id,
                        campaign_id=campaign.id,
                        contact_id=msg.contact_id,
                        to=msg.contact.phone if msg.contact else None,
                    )
                elif error_msg:
                    webhook_service.notify(
                        "message.failed",
                        campaign.business_id,
                        message_id=msg.id,
                        campaign_id=campaign.id,
                        contact_id=msg.contact_id,
                        to=msg.contact.phone if msg.contact else None,
                        error=error_msg,
                    )
            except Exception:
                current_app.logger.exception("[campaign] Erreur notify message")

        # Recalcul & statut final
        campaign.recalc_counters()
        remaining = Message.query.filter_by(
            campaign_id=campaign.id, status="pending"
        ).count()
        
        if remaining == 0:
            campaign.status = "completed"
            campaign.finished_at = _utcnow()
            db.session.commit()

            # --- NOTIFICATION INTERNE (UI) ---
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

            # ✅ WEBHOOK : campaign.completed (toujours)
            webhook_service.notify(
                "campaign.completed",
                campaign.business_id,
                campaign_id=campaign.id,
                campaign_name=campaign.name,
                total_contacts=campaign.total_contacts,
                sent=campaign.sent_count,
                delivered=campaign.delivered_count,
                failed=campaign.failed_count,
                read=campaign.read_count,
                media_type=campaign.media_file.media_type if has_media else None,
            )

            # ✅ WEBHOOK : campaign.failed (si au moins 1 échec)
            if campaign.failed_count > 0:
                webhook_service.notify(
                    "campaign.failed",
                    campaign.business_id,
                    campaign_id=campaign.id,
                    campaign_name=campaign.name,
                    total_contacts=campaign.total_contacts,
                    failed=campaign.failed_count,
                    sent=campaign.sent_count,
                )

            # ✅ EMAIL : Envoi du rapport de campagne avec PDF au propriétaire
            try:
                from app.services.email_service import EmailService
                from app.services.campaign_pdf_service import CampaignPdfService
                
                pdf_bytes = None
                try:
                    pdf_bytes = CampaignPdfService.generate_pdf(campaign)
                except Exception:
                    current_app.logger.warning("Impossible de générer le PDF pour l'email")
                
                EmailService.send_campaign_completed(campaign, pdf_bytes=pdf_bytes)
            except Exception:
                current_app.logger.exception("[campaign] Erreur envoi email fin de campagne")

    # ==================================================
    # RENDU DU MESSAGE
    # ==================================================
    @staticmethod
    def _render_message(campaign: Campaign, contact: Contact, custom_text: str = None) -> str:
        if campaign.template and not custom_text:
            return campaign.template.render(contact)

        text = custom_text or campaign.message or ""
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
    # RELANCES AUTOMATIQUES (FOLLOW-UPS)
    # ==================================================
    @staticmethod
    def process_follow_ups() -> None:
        """Vérifie et envoie les relances pour les campagnes éligibles."""
        from datetime import timedelta
        
        now_utc = _utcnow()
        
        # Trouver les campagnes terminées avec relance activée et non encore traitées
        candidates = (
            Campaign.query
            .filter(
                Campaign.status == "completed",
                Campaign.follow_up_enabled == True,
                Campaign.follow_up_sent_at.is_(None),
                Campaign.finished_at.isnot(None)
            )
            .all()
        )

        for campaign in candidates:
            delay = timedelta(hours=campaign.follow_up_delay_hours or 24)
            if now_utc >= campaign.finished_at + delay:
                try:
                    CampaignService._send_follow_ups(campaign)
                except Exception:
                    current_app.logger.exception(
                        f"Erreur lors de l'envoi des relances pour la campagne id={campaign.id}"
                    )

    @staticmethod
    def _send_follow_ups(campaign: Campaign) -> None:
        """Envoie la relance aux contacts qui n'ont pas répondu/lu."""
        from app.services.whatsapp_service import WhatsAppService
        
        # On cible les messages envoyés ou livrés, mais PAS lus
        unread_messages = (
            Message.query
            .filter(
                Message.campaign_id == campaign.id,
                Message.status.in_(["sent", "delivered"]),
                Message.is_follow_up == False
            )
            .all()
        )

        if not unread_messages:
            campaign.follow_up_sent_at = _utcnow()
            db.session.commit()
            return

        # Rendu du message de relance
        for msg in unread_messages:
            content = ""
            # Si un template de relance est défini
            if campaign.follow_up_template:
                content = campaign.follow_up_template.render(msg.contact)
            # Sinon on utilise le message texte de relance
            elif campaign.follow_up_message:
                content = campaign.follow_up_message
                replacements = {
                    "{{prenom}}": msg.contact.first_name or "",
                    "{{nom}}": msg.contact.last_name or "",
                    "{{entreprise}}": msg.contact.company or (campaign.business.name if campaign.business else ""),
                }
                for k, v in replacements.items():
                    content = content.replace(k, v)
            
            if not content.strip():
                continue

            # Créer un nouveau message (marqué comme relance)
            follow_up_msg = Message(
                campaign_id=campaign.id,
                contact_id=msg.contact_id,
                whatsapp_account_id=campaign.whatsapp_account_id,
                content=content,
                status="pending",
                is_follow_up=True
            )
            db.session.add(follow_up_msg)
            db.session.flush() # Pour avoir l'ID

            try:
                # Envoi via WhatsApp Service
                result = WhatsAppService.send_text(
                    account=campaign.whatsapp_account,
                    to=msg.contact.phone,
                    text=content,
                )
                if result.get("success"):
                    follow_up_msg.mark_sent(external_id=result.get("external_id"))
                else:
                    follow_up_msg.mark_failed(result.get("error", "Erreur inconnue"))
            except Exception as e:
                follow_up_msg.mark_failed(str(e)[:500])
            
            db.session.commit()

        # Marquer la campagne comme "relancée"
        campaign.follow_up_sent_at = _utcnow()
        db.session.commit()
        
        current_app.logger.info(f"Relances envoyées pour la campagne id={campaign.id} ({len(unread_messages)} contacts).")

    # ==================================================
    # TRAITEMENT AUTOMATIQUE (scheduler)
    # ==================================================
    @staticmethod
    def process_due_campaigns() -> None:
            """Appelé périodiquement par le scheduler."""
            now_utc = _utcnow()

            # 1. Démarrage des campagnes planifiées
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
                if not c.target_contacts.count() and not c.total_contacts:
                    c.status = "cancelled"
                    db.session.commit()
                    continue
                try:
                    CampaignService.start(c)
                except Exception:
                    current_app.logger.exception(f"Erreur démarrage campagne planifiée id={c.id}")

            # 2. Reprise des campagnes 'running' interrompues
            running = Campaign.query.filter_by(status="running").all()
            for c in running:
                pending_count = Message.query.filter_by(campaign_id=c.id, status="pending").count()
                if pending_count > 0:
                    try:
                        CampaignService._process(c)
                    except Exception:
                        current_app.logger.exception(f"Erreur reprise campagne id={c.id}")

            # 3. ✅ NOUVEAU : Traitement des relances automatiques
            try:
                CampaignService.process_follow_ups()
            except Exception:
                current_app.logger.exception("Erreur traitement des relances automatiques")