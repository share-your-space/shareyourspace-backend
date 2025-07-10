from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, UploadFile, status
from typing import Optional
import logging
import uuid

from app import crud, models, schemas
from app.utils.storage import gcs_storage
from app.schemas.user_profile import UserProfileUpdate

logger = logging.getLogger(__name__)

async def get_user_details(db: AsyncSession, user_id: int) -> Optional[models.User]:
    """
    Fetches user details and generates signed URLs for profile pictures and cover photos.
    """
    user = await crud.crud_user.get_user_details_for_profile(db, user_id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.profile:
        if user.profile.profile_picture_url:
            try:
                user.profile.profile_picture_signed_url = gcs_storage.generate_signed_url(user.profile.profile_picture_url)
            except Exception as e:
                logger.error(f"Failed to generate signed URL for profile picture for user {user.id}: {e}")
                user.profile.profile_picture_signed_url = None

        if user.profile.cover_photo_url:
            try:
                user.profile.cover_photo_signed_url = gcs_storage.generate_signed_url(user.profile.cover_photo_url)
            except Exception as e:
                logger.error(f"Failed to generate signed URL for cover photo for user {user.id}: {e}")
                user.profile.cover_photo_signed_url = None
    
    return user

async def _upload_and_update_user_photo(
    db: AsyncSession, 
    user: models.User, 
    file: UploadFile, 
    photo_type: str
):
    """
    Helper function to upload a photo, update the user's profile, and handle old photo deletion.
    """
    if not user.profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User profile not found")

    old_photo_url = getattr(user.profile, f"{photo_type}_url", None)
    
    folder = "profile_pictures" if photo_type == "profile_picture" else "cover_photos"
    
    uploaded_blob_name = None
    try:
        # Sanitize filename
        safe_filename = f"{uuid.uuid4()}_{file.filename.replace(' ', '_')}"
        blob_name = f"{folder}/{user.id}/{safe_filename}"
        
        uploaded_blob_name = await gcs_storage.upload_file_async(
            file=file,
            blob_name=blob_name,
            content_type=file.content_type
        )
        
        # Update profile with new blob name
        profile_update_data = UserProfileUpdate(**{f"{photo_type}_url": uploaded_blob_name})
        
        updated_profile = await update_user_profile(db=db, user=user, profile_in=profile_update_data)

        # Delete the old photo from GCS after the new one is confirmed
        if old_photo_url:
            try:
                gcs_storage.delete_blob(old_photo_url)
            except Exception as e:
                logger.error(f"Failed to delete old {photo_type} {old_photo_url} from GCS: {e}")

        return updated_profile

    except Exception as e:
        logger.error(f"Error during {photo_type} upload for user {user.id}: {e}", exc_info=True)
        # Attempt to delete the newly uploaded file if the process fails
        if uploaded_blob_name:
            try:
                gcs_storage.delete_blob(uploaded_blob_name)
            except Exception as del_e:
                logger.error(f"Failed to clean up failed upload {uploaded_blob_name}: {del_e}")
        raise HTTPException(status_code=500, detail=f"Failed to upload {photo_type}.")


async def upload_profile_picture(db: AsyncSession, user: models.User, file: UploadFile):
    return await _upload_and_update_user_photo(db, user, file, "profile_picture")

async def upload_cover_photo(db: AsyncSession, user: models.User, file: UploadFile):
    return await _upload_and_update_user_photo(db, user, file, "cover_photo")

async def update_user_profile(
    db: AsyncSession,
    user: models.User,
    profile_in: schemas.UserProfileUpdate,
) -> models.UserProfile:
    logger.info(f"--- Updating User Profile for User ID: {user.id} ---")
    logger.info(f"Incoming update data: {profile_in.model_dump_json(exclude_unset=True)}")
    if not user.profile:
        logger.warning(f"User {user.id} has no profile, creating one.")
        new_profile = await crud.crud_user_profile.create_with_owner(
            db=db, obj_in=profile_in, user_id=user.id
        )
        return new_profile

    update_data = profile_in.model_dump(exclude_unset=True)

    if not update_data:
        logger.warning("Update called with no data to update.")
        return user.profile

    logger.info(f"Calling CRUD to update profile. Data: {update_data}")
    updated_profile = await crud.crud_user_profile.update_profile_with_embedding_generation(
        db=db, db_obj=user.profile, obj_in=profile_in
    )
    logger.info(f"--- User Profile Update Finished for User ID: {user.id} ---")

    return updated_profile