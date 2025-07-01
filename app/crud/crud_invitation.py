from sqlalchemy.orm import Session, selectinload, Load
from sqlalchemy.future import select
from typing import Optional, List
import uuid
from datetime import datetime, timedelta
import logging

from app.crud.base import CRUDBase
from app.models.invitation import Invitation, InvitationStatus
from app.schemas.invitation import InvitationCreate, InvitationUpdate
from app.core.config import settings

logger = logging.getLogger(__name__)

class CRUDInvitation(CRUDBase[Invitation, InvitationCreate, InvitationUpdate]):
    async def get_by_email_and_startup(
        self, db: Session, *, email: str, startup_id: int
    ) -> Optional[Invitation]:
        statement = select(self.model).where(self.model.email == email, self.model.startup_id == startup_id)
        result = await db.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_invitation_token(
        self, db: Session, *, token: str, options: Optional[List[Load]] = None
    ) -> Optional[Invitation]:
        query = select(self.model).where(self.model.invitation_token == token)
        if options:
            query = query.options(*options)
        result = await db.execute(query)
        return result.scalars().first()

    async def create_with_startup(
        self, db: Session, *, obj_in: InvitationCreate
    ) -> Invitation:
        # Check if an active (PENDING and not EXPIRED) invitation already exists for this email and startup
        existing_invitation_stmt = select(self.model).where(
            self.model.email == obj_in.email,
            self.model.startup_id == obj_in.startup_id,
            self.model.status == InvitationStatus.PENDING,
            self.model.expires_at > datetime.utcnow()
        )
        existing_invitation_result = await db.execute(existing_invitation_stmt)
        existing_invitation = existing_invitation_result.scalar_one_or_none()

        if existing_invitation:
            # Optionally, update the expiry of the existing invitation or just return it
            # For now, let's return the existing one if it's still valid
            # Consider if approved_by_admin_id should be updated if it's a re-invite by a different admin
            return existing_invitation

        db_obj = self.model(
            email=obj_in.email,
            startup_id=obj_in.startup_id,
            approved_by_admin_id=obj_in.approved_by_admin_id, # Store who approved
            invitation_token=str(uuid.uuid4()), # Ensure a new token is generated
            expires_at=datetime.utcnow() + timedelta(days=settings.INVITATION_EXPIRE_DAYS) # Use config for expiry
        )
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def create_for_employee(
        self, db: Session, *, email: str, company_id: int, space_id: int, admin_id: int
    ) -> Invitation:
        """Creates an invitation for an employee to a company and space."""
        # Check for existing pending invitation to this company/space
        existing_invitation_stmt = select(self.model).where(
            self.model.email == email,
            self.model.company_id == company_id,
            self.model.space_id == space_id,
            self.model.status == InvitationStatus.PENDING,
            self.model.expires_at > datetime.utcnow()
        )
        existing_invitation_result = await db.execute(existing_invitation_stmt)
        existing_invitation = existing_invitation_result.scalar_one_or_none()

        if existing_invitation:
            return existing_invitation

        db_obj = self.model(
            email=email,
            company_id=company_id,
            space_id=space_id,
            approved_by_admin_id=admin_id,
            invitation_token=str(uuid.uuid4()),
            expires_at=datetime.utcnow() + timedelta(days=settings.INVITATION_EXPIRE_DAYS)
        )
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def mark_as_accepted(self, db: Session, *, invitation: Invitation, accepted_by_user_id: int) -> Invitation:
        invitation.status = InvitationStatus.ACCEPTED
        invitation.accepted_at = datetime.utcnow()
        invitation.accepted_by_user_id = accepted_by_user_id
        invitation.updated_at = datetime.utcnow() # Ensure updated_at is set
        db.add(invitation)
        await db.commit()
        await db.refresh(invitation)
        return invitation

    async def mark_as_expired(self, db: Session, *, invitation: Invitation) -> Invitation:
        invitation.status = InvitationStatus.EXPIRED
        invitation.updated_at = datetime.utcnow()
        db.add(invitation)
        await db.commit()
        await db.refresh(invitation)
        return invitation

    async def get_pending_invitations_for_startup(self, db: Session, *, startup_id: int) -> list[Invitation]:
        """Fetches all PENDING invitations for a specific startup."""
        stmt = select(self.model).where(
            self.model.startup_id == startup_id,
            self.model.status == InvitationStatus.PENDING,
            self.model.expires_at > datetime.utcnow() # Only show non-expired pending ones
        ).order_by(self.model.created_at.desc()) # Show newest first
        
        result = await db.execute(stmt)
        return result.scalars().all()

    async def revoke_invitation(self, db: Session, *, invitation_to_revoke: Invitation, revoking_admin_id: int) -> Invitation:
        """Marks an invitation as REVOKED."""
        if invitation_to_revoke.status != InvitationStatus.PENDING:
            # Or raise an error, depending on how you want to handle it.
            # For now, just log and return the invitation as is if not PENDING.
            # This prevents revoking an already accepted/expired/revoked invitation.
            logger.warning(f"Attempt to revoke invitation {invitation_to_revoke.id} which is not PENDING. Status: {invitation_to_revoke.status}")
            return invitation_to_revoke 
            
        invitation_to_revoke.status = InvitationStatus.REVOKED
        invitation_to_revoke.revoked_at = datetime.utcnow()
        invitation_to_revoke.revoked_by_admin_id = revoking_admin_id
        invitation_to_revoke.updated_at = datetime.utcnow() # Ensure updated_at is set
        db.add(invitation_to_revoke)
        await db.commit()
        await db.refresh(invitation_to_revoke)
        logger.info(f"Invitation {invitation_to_revoke.id} for {invitation_to_revoke.email} to startup {invitation_to_revoke.startup_id} revoked by admin {revoking_admin_id}.")
        return invitation_to_revoke

    async def mark_as_declined(self, db: Session, *, invitation: Invitation, reason: Optional[str] = None) -> Invitation:
        """Marks an invitation as DECLINED."""
        if invitation.status != InvitationStatus.PENDING:
            logger.warning(f"Attempt to decline invitation {invitation.id} which is not PENDING. Status: {invitation.status}")
            # Depending on business logic, you might raise an error or just return as is.
            # For now, if it's not pending (e.g., already accepted, revoked, expired), declining it might not make sense.
            # However, if it was EXPIRED and user clicks decline, maybe we still mark it declined.
            # Let's stick to only allowing decline for PENDING invitations for now for simplicity.
            return invitation 

        invitation.status = InvitationStatus.DECLINED
        invitation.declined_at = datetime.utcnow()
        invitation.decline_reason = reason
        invitation.updated_at = datetime.utcnow()
        db.add(invitation)
        await db.commit()
        await db.refresh(invitation)
        logger.info(f"Invitation {invitation.id} for {invitation.email} to startup {invitation.startup_id} marked as DECLINED.")
        return invitation

invitation = CRUDInvitation(Invitation) 