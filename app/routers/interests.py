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
    response_model=schemas.interest.Interest,
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
    dependencies=[Depends(get_current_user_with_roles(required_roles=["CORP_ADMIN"]))],
)
async def accept_interest(
    interest_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Accept an interest request, adding the user or startup to the space.
    """
    interest = await db.get(models.Interest, interest_id, options=[selectinload(models.Interest.user), selectinload(models.Interest.space)])
    if not interest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interest not found")

    managed_space = await crud.crud_space.get_managed_space(db, current_user)
    if not managed_space or managed_space.id != interest.space_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to accept this interest")

    user_to_add = interest.user
    if not user_to_add:
         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User associated with interest not found")

    if user_to_add.role == UserRole.FREELANCER:
        user_update = UserUpdateInternal(status=UserStatus.ACTIVE, space_id=managed_space.id)
        await crud.crud_user.update_user_internal(db=db, db_obj=user_to_add, obj_in=user_update)
    elif user_to_add.role == UserRole.STARTUP_ADMIN:
        if not user_to_add.startup_id:
            raise HTTPException(status_code=400, detail="Startup admin is not associated with any startup.")
        startup = await crud.crud_organization.get_startup(db, startup_id=user_to_add.startup_id, options=[selectinload(models.Startup.direct_members)])
        if not startup:
            raise HTTPException(status_code=404, detail="Startup not found")
        
        await crud.crud_organization.add_startup_to_space(db, startup=startup, space_id=managed_space.id)

    # Update interest status
    interest_update = interest_schema.InterestUpdate(status=models.interest.InterestStatus.ACCEPTED)
    await crud.crud_interest.interest.update(db, db_obj=interest, obj_in=interest_update)

    # Automatically create a connection between the new user and the space admin
    try:
        await crud.crud_connection.create_accepted_connection(
            db, user_one_id=user_to_add.id, user_two_id=current_user.id
        )
        logger.info(f"Successfully created an accepted connection between new user {user_to_add.email} and space admin {current_user.email}.")
    except Exception as e:
        logger.error(f"Failed to create automatic connection for user {user_to_add.email} and admin {current_user.email}. Error: {e}", exc_info=True)

    # Update conversations to not be external
    conversations = await crud.crud_chat.get_conversations_between_users(
        db, user1_id=current_user.id, user2_id=user_to_add.id
    )
    for conv in conversations:
        if conv.is_external:
            conv.is_external = False
            db.add(conv)
    
    await db.commit()

    return {"message": "Interest accepted successfully and user has been added to the space."} 

@router.get("/space/{space_id}/status", response_model=schemas.interest.InterestStatusResponse)
async def get_interest_status(
    space_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Check if the current user has expressed interest in a space.
    """
    interest = await crud.crud_interest.interest.get_by_user_and_space(db, user_id=current_user.id, space_id=space_id)
    return {"has_expressed_interest": interest is not None} 