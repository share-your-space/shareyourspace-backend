from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
import logging
from typing import Optional

from app import crud, models, schemas, security # Ensure security is imported
from app.db.session import get_db
from app.core.config import settings
from app.utils.email import send_email, send_startup_invitation_email # For potential notifications
from app.security import get_current_user_with_roles # For role checks and getting user details

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/accept/{invitation_token}", response_model=schemas.auth.TokenWithUser)
async def accept_startup_invitation(
    invitation_token: str,
    user_create_data: schemas.user.UserCreateAcceptInvitation, # Frontend will send this, but we ignore if user exists for now
    db: AsyncSession = Depends(get_db),
):
    invitation = await crud.invitation.get_by_invitation_token(db, token=invitation_token)

    if not invitation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found.")
    
    if invitation.status != models.invitation.InvitationStatus.PENDING:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invitation is no longer valid or has already been used.")

    if invitation.expires_at < datetime.utcnow():
        # await crud.invitation.mark_as_expired(db, invitation=invitation) # TODO: Consider batch job for expired tokens
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invitation has expired.")

    target_startup = await crud.crud_organization.get_startup(db, startup_id=invitation.startup_id)
    if not target_startup:
        logger.error(f"Startup {invitation.startup_id} linked to invitation {invitation.id} not found.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error processing invitation: Associated startup not found.")

    existing_user = await crud.crud_user.get_user_by_email(db, email=invitation.email)
    
    final_user: models.User

    if existing_user:
        logger.info(f"Existing user {existing_user.email} (ID: {existing_user.id}) attempting to accept invitation {invitation.id}.")
        # User exists, check if they can be added to the startup
        if existing_user.startup_id is not None:
            if existing_user.startup_id == target_startup.id:
                 raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User is already a member of this startup.")
            else:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User is already a member of another startup.")
        
        if existing_user.company_id is not None:
            # This logic might need refinement based on business rules (e.g., can a company employee also join a startup?)
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User is currently associated with a company.")

        # If suitable, update existing user
        update_data = schemas.user.UserUpdateInternal(
            startup_id=target_startup.id,
            space_id=target_startup.space_id,
            role="STARTUP_MEMBER", # Or keep existing role if more permissive/general and suitable
            is_active=True, 
            status="ACTIVE"
        )
        try:
            final_user = await crud.crud_user.update_user_internal(db, db_obj=existing_user, obj_in=update_data)
            logger.info(f"Existing user {final_user.id} successfully updated and linked to startup {target_startup.id}.")
        except Exception as e:
            logger.error(f"Error updating existing user {existing_user.id} for invitation {invitation.id}: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not update existing user account.")
    
    else:
        # User does not exist - Create a new user
        user_in_create = schemas.user.UserCreate(
            email=invitation.email, 
            full_name=user_create_data.full_name,
            password=user_create_data.password, 
            role="STARTUP_MEMBER",
            startup_id=target_startup.id,
            space_id=target_startup.space_id
        )
        try:
            new_user_created = await crud.crud_user.create_user(db=db, obj_in=user_in_create)
            activated_user = await crud.crud_user.activate_user_for_startup_invitation(db=db, user_to_activate=new_user_created)
            if not activated_user:
                 logger.error(f"Failed to activate new user {new_user_created.id} after accepting invitation {invitation.id}.")
                 raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="User account created but activation failed.")
            final_user = activated_user
            logger.info(f"New user {final_user.id} created and activated for startup {target_startup.id}.")
        except Exception as e:
            logger.error(f"Error creating new user from invitation {invitation.id} for email {invitation.email}: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not create user account.")

    # Mark invitation as accepted
    await crud.invitation.mark_as_accepted(db, invitation=invitation, accepted_by_user_id=final_user.id)

    # Log the user in by creating an access token
    access_token = security.create_access_token(
        data={"sub": final_user.email, "user_id": final_user.id, "role": final_user.role}
    )

    # --- Send Notifications ---
    startup_admins = await crud.crud_user.get_users_by_role_and_startup(db, role="STARTUP_ADMIN", startup_id=target_startup.id)
    if startup_admins:
        for startup_admin in startup_admins:
            notification_content_to_startup_admin = f"{final_user.full_name} ({final_user.email}) has accepted their invitation and joined your startup, {target_startup.name}."
            if invitation.approved_by_admin_id:
                corp_admin_approver = await crud.crud_user.get_user_by_id(db, user_id=invitation.approved_by_admin_id)
                if corp_admin_approver:
                    notification_content_to_startup_admin += f" This invitation was originally approved by Corp Admin {corp_admin_approver.full_name}."
            
            await crud.crud_notification.create_notification(
                db=db, 
                user_id=startup_admin.id, 
                type="member_joined_startup",
                message=notification_content_to_startup_admin, 
                reference=f"user:{final_user.id},startup:{target_startup.id}"
            )

    if invitation.approved_by_admin_id:
        corp_admin_approver = await crud.crud_user.get_user_by_id(db, user_id=invitation.approved_by_admin_id)
        if corp_admin_approver:
            notification_content_to_corp_admin = (
                f"The invitation you approved for {final_user.full_name} ({final_user.email}) "
                f"to join startup {target_startup.name} has been accepted."
            )
            await crud.crud_notification.create_notification(
                db=db, 
                user_id=corp_admin_approver.id, 
                type="invitation_accepted",
                message=notification_content_to_corp_admin, 
                reference=f"user:{final_user.id},invitation:{invitation.id}"
            )

    return schemas.auth.TokenWithUser(access_token=access_token, token_type="bearer", user=final_user)


@router.get("/startup/pending", response_model=schemas.invitation.InvitationListResponse)
async def list_pending_invitations_for_startup(
    current_user: models.User = Depends(get_current_user_with_roles(["STARTUP_ADMIN"])),
    db: AsyncSession = Depends(get_db),
):
    """
    Lists all pending and non-expired invitations for the current startup admin's startup.
    """
    if not current_user.startup_id:
        logger.warning(f"Startup Admin {current_user.id} has no startup_id associated.")
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
    """
    Revokes a pending invitation. Only accessible by Startup Admins for their own startup's invitations.
    """
    invitation_to_revoke = await crud.invitation.get(db, id=invitation_id)

    if not invitation_to_revoke:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found.")

    if not current_user.startup_id or invitation_to_revoke.startup_id != current_user.startup_id:
        logger.warning(
            f"Startup Admin {current_user.id} (startup_id: {current_user.startup_id}) attempted to revoke invitation {invitation_id} "
            f"belonging to another startup (startup_id: {invitation_to_revoke.startup_id})."
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to revoke this invitation.")

    if invitation_to_revoke.status != models.invitation.InvitationStatus.PENDING:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invitation cannot be revoked as its status is {invitation_to_revoke.status}.")
    
    if invitation_to_revoke.expires_at < datetime.utcnow():
        # This check is also in get_pending_invitations_for_startup, but good to have defense in depth
        # Optionally, could auto-mark as EXPIRED here if not already.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot revoke an already expired invitation. It will be automatically filtered.")

    revoked_invitation = await crud.invitation.revoke_invitation(
        db, invitation_to_revoke=invitation_to_revoke, revoking_admin_id=current_user.id
    )
    
    # TODO: Optionally, send a notification to the invited user that the invitation was revoked (if email was collected and user was PENDING)
    # TODO: Optionally, notify the Corp Admin (if one approved it) that it was revoked by the Startup Admin

    return revoked_invitation

@router.post("/decline/{invitation_token}", response_model=schemas.invitation.Invitation)
async def decline_startup_invitation(
    invitation_token: str,
    decline_data: Optional[schemas.invitation.InvitationDecline] = Body(None), # Reason is optional
    db: AsyncSession = Depends(get_db),
):
    """
    Allows a user to decline a pending startup invitation.
    """
    invitation = await crud.invitation.get_by_invitation_token(db, token=invitation_token)

    if not invitation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found.")
    
    if invitation.status != models.invitation.InvitationStatus.PENDING:
        # If already actioned (accepted, revoked, declined) or expired, inform appropriately.
        # We could return the current invitation status or a specific message.
        detail_message = f"Invitation is no longer pending. Current status: {invitation.status.value}."
        if invitation.status == models.invitation.InvitationStatus.EXPIRED:
            detail_message = "Invitation has expired and cannot be declined."
        elif invitation.status == models.invitation.InvitationStatus.ACCEPTED:
            detail_message = "Invitation has already been accepted."
        elif invitation.status == models.invitation.InvitationStatus.REVOKED:
            detail_message = "Invitation has been revoked by an administrator."
        elif invitation.status == models.invitation.InvitationStatus.DECLINED:
            detail_message = "Invitation has already been declined."
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail_message)

    if invitation.expires_at < datetime.utcnow():
        # This check is somewhat redundant if we only allow PENDING status, as an expired token should move to EXPIRED status.
        # However, having it ensures robustness if a token somehow remains PENDING past expiry without a batch job updating it.
        # The CRUD method `mark_as_declined` also checks for PENDING, so this is belt-and-suspenders.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invitation has expired.")

    reason = decline_data.reason if decline_data else None
    declined_invitation = await crud.invitation.mark_as_declined(db, invitation=invitation, reason=reason)

    # --- Send Notifications --- 
    # Notify Corp Admin who approved (if any) and Startup Admins
    target_startup = await crud.crud_organization.get_startup(db, startup_id=invitation.startup_id)
    if not target_startup:
        logger.error(f"Startup {invitation.startup_id} for declined invitation {invitation.id} not found. Cannot send full notifications.")
        # Invitation is declined, but notifications might be incomplete.
    else:
        # Notify Startup Admins
        startup_admins = await crud.crud_user.get_users_by_role_and_startup(db, role="STARTUP_ADMIN", startup_id=target_startup.id)
        if startup_admins:
            for startup_admin in startup_admins:
                notification_msg = f"The invitation for {invitation.email} to join your startup, {target_startup.name}, has been declined."
                if reason:
                    notification_msg += f" Reason provided: \"{reason}\""
                if invitation.approved_by_admin_id:
                    corp_admin_approver = await crud.crud_user.get_user_by_id(db, user_id=invitation.approved_by_admin_id)
                    if corp_admin_approver:
                        notification_msg += f" (Original request approved by Corp Admin {corp_admin_approver.full_name or corp_admin_approver.email})"
                
                await crud.crud_notification.create_notification(
                    db=db, 
                    user_id=startup_admin.id, 
                    type="startup_invitation_declined", 
                    message=notification_msg, 
                    reference=f"invitation:{invitation.id},email:{invitation.email}"
                )
        
        # Notify the Corp Admin who approved this (if any)
        if invitation.approved_by_admin_id:
            corp_admin_approver = await crud.crud_user.get_user_by_id(db, user_id=invitation.approved_by_admin_id)
            if corp_admin_approver:
                notification_msg_corp_admin = f"The invitation for {invitation.email} to join startup {target_startup.name} (which you approved) has been declined."
                if reason:
                    notification_msg_corp_admin += f" Reason provided: \"{reason}\""

                await crud.crud_notification.create_notification(
                    db=db, 
                    user_id=corp_admin_approver.id, 
                    type="user_declined_approved_invitation",
                    message=notification_msg_corp_admin, 
                    reference=f"invitation:{invitation.id},email:{invitation.email}"
                )

    return declined_invitation 

@router.post("/corp-admin/direct-invite", response_model=schemas.invitation.Invitation, tags=["invitations", "corp_admin"])
async def corp_admin_direct_invite_user_to_startup(
    invite_data: schemas.invitation.CorpAdminDirectInviteCreate,
    current_user: models.User = Depends(get_current_user_with_roles(["CORP_ADMIN"])),
    db: AsyncSession = Depends(get_db),
):
    """
    Allows a Corp Admin to directly invite a user to a startup within their managed space.
    """
    if not current_user.space_id:
        logger.error(f"Corp Admin {current_user.id} attempting direct invite but is not associated with a space.")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You are not associated with a space to manage startups.")

    target_startup = await crud.crud_organization.get_startup(db, startup_id=invite_data.startup_id)
    if not target_startup:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Startup with ID {invite_data.startup_id} not found.")

    if target_startup.space_id != current_user.space_id:
        logger.warning(
            f"Corp Admin {current_user.id} (space_id: {current_user.space_id}) attempted to invite user {invite_data.email} "
            f"to startup {target_startup.id} (space_id: {target_startup.space_id}) which is not in their managed space."
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only invite users to startups within your managed space.")

    existing_user_in_startup = await crud.crud_user.get_user_by_email_and_startup(db, email=invite_data.email, startup_id=target_startup.id)
    if existing_user_in_startup:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"User with email {invite_data.email} is already a member of startup '{target_startup.name}'.")

    existing_invitation = await crud.invitation.get_by_email_and_startup(db, email=invite_data.email, startup_id=target_startup.id)
    if existing_invitation and existing_invitation.status == models.invitation.InvitationStatus.PENDING and existing_invitation.expires_at > datetime.utcnow():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"An active invitation for {invite_data.email} to join startup '{target_startup.name}' already exists.")

    invitation_create_schema = schemas.invitation.InvitationCreate(
        email=invite_data.email,
        startup_id=target_startup.id,
        approved_by_admin_id=current_user.id # The Corp Admin is the approver
    )

    try:
        invitation = await crud.invitation.create_with_startup(db, obj_in=invitation_create_schema)
        logger.info(f"Corp Admin {current_user.id} directly created invitation for {invite_data.email} to join startup {target_startup.id}. Token: {invitation.invitation_token}")
        
        send_startup_invitation_email(
            to_email=invite_data.email,
            token=invitation.invitation_token,
            startup_name=target_startup.name,
            invited_by_name=current_user.full_name or current_user.email # Corp Admin's name
        )
        
        # Notify Startup Admins of the target startup
        startup_admins_to_notify = await crud.crud_user.get_users_by_role_and_startup(db, role="STARTUP_ADMIN", startup_id=target_startup.id)
        if startup_admins_to_notify:
            for admin_to_notify in startup_admins_to_notify:
                await crud.crud_notification.create_notification(
                    db=db,
                    user_id=admin_to_notify.id,
                    type="corp_admin_direct_invite_to_startup", 
                    message=f"Corporate Admin {current_user.full_name or current_user.email} has directly invited {invite_data.email} to join your startup, {target_startup.name}.",
                    reference=f"invitation_id={invitation.id},email={invite_data.email},invited_by_corp_admin_id={current_user.id}"
                )
                logger.info(f"Sent direct invite notification to Startup Admin {admin_to_notify.id} for email {invite_data.email}, startup {target_startup.name}")
        return invitation
    except Exception as e:
        logger.error(f"Failed to create direct invitation for {invite_data.email} to startup {target_startup.id} by Corp Admin {current_user.id}: {e}")
        # Consider more specific error handling if email sending fails vs. DB creation
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create and send invitation. Please try again.") 