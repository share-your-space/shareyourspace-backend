from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from datetime import datetime
import logging
from typing import Optional

from app import crud, models, schemas, security
from app.db.session import get_db
from app.core.config import settings
from app.utils.email import send_startup_invitation_email
from app.security import get_current_user_with_roles
from app.models.enums import UserRole, NotificationType
from app.schemas.token import TokenWithUser
from app.crud import crud_connection, crud_notification

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/{invitation_token}/details", response_model=schemas.invitation.InvitationDetails)
async def get_invitation_details(
    invitation_token: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Public endpoint to get basic details about an invitation.
    """
    invitation = await crud.invitation.get_by_invitation_token(
        db, token=invitation_token, options=[
            selectinload(models.Invitation.company),
            selectinload(models.Invitation.startup)
        ]
    )

    if not invitation or invitation.status != models.invitation.InvitationStatus.PENDING or invitation.expires_at < datetime.utcnow():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found or has expired.")
    
    org_name = ""
    org_type = ""

    if invitation.company:
        org_name = invitation.company.name
        org_type = "Company"
    elif invitation.startup:
        org_name = invitation.startup.name
        org_type = "Startup"

    return schemas.invitation.InvitationDetails(
        email=invitation.email,
        organization_name=org_name,
        organization_type=org_type
    )

@router.post("/invite", response_model=schemas.invitation.Invitation)
async def create_invitation(
    invite_data: schemas.invitation.UnifiedInvitationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user_with_roles([UserRole.CORP_ADMIN, UserRole.STARTUP_ADMIN])),
):
    """
    Creates an invitation for a user to join a startup.
    - Accessible by CORP_ADMIN and STARTUP_ADMIN.
    - Checks for available member slots before inviting.
    """
    target_startup = await crud.crud_organization.get_startup(db, startup_id=invite_data.startup_id)
    if not target_startup:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Startup not found.")

    if current_user.role == UserRole.CORP_ADMIN:
        if not current_user.space_id or target_startup.space_id != current_user.space_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only invite to startups within your managed space.")
    elif current_user.role == UserRole.STARTUP_ADMIN:
        if target_startup.id != current_user.startup_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only invite members to your own startup.")

    if target_startup.member_slots_used >= target_startup.member_slots_allocated:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No available member slots for this startup.")

    existing_user_in_startup = await crud.crud_user.get_user_by_email_and_startup(db, email=invite_data.email, startup_id=target_startup.id)
    if existing_user_in_startup:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User is already a member of this startup.")
    
    existing_invitation = await crud.invitation.get_by_email_and_startup(db, email=invite_data.email, startup_id=target_startup.id)
    if existing_invitation and existing_invitation.status == models.invitation.InvitationStatus.PENDING:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An active invitation for this user already exists.")

    invitation_create_schema = schemas.invitation.InvitationCreate(
        email=invite_data.email,
        startup_id=target_startup.id,
        approved_by_admin_id=current_user.id
    )

    try:
        invitation = await crud.invitation.create_with_startup(db, obj_in=invitation_create_schema)
        send_startup_invitation_email(
            to_email=invite_data.email,
            token=invitation.invitation_token,
            startup_name=target_startup.name,
            invited_by_name=current_user.full_name
        )
        return invitation
    except Exception as e:
        logger.error(f"Failed to create invitation for {invite_data.email}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create and send invitation.")

@router.post("/accept/{invitation_token}", response_model=TokenWithUser)
async def accept_invitation(
    invitation_token: str,
    user_create_data: schemas.user.UserCreateAcceptInvitation,
    db: AsyncSession = Depends(get_db),
):
    invitation = await crud.invitation.get_by_invitation_token(db, token=invitation_token)

    if not invitation or invitation.status != models.invitation.InvitationStatus.PENDING or invitation.expires_at < datetime.utcnow():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invitation is invalid, expired, or has already been used.")

    # Determine organization type and fetch it
    if invitation.company_id:
        target_org = await crud.crud_organization.get_company(db, company_id=invitation.company_id)
        org_type = "company"
        new_role = UserRole.CORP_EMPLOYEE
    elif invitation.startup_id:
        target_org = await crud.crud_organization.get_startup(db, startup_id=invitation.startup_id)
        org_type = "startup"
        new_role = UserRole.STARTUP_MEMBER
    else:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Invitation is not linked to any organization.")

    if not target_org:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Associated organization not found.")

    # Handle startup-specific logic (member slots)
    if org_type == "startup":
        if target_org.member_slots_used >= target_org.member_slots_allocated:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="All member slots for this startup have been filled.")

    # Create or update user
    existing_user = await crud.crud_user.get_user_by_email(db, email=invitation.email)
    
    final_user: models.User
    if existing_user:
        if existing_user.startup_id is not None or existing_user.company_id is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User is already associated with an organization.")
        
        update_data = {
            "role": new_role,
            "is_active": True, 
            "status": "ACTIVE",
            "space_id": invitation.space_id,
            f"{org_type}_id": target_org.id
        }
        final_user = await crud.crud_user.update_user_internal(db, db_obj=existing_user, obj_in=schemas.user.UserUpdateInternal(**update_data))
    else:
        user_create_data_dict = {
            "email": invitation.email,
            "full_name": user_create_data.full_name,
            "password": user_create_data.password,
            "role": new_role,
            "status": "ACTIVE",
            "is_active": True,
            "space_id": invitation.space_id,
            f"{org_type}_id": target_org.id
        }
        final_user = await crud.crud_user.create_user(db=db, obj_in=schemas.user.UserCreate(**user_create_data_dict))

    # Update organization state if needed
    if org_type == "startup":
        target_org.member_slots_used += 1
        db.add(target_org)
    
    await crud.invitation.mark_as_accepted(db, invitation=invitation, accepted_by_user_id=final_user.id)

    # Automatically create a connection with the inviting admin
    # and send notification
    if invitation.invited_by_user_id:
        await crud_connection.create_accepted_connection(
            db, user_one_id=final_user.id, user_two_id=invitation.invited_by_user_id
        )
        await crud_notification.create_notification(
            db,
            user_id=invitation.invited_by_user_id,
            type=NotificationType.INVITATION_ACCEPTED,
            message=f"{final_user.full_name or final_user.email} has accepted your invitation to join {target_org.name}.",
            reference=f"user:{final_user.id}"
        )

    await db.commit()

    # Re-fetch the user with all relationships loaded to satisfy the response_model
    final_user_with_relations = await crud.crud_user.get_user_details_for_profile(
        db, user_id=final_user.id
    )
    if not final_user_with_relations:
        raise HTTPException(status_code=500, detail="Could not retrieve user details after creation.")

    access_token = security.create_access_token(
        data={"sub": final_user_with_relations.email, "user_id": final_user_with_relations.id, "role": final_user_with_relations.role.value}
    )

    return TokenWithUser(access_token=access_token, token_type="bearer", user=final_user_with_relations)

@router.get("/startup/pending", response_model=schemas.invitation.InvitationListResponse)
async def list_pending_invitations_for_startup(
    current_user: models.User = Depends(get_current_user_with_roles(["STARTUP_ADMIN"])),
    db: AsyncSession = Depends(get_db),
):
    """Lists all pending and non-expired invitations for the current startup admin's startup."""
    if not current_user.startup_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is not associated with a startup.")
    pending_invitations = await crud.invitation.get_pending_invitations_for_startup(
        db, startup_id=current_user.startup_id
    )
    return schemas.invitation.InvitationListResponse(invitations=pending_invitations)

@router.put("/{invitation_id}/revoke", response_model=schemas.invitation.Invitation)
async def revoke_startup_invitation(
    invitation_id: int,
    current_user: models.User = Depends(get_current_user_with_roles(["STARTUP_ADMIN"])),
    db: AsyncSession = Depends(get_db),
):
    """Revokes a pending invitation."""
    invitation_to_revoke = await crud.invitation.get(db, id=invitation_id)
    if not invitation_to_revoke:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found.")
    if not current_user.startup_id or invitation_to_revoke.startup_id != current_user.startup_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to revoke this invitation.")
    if invitation_to_revoke.status != models.invitation.InvitationStatus.PENDING:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invitation cannot be revoked as its status is {invitation_to_revoke.status}.")
    revoked_invitation = await crud.invitation.revoke_invitation(
        db, invitation_to_revoke=invitation_to_revoke, revoking_admin_id=current_user.id
    )
    return revoked_invitation

@router.post("/decline/{invitation_token}", response_model=schemas.invitation.Invitation)
async def decline_startup_invitation(
    invitation_token: str,
    decline_data: Optional[schemas.invitation.InvitationDecline] = Body(None),
    db: AsyncSession = Depends(get_db),
):
    """Allows a user to decline a pending startup invitation."""
    invitation = await crud.invitation.get_by_invitation_token(db, token=invitation_token)
    if not invitation or invitation.status != models.invitation.InvitationStatus.PENDING:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invitation is no longer pending.")
    reason = decline_data.reason if decline_data else None
    declined_invitation = await crud.invitation.mark_as_declined(db, invitation=invitation, reason=reason)
    return declined_invitation 