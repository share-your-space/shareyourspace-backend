from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from app import crud, models, schemas, security
from app.models.enums import UserStatus, UserRole, NotificationType
from app.crud.crud_notification import create_notification_for_org_admins
from app.utils.email import send_startup_invitation_email

async def request_invitation(
    db: AsyncSession, *, request_data: schemas.organization.InvitationRequest, current_user: models.User
):
    """
    Handles a user's request for an invitation to an organization.
    """
    org_id = request_data.organization_id
    org_type = request_data.organization_type

    await crud.crud_user.update_user_internal(
        db, db_obj=current_user, obj_in=schemas.user.UserUpdateInternal(status=UserStatus.WAITLISTED)
    )

    await create_notification_for_org_admins(
        db=db,
        org_id=org_id,
        org_type=org_type,
        message=f"User '{current_user.full_name or current_user.email}' has requested an invitation to join.",
        related_entity_id=current_user.id
    )
    
    await db.commit()

async def create_admin_invitation(
    db: AsyncSession, *, invite_data: schemas.invitation.AdminInviteCreate, current_user: models.User
) -> models.Invitation:
    if not current_user.company_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin is not associated with a company.")

    invitation = await crud.invitation.create_with_company_and_role(
        db,
        obj_in=schemas.invitation.InvitationCreate(
            email=invite_data.email,
            company_id=current_user.company_id,
            role=UserRole.CORP_ADMIN,
            invited_by_user_id=current_user.id
        )
    )
    # TODO: Create a new email template for admin invitations
    # send_admin_invitation_email(to_email=invite_data.email, token=invitation.invitation_token, company_name=current_user.company.name)
    return invitation

async def create_startup_invitation(
    db: AsyncSession, *, invite_data: schemas.invitation.UnifiedInvitationCreate, current_user: models.User
) -> models.Invitation:
    target_startup = await crud.crud_organization.get_startup(db, startup_id=invite_data.startup_id)
    if not target_startup:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Startup not found.")

    if target_startup.member_slots_used >= target_startup.member_slots_allocated:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No available member slots.")

    invitation = await crud.invitation.create_with_startup(
        db, obj_in=schemas.invitation.InvitationCreate(**invite_data.model_dump(), approved_by_admin_id=current_user.id)
    )
    send_startup_invitation_email(
        to_email=invite_data.email,
        token=invitation.invitation_token,
        startup_name=target_startup.name,
        invited_by_name=current_user.full_name
    )
    return invitation

async def accept_invitation(
    db: AsyncSession, *, token: str, user_data: schemas.user.UserCreateAcceptInvitation
) -> schemas.token.TokenWithUser:
    invitation = await crud.invitation.get_by_invitation_token(db, token=token)
    if not invitation or invitation.status != 'PENDING' or invitation.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Invitation is invalid or expired.")

    if invitation.role == UserRole.CORP_ADMIN:
        # Accepting an admin invitation
        user_create = schemas.user.UserCreate(**user_data.model_dump(), email=invitation.email, role=UserRole.CORP_ADMIN, company_id=invitation.company_id)
        user = await crud.crud_user.create_user(db, obj_in=user_create)
    elif invitation.startup_id:
        # Accepting a startup member invitation
        startup = await crud.crud_organization.get_startup(db, startup_id=invitation.startup_id)
        if startup.member_slots_used >= startup.member_slots_allocated:
            raise HTTPException(status_code=409, detail="All member slots are filled.")
        startup.member_slots_used += 1
        db.add(startup)
        user_create = schemas.user.UserCreate(**user_data.model_dump(), email=invitation.email, role=UserRole.STARTUP_MEMBER, startup_id=invitation.startup_id, space_id=startup.space_id)
        user = await crud.crud_user.create_user(db, obj_in=user_create)
    else:
        raise HTTPException(status_code=500, detail="Invalid invitation type.")
    
    await crud.invitation.mark_as_accepted(db, invitation=invitation, accepted_by_user_id=user.id)
    if invitation.invited_by_user_id:
        await crud.crud_connection.create_accepted_connection(db, user_one_id=user.id, user_two_id=invitation.invited_by_user_id)
        await crud.crud_notification.create_notification(
            db,
            user_id=invitation.invited_by_user_id,
            type=NotificationType.INVITATION_ACCEPTED,
            message=f"{user.full_name} accepted your invitation.",
            reference=f"user:{user.id}"
        )

    await db.commit()
    
    final_user = await crud.crud_user.get_user_details_for_profile(db, user_id=user.id)
    access_token = security.create_access_token({"sub": final_user.email, "user_id": final_user.id, "role": final_user.role.value})
    
    return schemas.token.TokenWithUser(access_token=access_token, token_type="bearer", user=final_user)

async def get_invitation_details(db: AsyncSession, *, token: str) -> schemas.invitation.InvitationDetails:
    invitation = await crud.invitation.get_by_invitation_token(db, token=token, options=[
        models.Invitation.company, models.Invitation.startup
    ])
    if not invitation or invitation.status != 'PENDING' or invitation.expires_at < datetime.utcnow():
        raise HTTPException(status_code=404, detail="Invitation not found or has expired.")
    
    org_name = ""
    if invitation.company:
        org_name = invitation.company.name
    elif invitation.startup:
        org_name = invitation.startup.name

    return schemas.invitation.InvitationDetails(
        email=invitation.email, organization_name=org_name
    )

async def revoke_invitation(db: AsyncSession, *, invitation_id: int, current_user: models.User) -> models.Invitation:
    invitation = await crud.invitation.get(db, id=invitation_id)
    if not invitation:
        raise HTTPException(status_code=404, detail="Invitation not found.")
    if not current_user.startup_id or invitation.startup_id != current_user.startup_id:
        raise HTTPException(status_code=403, detail="Not authorized.")
    if invitation.status != 'PENDING':
        raise HTTPException(status_code=400, detail="Invitation is not pending.")
    
    return await crud.invitation.revoke_invitation(db, invitation_to_revoke=invitation, revoking_admin_id=current_user.id)

async def decline_invitation(db: AsyncSession, *, token: str, reason: str = None) -> models.Invitation:
    invitation = await crud.invitation.get_by_invitation_token(db, token=token)
    if not invitation or invitation.status != 'PENDING':
        raise HTTPException(status_code=400, detail="Invitation is not pending.")
        
    return await crud.invitation.mark_as_declined(db, invitation=invitation, reason=reason) 