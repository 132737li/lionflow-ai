"""
Service de statistiques et d'analyses pour le dashboard.
Toutes les fonctions agrègent les données par business_id.
"""
from datetime import datetime, timezone, timedelta, date

from sqlalchemy import func, extract, case, desc

from app.extensions import db
from app.models.contact import Contact
from app.models.campaign import Campaign
from app.models.message import Message
from app.models.log import Log


def _utcnow():
    """Heure UTC naïve (compatible MySQL DATETIME)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class StatisticsService:

    # ==================================================
    # RÉSUMÉ PRINCIPAL
    # ==================================================
    @staticmethod
    def summary(business_id: int) -> dict:
        """Retourne les compteurs pour les cartes du dashboard."""
        contacts_total = (
            db.session.query(func.count(Contact.id))
            .filter(Contact.business_id == business_id)
            .scalar() or 0
        )

        campaigns_total = (
            db.session.query(func.count(Campaign.id))
            .filter(Campaign.business_id == business_id)
            .scalar() or 0
        )

        msg_q = (
            db.session.query(
                func.count(Message.id).label("total"),
                func.sum(case((Message.status == "sent", 1), else_=0)).label("sent"),
                func.sum(case((Message.status == "delivered", 1), else_=0)).label("delivered"),
                func.sum(case((Message.status == "read", 1), else_=0)).label("read"),
                func.sum(case((Message.status == "failed", 1), else_=0)).label("failed"),
                func.sum(case((Message.status == "pending", 1), else_=0)).label("pending"),
            )
            .join(Campaign, Message.campaign_id == Campaign.id)
            .filter(Campaign.business_id == business_id)
            .one()
        )

        return {
            "contacts_total": contacts_total,
            "campaigns_total": campaigns_total,
            "messages_total": int(msg_q.total or 0),
            "messages_sent": int(msg_q.sent or 0),
            "messages_delivered": int(msg_q.delivered or 0),
            "messages_read": int(msg_q.read or 0),
            "messages_failed": int(msg_q.failed or 0),
            "messages_pending": int(msg_q.pending or 0),
        }

    # ==================================================
    # COMPARAISON PÉRIODE (Mois actuel vs Mois précédent)
    # ==================================================
    @staticmethod
    def period_comparison(business_id: int) -> dict:
        """
        Compare les messages envoyés ce mois vs le mois précédent.
        Retourne un dict avec les évolutions en %.
        """
        now = _utcnow()
        this_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_month_end = this_month_start - timedelta(seconds=1)
        last_month_start = last_month_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        def _count_msgs(start, end, status=None):
            q = (
                db.session.query(func.count(Message.id))
                .join(Campaign, Message.campaign_id == Campaign.id)
                .filter(
                    Campaign.business_id == business_id,
                    Message.created_at >= start,
                    Message.created_at <= end,
                )
            )
            if status:
                q = q.filter(Message.status.in_(status))
            return q.scalar() or 0

        # Messages envoyés (tous statuts sauf pending)
        this_sent = _count_msgs(this_month_start, now, ["sent", "delivered", "read"])
        last_sent = _count_msgs(last_month_start, last_month_end, ["sent", "delivered", "read"])

        # Messages lus
        this_read = _count_msgs(this_month_start, now, ["read"])
        last_read = _count_msgs(last_month_start, last_month_end, ["read"])

        # Contacts
        this_contacts = (
            db.session.query(func.count(Contact.id))
            .filter(
                Contact.business_id == business_id,
                Contact.created_at >= this_month_start,
            ).scalar() or 0
        )
        last_contacts = (
            db.session.query(func.count(Contact.id))
            .filter(
                Contact.business_id == business_id,
                Contact.created_at >= last_month_start,
                Contact.created_at <= last_month_end,
            ).scalar() or 0
        )

        def _pct_change(current, previous):
            if previous == 0:
                return 100.0 if current > 0 else 0.0
            return round((current - previous) / previous * 100, 1)

        return {
            "messages_sent": {
                "current": this_sent,
                "previous": last_sent,
                "change_pct": _pct_change(this_sent, last_sent),
                "direction": "up" if this_sent >= last_sent else "down",
            },
            "messages_read": {
                "current": this_read,
                "previous": last_read,
                "change_pct": _pct_change(this_read, last_read),
                "direction": "up" if this_read >= last_read else "down",
            },
            "contacts": {
                "current": this_contacts,
                "previous": last_contacts,
                "change_pct": _pct_change(this_contacts, last_contacts),
                "direction": "up" if this_contacts >= last_contacts else "down",
            },
        }

    # ==================================================
    # MESSAGES PAR JOUR (30 derniers jours)
    # ==================================================
    @staticmethod
    def messages_per_day(business_id: int, days: int = 30) -> dict:
        since = _utcnow() - timedelta(days=days - 1)
        rows = (
            db.session.query(
                func.date(Message.created_at).label("day"),
                func.sum(case((Message.status.in_(["sent", "delivered", "read"]), 1), else_=0)).label("sent"),
                func.sum(case((Message.status == "failed", 1), else_=0)).label("failed"),
                func.sum(case((Message.status == "read", 1), else_=0)).label("read"),
            )
            .join(Campaign, Message.campaign_id == Campaign.id)
            .filter(
                Campaign.business_id == business_id,
                Message.created_at >= since,
            )
            .group_by(func.date(Message.created_at))
            .order_by(func.date(Message.created_at))
            .all()
        )

        data_map = {str(r.day): (int(r.sent or 0), int(r.failed or 0), int(r.read or 0)) for r in rows}

        labels, sent, failed, read = [], [], [], []
        today = _utcnow().date()
        for i in range(days):
            d = today - timedelta(days=days - 1 - i)
            key = d.isoformat()
            labels.append(d.strftime("%d/%m"))
            s, f, r = data_map.get(key, (0, 0, 0))
            sent.append(s)
            failed.append(f)
            read.append(r)

        return {"labels": labels, "sent": sent, "failed": failed, "read": read}

    # ==================================================
    # MESSAGES PAR STATUT (doughnut)
    # ==================================================
    @staticmethod
    def messages_by_status(business_id: int) -> dict:
        rows = (
            db.session.query(
                Message.status,
                func.count(Message.id),
            )
            .join(Campaign, Message.campaign_id == Campaign.id)
            .filter(Campaign.business_id == business_id)
            .group_by(Message.status)
            .all()
        )
        mapping = {status: count for status, count in rows}
        order = ["pending", "sent", "delivered", "read", "failed"]
        return {
            "labels": ["En attente", "Envoyés", "Délivrés", "Lus", "Échoués"],
            "values": [int(mapping.get(s, 0)) for s in order],
            "keys": order,
        }

    # ==================================================
    # ÉVOLUTION DES CONTACTS (12 semaines)
    # ==================================================
    @staticmethod
    def contacts_evolution(business_id: int, weeks: int = 12) -> dict:
        today = _utcnow().date()
        start = today - timedelta(weeks=weeks - 1)
        rows = (
            db.session.query(
                func.date(Contact.created_at).label("day"),
                func.count(Contact.id).label("count"),
            )
            .filter(
                Contact.business_id == business_id,
                Contact.created_at >= datetime.combine(start, datetime.min.time()),
            )
            .group_by(func.date(Contact.created_at))
            .all()
        )
        counts_by_day = {str(r.day): int(r.count) for r in rows}

        labels, values = [], []
        cumul = (
            db.session.query(func.count(Contact.id))
            .filter(
                Contact.business_id == business_id,
                Contact.created_at < datetime.combine(start, datetime.min.time()),
            )
            .scalar() or 0
        )

        running = int(cumul)
        for i in range(weeks * 7):
            d = start + timedelta(days=i)
            running += counts_by_day.get(d.isoformat(), 0)
            if i % 7 == 6:
                labels.append(f"S{((i + 1) // 7) + 1}")
                values.append(running)

        return {"labels": labels, "values": values}

    # ==================================================
    # MESSAGES PAR HEURE (0-23)
    # ==================================================
    @staticmethod
    def messages_per_hour(business_id: int) -> dict:
        """
        Distribution des envois par heure de la journée (0-23).
        Aide à identifier la meilleure heure d'envoi.
        """
        rows = (
            db.session.query(
                extract("hour", Message.created_at).label("hour"),
                func.count(Message.id).label("count"),
            )
            .join(Campaign, Message.campaign_id == Campaign.id)
            .filter(
                Campaign.business_id == business_id,
                Message.status.in_(["sent", "delivered", "read"]),
            )
            .group_by(extract("hour", Message.created_at))
            .all()
        )

        counts = {int(r.hour): int(r.count) for r in rows}
        labels = [f"{h:02d}h" for h in range(24)]
        values = [counts.get(h, 0) for h in range(24)]

        # Meilleure heure
        best_hour = max(counts, key=counts.get) if counts else None

        return {
            "labels": labels,
            "values": values,
            "best_hour": best_hour,
            "best_hour_count": counts.get(best_hour, 0) if best_hour is not None else 0,
        }

    # ==================================================
    # TOP CONTACTS (par engagement)
    # ==================================================
    @staticmethod
    def top_contacts(business_id: int, limit: int = 5) -> list:
        """
        Top contacts triés par :
        1. Nombre de messages reçus
        2. Nombre de messages lus
        """
        rows = (
            db.session.query(
                Contact.id,
                Contact.first_name,
                Contact.last_name,
                Contact.phone,
                func.count(Message.id).label("total"),
                func.sum(case((Message.status == "read", 1), else_=0)).label("read_count"),
                func.sum(case((Message.status == "delivered", 1), else_=0)).label("delivered_count"),
            )
            .join(Message, Message.contact_id == Contact.id)
            .join(Campaign, Message.campaign_id == Campaign.id)
            .filter(Campaign.business_id == business_id)
            .group_by(Contact.id)
            .order_by(desc("read_count"), desc("total"))
            .limit(limit)
            .all()
        )

        result = []
        for r in rows:
            total = int(r.total or 0)
            read_c = int(r.read_count or 0)
            result.append({
                "id": r.id,
                "full_name": f"{r.first_name or ''} {r.last_name or ''}".strip() or r.phone,
                "phone": r.phone,
                "total_messages": total,
                "read_count": read_c,
                "read_rate": round(read_c / total * 100, 1) if total > 0 else 0,
            })

        return result

    # ==================================================
    # TAUX DE LECTURE
    # ==================================================
    @staticmethod
    def read_rate(business_id: int) -> float:
        """Taux de lecture = messages lus / messages envoyés."""
        stats = StatisticsService.summary(business_id)
        sent_total = (
            stats["messages_sent"]
            + stats["messages_delivered"]
            + stats["messages_read"]
        )
        if sent_total == 0:
            return 0.0
        return round(stats["messages_read"] / sent_total * 100, 1)

    # ==================================================
    # TAUX DE DÉLIVRABILITÉ
    # ==================================================
    @staticmethod
    def delivery_rate(business_id: int) -> float:
        stats = StatisticsService.summary(business_id)
        sent_total = (
            stats["messages_sent"]
            + stats["messages_delivered"]
            + stats["messages_read"]
        )
        if sent_total == 0:
            return 0.0
        delivered = stats["messages_delivered"] + stats["messages_read"]
        return round(delivered / sent_total * 100, 1)

    # ==================================================
    # TAUX D'ÉCHEC
    # ==================================================
    @staticmethod
    def failure_rate(business_id: int) -> float:
        stats = StatisticsService.summary(business_id)
        total = stats["messages_total"]
        if total == 0:
            return 0.0
        return round(stats["messages_failed"] / total * 100, 1)

    # ==================================================
    # ACTIVITÉ RÉCENTE
    # ==================================================
    @staticmethod
    def recent_activity(user_id: int, limit: int = 10) -> list:
        logs = (
            Log.query
            .filter(Log.user_id == user_id)
            .order_by(Log.created_at.desc())
            .limit(limit)
            .all()
        )
        return [log.to_dict() for log in logs]

    # ==================================================
    # DERNIÈRES CAMPAGNES
    # ==================================================
    @staticmethod
    def recent_campaigns(business_id: int, limit: int = 5) -> list:
        campaigns = (
            Campaign.query
            .filter(Campaign.business_id == business_id)
            .order_by(Campaign.created_at.desc())
            .limit(limit)
            .all()
        )
        return [c.to_dict() for c in campaigns]

    # ==================================================
    # DERNIERS MESSAGES
    # ==================================================
    @staticmethod
    def recent_messages(business_id: int, limit: int = 10) -> list:
        messages = (
            Message.query
            .join(Campaign, Message.campaign_id == Campaign.id)
            .filter(Campaign.business_id == business_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
            .all()
        )
        result = []
        for m in messages:
            data = m.to_dict()
            data["contact_name"] = m.contact.full_name if m.contact else "—"
            data["contact_phone"] = m.contact.phone if m.contact else "—"
            data["campaign_name"] = m.campaign.name if m.campaign else "—"
            result.append(data)
        return result

    # ==================================================
    # INSIGHTS (recommandations intelligentes)
    # ==================================================
    @staticmethod
    def insights(business_id: int) -> list:
        """
        Génère des insights intelligents basés sur les données.
        Retourne une liste de dicts {type, icon, title, message}.
        """
        insights = []
        stats = StatisticsService.summary(business_id)
        summary_sent = (
            stats["messages_sent"]
            + stats["messages_delivered"]
            + stats["messages_read"]
        )

        # Insight 1 — Meilleure heure d'envoi
        hour_stats = StatisticsService.messages_per_hour(business_id)
        if hour_stats["best_hour"] is not None and hour_stats["best_hour_count"] > 0:
            insights.append({
                "type": "info",
                "icon": "bi-clock-history",
                "title": "Meilleure heure d'envoi",
                "message": (
                    f"Vos messages sont les plus nombreux à "
                    f"<strong>{hour_stats['best_hour']:02d}h</strong>. "
                    f"Essayez de programmer vos campagnes à cette heure."
                ),
            })

        # Insight 2 — Taux de lecture
        rate = StatisticsService.read_rate(business_id)
        if summary_sent >= 10:
            if rate >= 60:
                insights.append({
                    "type": "success",
                    "icon": "bi-graph-up-arrow",
                    "title": "Excellent engagement",
                    "message": (
                        f"Votre taux de lecture est de "
                        f"<strong>{rate}%</strong>. Continuez comme ça !"
                    ),
                })
            elif rate < 30:
                insights.append({
                    "type": "warning",
                    "icon": "bi-graph-down-arrow",
                    "title": "Taux de lecture faible",
                    "message": (
                        f"Seulement <strong>{rate}%</strong> de vos messages sont lus. "
                        f"Essayez des messages plus courts ou avec des emojis."
                    ),
                })

        # Insight 3 — Taux d'échec
        fail_rate = StatisticsService.failure_rate(business_id)
        if stats["messages_total"] >= 10 and fail_rate >= 5:
            insights.append({
                "type": "error",
                "icon": "bi-exclamation-triangle",
                "title": "Taux d'échec élevé",
                "message": (
                    f"<strong>{fail_rate}%</strong> de vos messages échouent. "
                    f"Vérifiez la validité des numéros WhatsApp de vos contacts."
                ),
            })

        # Insight 4 — Croissance contacts
        comparison = StatisticsService.period_comparison(business_id)
        contacts_change = comparison["contacts"]["change_pct"]
        if contacts_change >= 20:
            insights.append({
                "type": "success",
                "icon": "bi-people",
                "title": "Croissance des contacts",
                "message": (
                    f"Votre base de contacts a augmenté de "
                    f"<strong>+{contacts_change}%</strong> ce mois-ci !"
                ),
            })

        # Insight 5 — Croissance messages
        msgs_change = comparison["messages_sent"]["change_pct"]
        if msgs_change >= 30:
            insights.append({
                "type": "success",
                "icon": "bi-send-check",
                "title": "Activité en forte hausse",
                "message": (
                    f"Vous avez envoyé <strong>+{msgs_change}%</strong> de messages "
                    f"ce mois-ci par rapport au mois dernier."
                ),
            })
        elif msgs_change <= -30:
            insights.append({
                "type": "warning",
                "icon": "bi-send-dash",
                "title": "Activité en baisse",
                "message": (
                    f"Vous avez envoyé <strong>{msgs_change}%</strong> de messages "
                    f"ce mois-ci. Pensez à relancer vos campagnes."
                ),
            })

        # Insight 6 — Pas de campagne
        if stats["campaigns_total"] == 0 and stats["contacts_total"] > 0:
            insights.append({
                "type": "info",
                "icon": "bi-megaphone",
                "title": "Prêt à démarrer ?",
                "message": (
                    "Vous avez des contacts mais aucune campagne. "
                    "Créez votre première campagne pour les engager !"
                ),
            })

        return insights