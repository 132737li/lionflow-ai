"""
Service de statistiques pour le dashboard et l'API.
Toutes les fonctions agrègent les données par business_id.
"""
from datetime import datetime, timezone, timedelta

from sqlalchemy import func, extract, case

from app.extensions import db
from app.models.contact import Contact
from app.models.campaign import Campaign
from app.models.message import Message
from app.models.log import Log


def _utcnow():
    """Heure UTC naïve (compatible MySQL DATETIME)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class StatisticsService:

    @staticmethod
    def summary(business_id: int) -> dict:
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

    @staticmethod
    def messages_per_day(business_id: int, days: int = 30) -> dict:
        since = _utcnow() - timedelta(days=days - 1)
        rows = (
            db.session.query(
                func.date(Message.created_at).label("day"),
                func.sum(case((Message.status.in_(["sent", "delivered", "read"]), 1), else_=0)).label("sent"),
                func.sum(case((Message.status == "failed", 1), else_=0)).label("failed"),
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

        data_map = {str(r.day): (int(r.sent or 0), int(r.failed or 0)) for r in rows}

        labels, sent, failed = [], [], []
        today = _utcnow().date()
        for i in range(days):
            d = today - timedelta(days=days - 1 - i)
            key = d.isoformat()
            labels.append(d.strftime("%d/%m"))
            s, f = data_map.get(key, (0, 0))
            sent.append(s)
            failed.append(f)

        return {"labels": labels, "sent": sent, "failed": failed}

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

    @staticmethod
    def recent_activity(user_id: int, limit: int = 10):
        logs = (
            Log.query
            .filter(Log.user_id == user_id)
            .order_by(Log.created_at.desc())
            .limit(limit)
            .all()
        )
        return [log.to_dict() for log in logs]

    @staticmethod
    def recent_campaigns(business_id: int, limit: int = 5):
        campaigns = (
            Campaign.query
            .filter(Campaign.business_id == business_id)
            .order_by(Campaign.created_at.desc())
            .limit(limit)
            .all()
        )
        return [c.to_dict() for c in campaigns]

    @staticmethod
    def recent_messages(business_id: int, limit: int = 10):
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

    @staticmethod
    def delivery_rate(business_id: int) -> float:
        stats = StatisticsService.summary(business_id)
        total = stats["messages_sent"] + stats["messages_delivered"] + stats["messages_read"]
        if total == 0:
            return 0.0
        delivered = stats["messages_delivered"] + stats["messages_read"]
        return round(delivered / total * 100, 1)