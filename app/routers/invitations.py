from fastapi import APIRouter, Depends, status
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from app import models, schemas, services
from app.db.session import get_db
from app.dependencies import get_current_user_with_roles, get_current_active_user

router = APIRouter()

@router.post("/request", status_code=status.HTTP_202_ACCEPTED)
async def request_invitation(
    request_data: schemas.organization.InvitationRequest, 
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Handles a user's request for an invitation to an organization."""
    await services.invitation_service.request_invitation(
        db, request_data=request_data, current_user=current_user
    )
    return {"message": "Your request for an invitation has been sent."}

@router.get("/{invitation_token}/details", response_model=schemas.invitation.InvitationDetails)
async def get_invitation_details(
    invitation_token: str,
    db: AsyncSession = Depends(get_db),
):
    """Public endpoint to get basic details about an invitation."""
    return await services.invitation_service.get_invitation_details(db, token=invitation_token)

@router.post("/invite", response_model=schemas.invitation.Invitation)
async def create_invitation(
    invite_data: schemas.invitation.UnifiedInvitationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user_with_roles(["CORP_ADMIN", "STARTUP_ADMIN"])),
):
    """Creates an invitation for a user to join a startup."""
    return await services.invitation_service.create_startup_invitation(
        db, invite_data=invite_data, current_user=current_user
    )

@router.post("/accept/{invitation_token}", response_model=schemas.token.TokenWithUser)
async def accept_invitation(
    invitation_token: str,
    user_create_data: schemas.user.UserCreateAcceptInvitation,
    db: AsyncSession = Depends(get_db),
):
    """Accept an invitation to join an organization."""
    return await services.invitation_service.accept_invitation(
        db, token=invitation_token, user_data=user_create_data
    )

@router.get("/startup/pending", response_model=schemas.invitation.InvitationListResponse)
async def list_pending_invitations_for_startup(
    current_user: models.User = Depends(get_current_user_with_roles(["STARTUP_ADMIN"])),
    db: AsyncSession = Depends(get_db),
):
    """Lists all pending invitations for the current startup admin's startup."""
    if not current_user.startup_id:
        raise HTTPException(status_code=403, detail="User not associated with a startup.")
    
    invitations = await crud.invitation.get_pending_invitations_for_startup(db, startup_id=current_user.startup_id)
    return {"invitations": invitations}

@router.put("/{invitation_id}/revoke", response_model=schemas.invitation.Invitation)
async def revoke_startup_invitation(
    invitation_id: int,
    current_user: models.User = Depends(get_current_user_with_roles(["STARTUP_ADMIN"])),
    db: AsyncSession = Depends(get_db),
):
    """Revokes a pending invitation."""
    return await services.invitation_service.revoke_invitation(
        db, invitation_id=invitation_id, current_user=current_user
    )

@router.post("/decline/{invitation_token}", response_model=schemas.invitation.Invitation)
async def decline_startup_invitation(
    invitation_token: str,
    decline_data: schemas.invitation.InvitationDecline = None,
    db: AsyncSession = Depends(get_db),
):
    """Allows a user to decline a pending startup invitation."""
    reason = decline_data.reason if decline_data else None
    return await services.invitation_service.decline_invitation(db, token=invitation_token, reason=reason) 