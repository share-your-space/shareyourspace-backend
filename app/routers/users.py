from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
import uuid
import datetime
from fastapi.responses import StreamingResponse # Import StreamingResponse
import io # Import io for streaming
import logging # Import logging

from app import models, security
from app.schemas.user import User as UserSchema
# Import profile schemas and crud functions
from app.schemas.user_profile import UserProfile as UserProfileSchema, UserProfileUpdate
from app.crud import crud_user_profile
from app.db.session import get_db
from app.utils import storage # Import storage utility
from app.utils.embeddings import generate_embedding # Import embedding utility

router = APIRouter()
logger = logging.getLogger(__name__) # Add logger


@router.get("/me", response_model=UserSchema)
async def read_users_me(
    current_user: models.User = Depends(security.get_current_user),
):
    """
    Fetch the details of the currently authenticated user.
    Requires only a valid token, not necessarily ACTIVE status.
    """
    # The dependency already fetches and validates the user
    return current_user

@router.get("/me/profile", response_model=UserProfileSchema)
async def read_my_profile(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(security.get_current_user),
):
    """Fetch the profile of the currently authenticated user.
    Returns profile data including a temporary signed URL for the profile picture.
    Requires only a valid token.
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
    current_user: models.User = Depends(security.get_current_user),
):
    """Update the profile of the currently authenticated user.
    If profile doesn't exist, it will be created.
    Generates and stores profile embedding vector on successful update.
    Returns updated profile data including the blob name.
    Requires only a valid token.
    """
    profile_db = await crud_user_profile.get_profile_by_user_id(db, user_id=current_user.id)
    if not profile_db:
        profile_db = await crud_user_profile.create_profile_for_user(db, user_id=current_user.id)

    # Update standard profile fields first
    updated_profile_db = await crud_user_profile.update_profile(
        db=db, db_obj=profile_db, obj_in=profile_in
    )
    
    # --- Generate and Save Embedding --- 
    try:
        # 1. Construct text input for embedding
        # Combine relevant text fields. Ensure None values are handled gracefully.
        text_parts = [
            updated_profile_db.title or "",
            updated_profile_db.bio or "",
            "Skills: " + ", ".join(updated_profile_db.skills_expertise or []),
            "Industry: " + ", ".join(updated_profile_db.industry_focus or []),
            "Goals: " + (updated_profile_db.project_interests_goals or ""),
            "Collaboration: " + ", ".join(updated_profile_db.collaboration_preferences or []),
            "Tools: " + ", ".join(updated_profile_db.tools_technologies or []),
        ]
        combined_text = "\n".join(filter(None, text_parts)) # Join non-empty parts
        logger.info(f"Generating embedding for user {current_user.id} based on text: {combined_text[:200]}...") # Log beginning of text

        # 2. Generate embedding
        embedding_vector = None
        if combined_text:
             embedding_vector = generate_embedding(combined_text)

        # 3. Save embedding (if generated successfully)
        if embedding_vector:
            logger.info(f"Embedding generated successfully for user {current_user.id}. Saving...")
            updated_profile_db.profile_vector = embedding_vector
            db.add(updated_profile_db) # Add to session again to include vector update
            await db.commit() # Commit the vector update
            await db.refresh(updated_profile_db) # Refresh to get the latest state including vector
            logger.info(f"Embedding vector saved for user {current_user.id}.")
        else:
            logger.warning(f"Embedding vector generation failed or text was empty for user {current_user.id}. Vector not saved.")

    except Exception as e:
        await db.rollback() # Rollback embedding commit on error
        logger.error(f"Error during embedding generation/saving for user {current_user.id}: {e}", exc_info=True)
        # Decide if this error should fail the whole request or just be logged
        # For now, let's log it but allow the profile update to succeed without the vector
        pass 
    # --- End Embedding Generation --- 

    # Convert final DB model (potentially with vector) to Pydantic schema for response
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
            logger.error(f"Error generating signed URL after update for {updated_profile_db.profile_picture_url}: {e}", exc_info=True) # Use logger

    updated_profile_data.profile_picture_signed_url = signed_url

    return updated_profile_data

@router.post("/me/profile/picture", response_model=UserProfileSchema)
async def upload_my_profile_picture(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(security.get_current_user),
):
    """Upload a profile picture for the currently authenticated user.
    Saves the blob name and returns the updated profile.
    Requires only a valid token.
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

# --- Endpoint to view OTHER users' profiles --- 
@router.get("/{user_id}/profile", response_model=UserProfileSchema)
async def read_user_profile(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(security.get_current_user), # Get current user to check relationship
):
    """Fetch the profile of a specific user by their ID.
    
    TODO: Implement privacy controls based on connection status and user settings.
    For now, returns most profile data but excludes sensitive details if not connected.
    """
    if user_id == current_user.id:
        # Redirect or call the "/me/profile" logic? For simplicity, let's call it.
        return await read_my_profile(db=db, current_user=current_user)

    # Fetch the target user's profile
    profile_db = await crud_user_profile.get_profile_by_user_id(db, user_id=user_id)
    if not profile_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User profile not found.")

    # Fetch the target user model as well (needed for relationship check, etc.)
    # target_user = await crud_user.get_user_by_id(db, user_id=user_id) # Assuming this exists
    # if not target_user:
    #     raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    # --- Privacy Check Logic (Basic MVP Implementation) --- 
    # Check connection status between current_user and target_user (user_id)
    # connection = await crud_connection.get_connection_between_users(db, user1_id=current_user.id, user2_id=user_id) # Assuming this exists
    # is_connected = connection and connection.status == 'accepted'
    
    # For now, let's assume we return the same profile data regardless of connection
    # We can add filtering later based on `is_connected` or `profile_db.contact_info_visibility`
    profile_data = UserProfileSchema.from_orm(profile_db)

    # --- Generate Signed URL --- 
    signed_url = None
    if profile_db.profile_picture_url and storage.GCS_BUCKET:
        try:
            blob = storage.GCS_BUCKET.blob(profile_db.profile_picture_url)
            signed_url = blob.generate_signed_url(
                version="v4",
                expiration=datetime.timedelta(hours=1),
                method="GET",
            )
        except Exception as e:
            logger.error(f"Error generating signed URL for user {user_id} profile pic {profile_db.profile_picture_url}: {e}", exc_info=True)

    profile_data.profile_picture_signed_url = signed_url

    return profile_data

# Add other user-related endpoints here later (e.g., update profile) 