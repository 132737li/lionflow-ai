"""
Service de notifications.
Crée des notifications utilisateur liées à différents événements.
Envoie également des notifications push PWA si configuré.
"""
from flask import current_app

from app.extensions import db
from app.models.notification import Notification


class NotificationService:

    # ==================================================
    # CRÉER UNE NOTIFICATION
    # ==================================================
    @staticmethod
    def notify(
        user_id: int,
        title: str,
        message: str = "",
        type: str = "info",
        link: str | None = None,
        send_push: bool = True,
    ) -> Notification:
        """
        Crée une notification interne + envoie un push si possible.

        Args:
            user_id : ID de l'utilisateur
            title : Titre de la notification
            message : Contenu
            type : 'success', 'info', 'warning', 'error'
            link : URL vers laquelle rediriger au clic (ex: '/campaigns/5')
            send_push : Si True, envoie aussi une notification push PWA

        Returns:
            L'objet Notification créé
        """
        # Valider le type
        if type not in ("success", "info", "warning", "error"):
            type = "info"

        # 1. Créer la notification interne
        notif = Notification(
            user_id=user_id,
            title=title[:200],
            message=(message or "")[:2000],
            type=type,
            link=link,
        )
        db.session.add(notif)
        db.session.commit()

        # 2. Envoyer une notification push (non bloquant)
        if send_push:
            NotificationService._send_push_safely(
                user_id=user_id,
                title=title,
                body=message or title,
                url=link or "/",
            )

        return notif

    # ==================================================
    # ENVOI PUSH SÉCURISÉ (ne bloque jamais)
    # ==================================================
    @staticmethod
    def _send_push_safely(user_id: int, title: str, body: str, url: str) -> int:
        """
        Envoie une notification push sans jamais lever d'exception.
        Retourne le nombre de notifications envoyées (ou 0).
        """
        try:
            from app.services.push_service import PushService
            count = PushService.send_to_user(
                user_id=user_id,
                title=title,
                body=body,
                url=url,
            )
            if count > 0:
                current_app.logger.info(
                    f"[Push] {count} notification(s) envoyée(s) à user {user_id}"
                )
            return count
        except Exception as e:
            # Ne jamais bloquer la création de notification
            try:
                current_app.logger.warning(
                    f"[Push] Échec d'envoi pour user {user_id} : {e}"
                )
            except Exception:
                pass
            return 0

    # ==================================================
    # MARQUER COMME LU
    # ==================================================
    @staticmethod
    def mark_all_read(user_id: int) -> int:
        """Marque toutes les notifications non lues comme lues."""
        count = (
            Notification.query
            .filter_by(user_id=user_id, is_read=False)
            .update({"is_read": True})
        )
        db.session.commit()
        return count

    @staticmethod
    def mark_read(notification_id: int, user_id: int) -> bool:
        """Marque une notification spécifique comme lue."""
        notif = Notification.query.filter_by(
            id=notification_id, user_id=user_id
        ).first()
        if not notif:
            return False
        notif.mark_read()
        db.session.commit()
        return True

    # ==================================================
    # COMPTEURS
    # ==================================================
    @staticmethod
    def unread_count(user_id: int) -> int:
        """Nombre de notifications non lues."""
        return Notification.query.filter_by(
            user_id=user_id, is_read=False
        ).count()

    # ==================================================
    # SUPPRESSION
    # ==================================================
    @staticmethod
    def delete(notification_id: int, user_id: int) -> bool:
        """Supprime une notification."""
        notif = Notification.query.filter_by(
            id=notification_id, user_id=user_id
        ).first()
        if not notif:
            return False
        db.session.delete(notif)
        db.session.commit()
        return True

    @staticmethod
    def delete_all(user_id: int) -> int:
        """Supprime toutes les notifications d'un utilisateur."""
        count = Notification.query.filter_by(user_id=user_id).delete()
        db.session.commit()
        return count

    # ==================================================
    # RACCOURCIS PAR TYPE
    # ==================================================
    @staticmethod
    def success(user_id: int, title: str, message: str = "", link: str = None):
        """Notification de succès."""
        return NotificationService.notify(user_id, title, message, "success", link)

    @staticmethod
    def info(user_id: int, title: str, message: str = "", link: str = None):
        """Notification d'information."""
        return NotificationService.notify(user_id, title, message, "info", link)

    @staticmethod
    def warning(user_id: int, title: str, message: str = "", link: str = None):
        """Notification d'avertissement."""
        return NotificationService.notify(user_id, title, message, "warning", link)

    @staticmethod
    def error(user_id: int, title: str, message: str = "", link: str = None):
        """Notification d'erreur."""
        return NotificationService.notify(user_id, title, message, "error", link)