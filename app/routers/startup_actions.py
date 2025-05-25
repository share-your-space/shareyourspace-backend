from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
import logging
from datetime import datetime

from app import crud, models, schemas
from app.db.session import get_db
from app.security import get_current_user_with_roles

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/request-member", response_model=schemas.message.Message, status_code=status.HTTP_202_ACCEPTED)
async def request_new_member_for_startup(
    member_request_data: schemas.member_request.StartupMemberRequestCreate,
    current_user: models.User = Depends(get_current_user_with_roles(["STARTUP_ADMIN"])),
    db: AsyncSession = Depends(get_db),
):
    """
    Allows a Startup Admin to request the addition of a new member to their startup.
    This will create a notification for Corp Admins of the space to approve.
    """
    if not current_user.startup_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is not associated with a startup.")

    startup = await crud.crud_organization.get_startup(db, startup_id=current_user.startup_id)
    if not startup:
        logger.error(f"Startup {current_user.startup_id} not found for Startup Admin {current_user.id}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Associated startup not found.")

    if not startup.space_id:
        logger.error(f"Startup {startup.id} (name: {startup.name}) is not associated with any space.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Startup is not part of a space, cannot process member request.")

    # Check if user with this email already exists and is part of *this* startup
    existing_user_in_startup = await crud.crud_user.get_user_by_email_and_startup(db, email=member_request_data.email, startup_id=startup.id)
    if existing_user_in_startup:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"User with email {member_request_data.email} is already a member of your startup.")

    # Check if an active invitation already exists for this email and startup
    # (created by a corp admin previously, or via another startup admin request)
    existing_invitation = await crud.invitation.get_by_email_and_startup(
        db, email=member_request_data.email, startup_id=startup.id
    )
    if existing_invitation and existing_invitation.status == models.invitation.InvitationStatus.PENDING and existing_invitation.expires_at > datetime.utcnow():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"An active invitation for {member_request_data.email} to join your startup already exists.")


    corp_admins_in_space = await crud.crud_user.get_users_by_role_and_space_id(
        db, role="CORP_ADMIN", space_id=startup.space_id
    )

    if not corp_admins_in_space:
        logger.warning(f"No Corp Admins found for space {startup.space_id} to handle member request for startup {startup.id}. Request cannot be processed.")
        # Depending on policy, this could be an error or the request could be queued differently.
        # For now, returning an error as no one can approve it.
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="No corporate administrators available in the space to approve this request.")

    notification_title = f"Member Request: {startup.name}"
    message_detail = f"Startup '{startup.name}' requests to add member: {member_request_data.email}"
    if member_request_data.full_name:
        message_detail += f" (Name: {member_request_data.full_name})"
    message_detail += ". Please review and approve or reject this request."
    
    # Using a structured reference for easier parsing later by Corp Admin when approving
    reference_payload = f"startup_id={startup.id},email={member_request_data.email}"
    if member_request_data.full_name:
        reference_payload += f",full_name={member_request_data.full_name}"

    for corp_admin in corp_admins_in_space:
        await crud.crud_notification.create_notification_for_user(
            db,
            user_id=corp_admin.id,
            title=notification_title,
            message=message_detail,
            notification_type="member_request_pending_approval",
            reference=reference_payload 
        )
        logger.info(f"Sent member request notification to Corp Admin {corp_admin.id} for startup {startup.id}, email {member_request_data.email}")

    return schemas.message.Message(message="Member addition request submitted successfully. It will be reviewed by a Corporate Administrator.") 