import logging
import uuid
from fastapi import HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud, models, schemas
from app.schemas.user_profile import UserProfileUpdate
from app.utils import storage

logger = logging.getLogger(__name__)


async def get_user_details(db: AsyncSession, user_id: int) -> schemas.user.UserDetail:
    """
    Fetches a user's detailed profile and generates a signed URL for the profile picture.
    Returns a Pydantic schema object ready for the API response.
    """
    user_db = await crud.crud_user.get_user_details_for_profile(db, user_id=user_id)
    if not user_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user_detail_schema = schemas.user.UserDetail.model_validate(user_db)

    if user_db.profile and user_db.profile.profile_picture_url:
        try:
            signed_url = storage.generate_gcs_signed_url(blob_name=user_db.profile.profile_picture_url)
            if user_detail_schema.profile:
                user_detail_schema.profile.profile_picture_signed_url = signed_url
        except Exception as e:
            logger.error(f"Failed to generate signed URL for user {user_id}: {e}", exc_info=True)

    return user_detail_schema


async def update_user_profile(
    db: AsyncSession, *, user: models.User, profile_in: UserProfileUpdate
) -> schemas.user_profile.UserProfile:
    """
    Updates a user's profile and returns the updated profile as a Pydantic schema
    with a signed URL for the profile picture.
    """
    db_profile = await crud.crud_user_profile.get_profile_by_user_id(db, user_id=user.id)
    if not db_profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found for this user.")

    updated_profile = await crud.crud_user_profile.update_profile(db=db, db_obj=db_profile, obj_in=profile_in)
    
    profile_schema = schemas.user_profile.UserProfile.model_validate(updated_profile)
    profile_schema.full_name = user.full_name
    
    if updated_profile.profile_picture_url:
        try:
            signed_url = storage.generate_gcs_signed_url(blob_name=updated_profile.profile_picture_url)
            profile_schema.profile_picture_signed_url = signed_url
        except Exception as e:
            logger.error(f"Failed to generate signed URL for updated profile picture for user {user.id}: {e}", exc_info=True)
            
    if updated_profile.cover_photo_url:
        try:
            signed_url = storage.generate_gcs_signed_url(blob_name=updated_profile.cover_photo_url)
            profile_schema.cover_photo_signed_url = signed_url
        except Exception as e:
            logger.error(f"Failed to generate signed URL for updated cover photo for user {user.id}: {e}", exc_info=True)

    return profile_schema


async def upload_profile_picture(
    db: AsyncSession, *, user: models.User, file: UploadFile
) -> schemas.user_profile.UserProfile:
    """
    Uploads a profile picture, updates the user's profile, deletes the old picture,
    and returns the updated profile schema.
    """
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No filename provided.")

    file_extension = file.filename.split('.')[-1] if '.' in file.filename else 'png'
    unique_filename = f"{uuid.uuid4()}.{file_extension}"
    destination_blob_name = f"profile_pictures/{user.id}/{unique_filename}"

    db_profile = await crud.crud_user_profile.get_profile_by_user_id(db, user_id=user.id)
    if not db_profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found.")

    old_blob_name = db_profile.profile_picture_url
    uploaded_blob_name = None

    try:
        uploaded_blob_name = await run_in_threadpool(
            storage.upload_file_to_gcs, file=file, destination_blob_name=destination_blob_name
        )
        if not uploaded_blob_name:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Profile picture upload failed.")

        profile_update_data = UserProfileUpdate(profile_picture_url=uploaded_blob_name)
        updated_profile_model = await crud.crud_user_profile.update_profile(db=db, db_obj=db_profile, obj_in=profile_update_data)

        if old_blob_name and old_blob_name != uploaded_blob_name:
            await run_in_threadpool(storage.delete_gcs_blob, blob_name=old_blob_name)
        
        return await update_user_profile(db, user=user, profile_in=UserProfileUpdate())

    except Exception as e:
        logger.error(f"Error during profile picture upload for user {user.id}: {e}", exc_info=True)
        if uploaded_blob_name:
            await run_in_threadpool(storage.delete_gcs_blob, blob_name=uploaded_blob_name)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not upload profile picture.")


async def upload_cover_photo(
    db: AsyncSession, *, user: models.User, file: UploadFile
) -> schemas.user_profile.UserProfile:
    """
    Uploads a cover photo, updates the user's profile, and returns the updated profile.
    """
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No filename provided.")

    destination_blob_name = f"cover_photos/{user.id}/{uuid.uuid4()}_{file.filename}"
    
    db_profile = await crud.crud_user_profile.get_profile_by_user_id(db, user_id=user.id)
    if not db_profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found.")

    old_blob_name = db_profile.cover_photo_url
    
    try:
        uploaded_blob_name = await run_in_threadpool(
            storage.upload_file_to_gcs, file=file, destination_blob_name=destination_blob_name
        )
        if not uploaded_blob_name:
            raise HTTPException(status_code=500, detail="Cover photo upload failed.")

        profile_update = UserProfileUpdate(cover_photo_url=uploaded_blob_name)
        await crud.crud_user_profile.update_profile(db, db_obj=db_profile, obj_in=profile_update)

        if old_blob_name:
            await run_in_threadpool(storage.delete_gcs_blob, blob_name=old_blob_name)
            
        return await update_user_profile(db, user=user, profile_in=UserProfileUpdate())
    except Exception as e:
        logger.error(f"Error during cover photo upload for user {user.id}: {e}")
        if 'uploaded_blob_name' in locals() and uploaded_blob_name:
            await run_in_threadpool(storage.delete_gcs_blob, blob_name=uploaded_blob_name)
        raise HTTPException(status_code=500, detail="An error occurred during file upload.") 