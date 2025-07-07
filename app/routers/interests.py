import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import selectinload
from fastapi.responses import JSONResponse

from app import models, schemas, crud, services
from app.crud import crud_notification
from app.security import get_current_active_user
from app.db.session import get_db
from app.models.enums import NotificationType, UserStatus, UserRole
from app.crud.crud_interest import interest as crud_interest
from app.security import get_current_user_with_roles
from app.schemas import interest as interest_schema
from app.schemas.user import UserUpdateInternal
from app.dependencies import get_current_active_user

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post(
    "/space/{space_id}/express",
    response_model=schemas.interest.InterestWithUserDetails,
    status_code=status.HTTP_201_CREATED,
    summary="Express interest in a space",
    description="Allows a user (freelancer or startup admin) to express interest in joining a specific space.",
)
async def express_interest_in_space(
    space_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Allows a user to express interest in a space, creating an Interest object
    and notifying the space admin.
    """
    interest = await services.interest_service.express_interest(db=db, space_id=space_id, current_user=current_user)
    return interest

@router.post(
    "/{interest_id}/accept",
    response_model=schemas.Message,
    status_code=status.HTTP_200_OK,
    summary="Accept an invitation to join a space",
    description="Allows a freelancer or startup admin to accept an invitation from a corporate admin.",
)
async def accept_invitation(
    interest_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Accept an invitation, adding the user or startup to the space.
    """
    await services.interest_service.accept_invitation(
        db=db, interest_id=interest_id, current_user=current_user
    )
    return {"message": "Invitation accepted. Welcome to the space!"} 