"""
Service de gestion des membres d'une entreprise.
"""
from flask import url_for
from app.extensions import db
from app.models.business_member import BusinessMember
from app.models.role_change_request import RoleChangeRequest
from app.models.user import User
from app.services.notification_service import NotificationService


class MemberService:

    @staticmethod
    def get_business_role(user, business_id: int) -> str:
        """Retourne le rôle d'un utilisateur dans une entreprise (ou None)."""
        member = BusinessMember.query.filter_by(
            user_id=user.id, business_id=business_id, is_active=True
        ).first()
        return member.role if member else None

    @staticmethod
    def add_member(business, email: str, role: str = "viewer") -> BusinessMember:
        """Ajoute un membre à une entreprise. Crée un utilisateur s'il n'existe pas."""
        user = User.query.filter_by(email=email.lower()).first()
        
        if not user:
            user = User(
                email=email.lower(), 
                first_name=email.split('@')[0], 
                is_active=False
            )
            user.set_password("Temporaire123!")
            db.session.add(user)
            db.session.flush()

        existing = BusinessMember.query.filter_by(business_id=business.id, user_id=user.id).first()
        if existing:
            raise ValueError("Cet utilisateur est déjà membre de l'entreprise.")

        member = BusinessMember(
            business_id=business.id,
            user_id=user.id,
            role=role
        )
        db.session.add(member)
        db.session.commit()
        return member

    @staticmethod
    def request_role_change(business, target_user, new_role: str, requested_by) -> RoleChangeRequest:
        """Crée une demande de changement de rôle (approuvée par le super-admin)."""
        member = BusinessMember.query.filter_by(business_id=business.id, user_id=target_user.id).first()
        if not member:
            raise ValueError("Cet utilisateur n'est pas membre de l'entreprise.")
            
        if member.role == new_role:
            raise ValueError("L'utilisateur a déjà ce rôle.")

        existing_req = RoleChangeRequest.query.filter_by(
            business_id=business.id, target_user_id=target_user.id, status="pending"
        ).first()
        if existing_req:
            raise ValueError("Une demande est déjà en attente pour cet utilisateur.")

        req = RoleChangeRequest(
            business_id=business.id,
            target_user_id=target_user.id,
            requested_by_id=requested_by.id,
            requested_role=new_role
        )
        db.session.add(req)
        db.session.commit()

        # ✅ NOUVEAU : Notifier tous les Super Admins de la plateforme
        super_admins = User.query.filter_by(role="admin", is_active=True).all()
        for admin in super_admins:
            NotificationService.notify(
                user_id=admin.id,
                title="Demande de rôle en attente",
                message=f"{requested_by.full_name} demande de changer le rôle de {target_user.full_name} en '{new_role}' pour l'entreprise {business.name}.",
                type="warning",
                link="/admin/role-requests"
            )

        return req