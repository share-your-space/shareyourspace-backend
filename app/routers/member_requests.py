from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
import logging
import re # For parsing
# from datetime import datetime # Not currently used directly

# Corrected import for the database session
from app.db.session import get_db

# Schemas used in this router
from app.schemas.member_request import MemberRequestActionResponse
# Note: List[schemas.notification.Notification] is used directly in an endpoint,
# so schemas.notification must be accessible.

# Main app components
from app import crud, schemas, models
from app.security import get_current_user_with_roles
from app.utils.email import send_startup_invitation_email # Added import

router = APIRouter()
logger = logging.getLogger(__name__) # Add logger instance

# Valid notification types for member requests that Corp Admins can action
VALID_MEMBER_REQUEST_NOTIFICATION_TYPES = ["member_request", "member_request_pending_approval"]

def parse_reference_string(reference: str) -> dict:
    """Parses a reference string, attempting comma-separated key=value first, then semicolon-separated key:value."""
    data = {}
    if not reference: 
        return data

    # Try parsing comma-separated key=value (new format)
    # Example: startup_id=3,email=user@example.com,full_name=Test User
    try:
        pairs_eq_comma = re.findall(r'([a-zA-Z_][a-zA-Z0-9_]*)=([^,]+)', reference)
        if pairs_eq_comma:
            for key, value in pairs_eq_comma:
                data[key.strip()] = value.strip()
            # If we found data with this primary method, check if essential keys are present
            if data.get("startup_id") and (data.get("email") or data.get("requested_email")):
                logger.debug(f"Parsed reference (comma-separated) '{reference}' into: {data}")
                return data
            else: # Potentially parsed something, but not the essential parts, try next method
                data = {} # Reset data if primary method didn't yield essential keys
    except Exception as e:
        logger.warning(f"Regex error parsing (comma-separated) '{reference}': {e}. Trying alternative.")
        data = {} # Reset data on error

    # Try parsing semicolon-separated key:value (potential old format)
    # Example: startup_id:3;requested_email:user@example.com
    try:
        pairs_colon_semicolon = re.findall(r'([a-zA-Z_][a-zA-Z0-9_]*):([^;]+)', reference)
        if pairs_colon_semicolon:
            for key, value in pairs_colon_semicolon:
                data[key.strip()] = value.strip()
            logger.debug(f"Parsed reference (semicolon-separated) '{reference}' into: {data}")
            return data # Return whatever was parsed by this method
    except Exception as e:
        logger.warning(f"Regex error parsing (semicolon-separated) '{reference}': {e}")
        data = {} # Reset data on error
    
    if not data:
        logger.warning(f"Could not parse reference string using known formats: {reference}")
    return data

@router.get(
    "/",
    response_model=List[schemas.notification.Notification],
    dependencies=[Depends(get_current_user_with_roles(required_roles=["CORP_ADMIN"]))],
)
async def list_pending_member_requests_for_admin(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user_with_roles(required_roles=["CORP_ADMIN"])),
):
    """
    Retrieve all pending member join requests (of valid types) for the authenticated Corporate Admin.
    """
    all_pending_requests: List[models.Notification] = [] # Explicitly type hint
    for notif_type in VALID_MEMBER_REQUEST_NOTIFICATION_TYPES:
        requests = await crud.crud_notification.get_notifications_by_type_for_user(
            db=db, user_id=current_user.id, notification_type=notif_type, is_read=False
        )
        if requests:
            all_pending_requests.extend(requests)
    
    # Sort by creation date, newest first
    all_pending_requests.sort(key=lambda x: x.created_at, reverse=True)
    return all_pending_requests

@router.put(
    "/{request_id}/approve",
    response_model=schemas.member_request.MemberRequestActionResponse,
    dependencies=[Depends(get_current_user_with_roles(required_roles=["CORP_ADMIN"]))],
)
async def approve_member_request_by_admin(
    request_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user_with_roles(required_roles=["CORP_ADMIN"])),
):
    notification = await crud.crud_notification.get_notification_by_id(db, notification_id=request_id)
    if not notification or notification.user_id != current_user.id or notification.type not in VALID_MEMBER_REQUEST_NOTIFICATION_TYPES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member request not found or not accessible.")

    if not notification.reference:
        logger.error(f"Notification {notification.id} is missing reference string.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Notification data incomplete.")

    ref_data = parse_reference_string(notification.reference)
    
    # Use "email" as the key from the new reference format
    # Fallback to "requested_email" for backward compatibility with old format if any.
    requested_email = ref_data.get("email") or ref_data.get("requested_email")
    startup_id_str = ref_data.get("startup_id")

    if not requested_email or not startup_id_str:
        logger.error(f"Failed to parse email or startup_id from reference: {notification.reference}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Invalid notification reference format.")
    
    try:
        target_startup_id = int(startup_id_str)
    except ValueError:
        logger.error(f"Invalid startup_id format in reference: {startup_id_str}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Invalid startup ID in notification reference.")

    response_message = ""
    action_status = "pending_action"

    existing_user_in_target_startup = await crud.crud_user.get_user_by_email_and_startup(db, email=requested_email, startup_id=target_startup_id)
    if existing_user_in_target_startup:
        response_message = f"User {requested_email} is already a member of startup {target_startup_id}. No further action taken."
        action_status = "no_action_needed"
    else:
        invitation_create = schemas.invitation.InvitationCreate(
            email=requested_email,
            startup_id=target_startup_id,
            approved_by_admin_id=current_user.id
        )
        try:
            invitation = await crud.invitation.create_with_startup(db, obj_in=invitation_create)
            logger.info(f"Invitation created for {requested_email} to join startup {target_startup_id}. Token: {invitation.invitation_token}")
            
            target_startup = await crud.crud_organization.get_startup(db, startup_id=target_startup_id)
            if not target_startup:
                logger.error(f"Target startup {target_startup_id} not found when sending invitation for {requested_email}.")
                action_status = "invitation_created_email_failed"
                response_message = f"Invitation created for {requested_email}, but failed to retrieve startup details for email."
            else:
                try:
                    send_startup_invitation_email(
                        to_email=requested_email,
                        token=invitation.invitation_token,
                        startup_name=target_startup.name,
                        invited_by_name=current_user.full_name or current_user.email
                    )
                    response_message = f"Invitation sent to {requested_email} to join startup {target_startup.name}."
                    action_status = "invitation_sent"
                except Exception as email_exc:
                    logger.error(f"Created invitation for {requested_email} but failed to send email: {email_exc}")
                    response_message = f"Invitation created for {requested_email}, but email sending failed. Check logs."
                    action_status = "invitation_created_email_failed"

        except Exception as e:
            logger.error(f"Failed to create invitation for {requested_email} (startup {target_startup_id}): {e}")
            response_message = f"Failed to create invitation for {requested_email}. Please try again."
            action_status = "invitation_failed"

    await crud.crud_notification.mark_notification_as_read(db, notification=notification)
    
    return schemas.member_request.MemberRequestActionResponse(
        message=response_message, 
        request_id=request_id, 
        status=action_status
    )

@router.put(
    "/{request_id}/reject",
    response_model=schemas.member_request.MemberRequestActionResponse,
    dependencies=[Depends(get_current_user_with_roles(required_roles=["CORP_ADMIN"]))],
)
async def reject_member_request_by_admin(
    request_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user_with_roles(required_roles=["CORP_ADMIN"])),
):
    notification = await crud.crud_notification.get_notification_by_id(db, notification_id=request_id)
    if not notification or notification.user_id != current_user.id or notification.type not in VALID_MEMBER_REQUEST_NOTIFICATION_TYPES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member request not found or not accessible.")

    target_startup_id_for_notification = None
    if notification.reference:
        ref_data = parse_reference_string(notification.reference)
        requested_email = ref_data.get("email") or ref_data.get("requested_email", "[unknown email]")
        startup_id_str = ref_data.get("startup_id")
        startup_name = "[unknown startup]"
        if startup_id_str and startup_id_str.isdigit():
            target_startup_id_for_notification = int(startup_id_str)
            target_startup = await crud.crud_organization.get_startup(db, startup_id=target_startup_id_for_notification)
            if target_startup: 
                startup_name = target_startup.name
    else:
        requested_email = "[unknown email due to missing reference]"
        startup_name = "[unknown startup due to missing reference]"

    await crud.crud_notification.mark_notification_as_read(db, notification=notification)
    
    # Notify the Startup Admin(s) who originally requested (if applicable)
    if notification.type == "member_request_pending_approval" and target_startup_id_for_notification:
        startup_admins_to_notify = await crud.crud_user.get_users_by_role_and_startup(
            db, role="STARTUP_ADMIN", startup_id=target_startup_id_for_notification
        )
        for admin_to_notify in startup_admins_to_notify:
            await crud.crud_notification.create_notification_for_user(
                db,
                user_id=admin_to_notify.id,
                title=f"Member Request Rejected: {requested_email}",
                message=f"Your request to add member {requested_email} to startup '{startup_name}' was rejected by Corporate Admin {current_user.full_name or current_user.email}.",
                notification_type="startup_member_request_rejected",
                reference=f"rejected_email={requested_email},startup_id={target_startup_id_for_notification}" # Reference for the new notification
            )
            logger.info(f"Sent rejection notification to Startup Admin {admin_to_notify.id} for email {requested_email}, startup {startup_name}")

    logger.info(f"Corp Admin {current_user.id} (Notification ID: {request_id}) rejected request for {requested_email} to join {startup_name}.")

    return schemas.member_request.MemberRequestActionResponse(
        message=f"Request to add {requested_email} to startup {startup_name} has been rejected.", 
        request_id=request_id, 
        status="rejected"
    )
