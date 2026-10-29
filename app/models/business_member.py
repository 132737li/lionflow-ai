"""
Modèle BusinessMember — lie un utilisateur à une entreprise avec un rôle spécifique.
"""
from datetime import datetime, timezone
from app.extensions import db


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class BusinessMember(db.Model):
    __tablename__ = "business_members"
    __table_args__ = (
        db.UniqueConstraint("business_id", "user_id", name="uq_business_user"),
    )

    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(
        db.Integer, db.ForeignKey("businesses.id", ondelete="CASCADE"), 
        nullable=False, index=True
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), 
        nullable=False, index=True
    )
    role = db.Column(
        db.Enum("owner", "admin", "editor", "viewer", name="member_role"),
        nullable=False, default="viewer"
    )
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    business = db.relationship("Business", backref="members")
    user = db.relationship("User", backref="business_memberships")

    def __repr__(self):
        return f"<BusinessMember {self.user.email} @ {self.business.name} ({self.role})>"