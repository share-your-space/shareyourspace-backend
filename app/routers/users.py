from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
import uuid
import datetime
from fastapi.responses import StreamingResponse # Import StreamingResponse
import io # Import io for streaming

from app import models, security
from app.schemas.user import User as UserSchema
# Import profile schemas and crud functions
from app.schemas.user_profile import UserProfile as UserProfileSchema, UserProfileUpdate
from app.crud import crud_user_profile
from app.db.session import get_db
from app.utils import storage # Import storage utility

router = APIRouter()


@router.get("/me", response_model=UserSchema)
async def read_users_me(
    current_user: models.User = Depends(security.get_current_active_user),
):
    """
    Fetch the details of the currently authenticated user.
    """
    # The dependency already fetches and validates the user
    return current_user

@router.get("/me/profile", response_model=UserProfileSchema)
async def read_my_profile(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(security.get_current_active_user),
):
    """Fetch the profile of the currently authenticated user.
    Returns profile data including a temporary signed URL for the profile picture.
    """
    profile_db = await crud_user_profile.get_profile_by_user_id(db, user_id=current_user.id)
    if not profile_db:
        profile_db = await crud_user_profile.create_profile_for_user(db, user_id=current_user.id)

    # Convert DB model to Pydantic schema
    profile_data = UserProfileSchema.from_orm(profile_db)

    # Generate signed URL if profile picture exists
    signed_url = None
    if profile_db.profile_picture_url and storage.GCS_BUCKET:
        try:
            blob = storage.GCS_BUCKET.blob(profile_db.profile_picture_url)
            signed_url = blob.generate_signed_url(
                version="v4",
                # URL expires in 1 hour
                expiration=datetime.timedelta(hours=1),
                method="GET",
            )
        except Exception as e:
            # Log error but don't fail the request
            print(f"Error generating signed URL for {profile_db.profile_picture_url}: {e}") # Replace with logger

    # Add the signed URL to the response object (even if None)
    profile_data.profile_picture_signed_url = signed_url

    return profile_data

@router.put("/me/profile", response_model=UserProfileSchema)
async def update_my_profile(
    profile_in: UserProfileUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(security.get_current_active_user),
):
    """Update the profile of the currently authenticated user.
    Returns updated profile data including the blob name.
    """
    profile_db = await crud_user_profile.get_profile_by_user_id(db, user_id=current_user.id)
    if not profile_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found. Cannot update.",
        )

    updated_profile_db = await crud_user_profile.update_profile(
        db=db, db_obj=profile_db, obj_in=profile_in
    )

    # Convert DB model to Pydantic schema for response
    updated_profile_data = UserProfileSchema.from_orm(updated_profile_db)

    # Generate signed URL for the potentially updated picture
    signed_url = None
    if updated_profile_db.profile_picture_url and storage.GCS_BUCKET:
        try:
            blob = storage.GCS_BUCKET.blob(updated_profile_db.profile_picture_url)
            signed_url = blob.generate_signed_url(
                version="v4",
                expiration=datetime.timedelta(hours=1),
                method="GET",
            )
        except Exception as e:
            print(f"Error generating signed URL after update for {updated_profile_db.profile_picture_url}: {e}") # Replace with logger

    updated_profile_data.profile_picture_signed_url = signed_url

    return updated_profile_data

@router.post("/me/profile/picture", response_model=UserProfileSchema)
async def upload_my_profile_picture(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(security.get_current_active_user),
):
    """Upload a profile picture for the currently authenticated user.
    Saves the blob name and returns the updated profile.
    """
    profile_db = await crud_user_profile.get_profile_by_user_id(db, user_id=current_user.id)
    if not profile_db:
        profile_db = await crud_user_profile.create_profile_for_user(db, user_id=current_user.id)

    # Generate unique blob name
    file_extension = file.filename.split('.')[-1] if '.' in file.filename else 'jpg'
    unique_filename = f"user_{current_user.id}_profile_{uuid.uuid4()}.{file_extension}"
    destination_blob_name = f"profile_pictures/{unique_filename}"

    # Upload file to GCS - returns blob name on success
    blob_name = storage.upload_file(file=file, destination_blob_name=destination_blob_name)

    if not blob_name:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload profile picture.",
        )

    # Update profile with the new blob name
    profile_update_data = UserProfileUpdate(profile_picture_url=blob_name)
    updated_profile_db = await crud_user_profile.update_profile(
        db=db, db_obj=profile_db, obj_in=profile_update_data
    )

    # Convert DB model to Pydantic schema for response
    profile_data = UserProfileSchema.from_orm(updated_profile_db)

    # Generate signed URL for the *newly* uploaded picture
    signed_url = None
    if updated_profile_db.profile_picture_url and storage.GCS_BUCKET:
        try:
            blob = storage.GCS_BUCKET.blob(updated_profile_db.profile_picture_url)
            signed_url = blob.generate_signed_url(
                version="v4",
                expiration=datetime.timedelta(hours=1),
                method="GET",
            )
        except Exception as e:
            print(f"Error generating signed URL after upload for {updated_profile_db.profile_picture_url}: {e}") # Replace with logger

    profile_data.profile_picture_signed_url = signed_url

    return profile_data

# Add other user-related endpoints here later (e.g., update profile) 