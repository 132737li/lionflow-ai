"""
Modèle RoleChangeRequest — Demande de changement de rôle en attente d'approbation.
"""
from datetime import datetime, timezone
from app.extensions import db


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class RoleChangeRequest(db.Model):
    __tablename__ = "role_change_requests"

    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(
        db.Integer, db.ForeignKey("businesses.id", ondelete="CASCADE"), 
        nullable=False, index=True
    )
    target_user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), 
        nullable=False, index=True
    )
    requested_by_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), 
        nullable=True
    )
    requested_role = db.Column(
        db.Enum("owner", "admin", "editor", "viewer", name="member_role"),
        nullable=False
    )
    
    status = db.Column(
        db.Enum("pending", "approved", "rejected", name="request_status"),
        nullable=False, default="pending", index=True
    )
    
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)
    reviewed_at = db.Column(db.DateTime)
    reviewed_by_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), 
        nullable=True
    )

    business = db.relationship("Business")
    target_user = db.relationship("User", foreign_keys=[target_user_id])
    requested_by = db.relationship("User", foreign_keys=[requested_by_id])
    reviewed_by = db.relationship("User", foreign_keys=[reviewed_by_id])