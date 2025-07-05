from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from app import models, schemas, services
from app.db.session import get_db
from app.dependencies import get_current_active_user
from app.schemas.user_profile import UserProfileUpdate
from app.schemas.message import Message

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/me", response_model=schemas.user.UserDetail)
async def read_current_user_profile(
    current_user: models.User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get the detailed profile for the currently authenticated user.
    """
    return await services.user_service.get_user_details(db, user_id=current_user.id)

@router.put("/me", response_model=schemas.user_profile.UserProfile)
async def update_current_user_profile(
    profile_in: UserProfileUpdate,
    current_user: models.User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update the profile for the currently authenticated user.
    """
    return await services.user_service.update_user_profile(
        db=db, user=current_user, profile_in=profile_in
    )

@router.post("/me/picture", response_model=schemas.user_profile.UserProfile)
async def upload_current_user_profile_picture(
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Upload a new profile picture for the current user.
    """
    return await services.user_service.upload_profile_picture(db=db, user=current_user, file=file)

@router.post("/me/cover-photo", response_model=schemas.user_profile.UserProfile)
async def upload_current_user_cover_photo(
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Upload a new cover photo for the current user.
    """
    return await services.user_service.upload_cover_photo(db=db, user=current_user, file=file)

@router.get("/{user_id}", response_model=schemas.user.UserDetail)
async def read_user_profile_by_id(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Fetch the detailed profile of a specific user by their ID.
    TODO: Implement privacy controls.
    """
    # Simple check to prevent fetching other users if not intended
    # A more robust ACL/permission system would be needed for production
    if user_id != current_user.id and current_user.role not in ["ADMIN", "CORP_ADMIN"]:
         # Allowing admins to view for now, this should be a proper permission
        pass # Or raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")
    
    return await services.user_service.get_user_details(db, user_id=user_id)

@router.post("/{user_id}/initiate-contact", response_model=Message)
async def initiate_contact_with_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Creates a notification for a user to initiate contact.
    This logic can be moved to a `notification_service` in the future.
    """
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot initiate contact with yourself.")

    target_user = await crud.crud_user.get_user_by_id(db, user_id=user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="Target user not found.")

    space_name = "their space"
    if current_user.role == 'CORP_ADMIN' and current_user.managed_space:
        space_name = f"the '{current_user.managed_space.name}' space"

    message = f"{current_user.full_name or 'A corporate admin'} from {space_name} would like to discuss having you join their space."

    await crud.crud_notification.create_notification(
        db=db,
        user_id=target_user.id,
        type=models.enums.NotificationType.INTEREST_EXPRESSED,
        message=message,
        related_entity_id=current_user.id,
        link=f"/chat?with={current_user.id}"
    )

    return {"message": "Contact initiation notification sent successfully."} 