from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select # Add select
from sqlalchemy.orm import selectinload # Add selectinload
import uuid
import datetime
from fastapi.responses import StreamingResponse, JSONResponse # Import StreamingResponse and JSONResponse
import io # Import io for streaming
import logging # Import logging
from fastapi.concurrency import run_in_threadpool # Ensure this is imported at the top if not already
from fastapi.encoders import jsonable_encoder

from app import models, security, crud # Ensure crud is imported
from app.schemas.user import User as UserSchema, UserDetail as UserDetailSchema # Import UserDetailSchema
# Import profile schemas and crud functions
from app.schemas.user_profile import UserProfile as UserProfileSchema, UserProfileUpdate
from app.crud import crud_user_profile
from app.crud import crud_user # Add this line
from app.db.session import get_db
from app.utils import storage # Import storage utility
from app.utils.embeddings import generate_embedding # Import embedding utility
from app.models.space import WorkstationAssignment, SpaceNode # Import WorkstationAssignment for type hint/logic and SpaceNode
from app.security import get_current_user
from app.utils.storage import generate_gcs_signed_url, upload_file_to_gcs # Add upload_file_to_gcs
from app.models.profile import UserProfile # Ensure UserProfile model is imported
from app.schemas.space import UserWorkstationInfo
from app.schemas.message import Message
from app.models.enums import NotificationType
# Import schemas for manual construction
from app.schemas.space import BasicSpace
from app.schemas.organization import Company as CompanySchema, Startup as StartupSchema
from app.dependencies import get_current_active_user

router = APIRouter()
logger = logging.getLogger(__name__) # Add logger


@router.get("/me", response_model=UserDetailSchema)
async def read_users_me(
    current_user: models.User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get current user's detailed profile.
    This fetches the user with all necessary relationships pre-loaded
    to avoid any lazy-loading issues during serialization.
    """
    user_details = await crud.crud_user.get_user_details_for_profile(db, user_id=current_user.id)
    if not user_details:
        # This should theoretically not happen if the user is authenticated
        raise HTTPException(status_code=404, detail="User not found")
    return user_details

@router.get("/me/profile", response_model=UserProfileSchema)
async def read_my_profile(
    current_user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get current user's profile.
    """
    profile = await crud_user_profile.get_profile_by_user_id(db, user_id=current_user.id)
    if not profile:
        # If profile does not exist, create one. This could happen if user was created before profile logic.
        profile = await crud_user_profile.create_profile_for_user(db, user=current_user)
        # We might want to raise an error or handle this differently based on expected state
        # For now, creating it ensures the endpoint doesn't fail for users without one.

    # Populate full_name and generate signed URL for profile picture
    profile_data = UserProfileSchema.model_validate(profile) # Use model_validate for Pydantic v2
    profile_data.full_name = current_user.full_name # Populate from the User model

    if profile.profile_picture_url:
        try:
            # Assuming profile_picture_url stores the GCS blob name
            signed_url = generate_gcs_signed_url(blob_name=profile.profile_picture_url)
            profile_data.profile_picture_signed_url = signed_url
        except Exception as e:
            logger.error(f"Failed to generate signed URL for profile picture {profile.profile_picture_url} for user {current_user.id}: {e}", exc_info=True)
            profile_data.profile_picture_signed_url = None # Or a placeholder/default URL

    return profile_data

@router.put("/me/profile", response_model=UserProfileSchema)
async def update_my_profile(
    profile_in: UserProfileUpdate,
    current_user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update current user's profile.
    """
    db_profile = await crud_user_profile.get_profile_by_user_id(db, user_id=current_user.id)
    if not db_profile:
        # This case should ideally not happen if profiles are created on user registration or first access
        # Consider if creating one here is the right approach or if it indicates a prior error
        logger.warning(f"Profile not found for user {current_user.id} during update. Creating one now.")
        db_profile = await crud_user_profile.create_profile_for_user(db, user=current_user)

    updated_profile = await crud_user_profile.update_profile(db=db, db_obj=db_profile, obj_in=profile_in)
    
    # Populate full_name and generate signed URL for profile picture for the response
    profile_data = UserProfileSchema.model_validate(updated_profile) # Use model_validate for Pydantic v2
    profile_data.full_name = current_user.full_name

    if updated_profile.profile_picture_url:
        try:
            signed_url = generate_gcs_signed_url(blob_name=updated_profile.profile_picture_url)
            profile_data.profile_picture_signed_url = signed_url
        except Exception as e:
            logger.error(f"Failed to generate signed URL for updated profile picture {updated_profile.profile_picture_url} for user {current_user.id}: {e}", exc_info=True)
            profile_data.profile_picture_signed_url = None

    return profile_data

@router.post("/me/profile/picture", response_model=UserProfileSchema)
async def upload_my_profile_picture(
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Upload a new profile picture for the current user.
    Updates the user's profile_picture_url with the GCS blob name.
    Returns the updated profile information with a new signed URL for the picture.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided for profile picture.")

    # Generate a unique filename for the profile picture
    file_extension = file.filename.split('.')[-1] if '.' in file.filename else 'png' # Default to png if no extension
    # Sanitize or ensure file_extension is safe if used directly in blob name
    unique_filename = f"{uuid.uuid4()}.{file_extension}"
    destination_blob_name = f"profile_pictures/{current_user.id}/{unique_filename}"

    # Get the current profile or create if it doesn't exist
    db_profile = await crud_user_profile.get_profile_by_user_id(db, user_id=current_user.id)
    if not db_profile:
        logger.info(f"Profile not found for user {current_user.id} during picture upload. Creating one.")
        db_profile = await crud_user_profile.create_profile_for_user(db, user=current_user)

    # If there's an old picture, consider deleting it from GCS
    old_blob_name = db_profile.profile_picture_url

    try:
        # Upload the new file to GCS
        uploaded_blob_name = await run_in_threadpool(
            upload_file_to_gcs, 
            file=file, 
            destination_blob_name=destination_blob_name
        )

        if not uploaded_blob_name:
            raise HTTPException(status_code=500, detail="Profile picture upload failed.")

    # Update profile with the new blob name
        profile_update_data = UserProfileUpdate(profile_picture_url=uploaded_blob_name)
        updated_profile = await crud_user_profile.update_profile(db=db, db_obj=db_profile, obj_in=profile_update_data)

        # If upload and DB update were successful, delete the old blob if it existed
        if old_blob_name and old_blob_name != uploaded_blob_name:
            logger.info(f"Attempting to delete old profile picture: {old_blob_name} for user {current_user.id}")
            # Consider making delete_gcs_blob async or running in threadpool if it's blocking
            # For now, assuming it's quick enough or background deletion is handled elsewhere if needed.
            from app.utils.storage import delete_gcs_blob # Import locally for now
            delete_success = await run_in_threadpool(delete_gcs_blob, blob_name=old_blob_name)
            if delete_success:
                logger.info(f"Successfully deleted old profile picture: {old_blob_name}")
            else:
                logger.warning(f"Failed to delete old profile picture: {old_blob_name}")

    except Exception as e:
        logger.error(f"Error during profile picture upload for user {current_user.id}: {e}", exc_info=True)
        # If upload failed partway, consider if GCS blob needs cleanup if it was created but DB update failed
        raise HTTPException(status_code=500, detail=f"Could not upload profile picture: {e}")

    # Prepare response with signed URL for the new picture
    response_data = UserProfileSchema.model_validate(updated_profile)
    response_data.full_name = current_user.full_name
    if updated_profile.profile_picture_url:
        try:
            signed_url = generate_gcs_signed_url(blob_name=updated_profile.profile_picture_url)
            response_data.profile_picture_signed_url = signed_url
        except Exception as e:
            logger.error(f"Failed to generate signed URL for new profile picture {updated_profile.profile_picture_url} for user {current_user.id}: {e}", exc_info=True)
            response_data.profile_picture_signed_url = None

    return response_data

# --- Endpoint to view OTHER users' profiles --- 
@router.get("/{user_id}/profile", response_model=UserProfileSchema)
async def read_user_profile(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user), # Get current user to check relationship
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
        # If profile does not exist, it might be an old user. Create one on-the-fly.
        target_user = await crud.crud_user.get_user_by_id(db, user_id=user_id)
        if not target_user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
        profile_db = await crud_user_profile.create_profile_for_user(db, user=target_user)

    # For now, let's assume we return the same profile data regardless of connection
    # We can add filtering later based on `is_connected` or `profile_db.contact_info_visibility`
    profile_data = UserProfileSchema.from_orm(profile_db)
    profile_data.role = profile_db.user.role
    profile_data.status = profile_db.user.status
    profile_data.email = profile_db.user.email

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

@router.get(
    "/{user_id}/detailed-profile", 
    response_model=UserDetailSchema,
    dependencies=[Depends(get_current_user)] # Or specific role if needed
)
async def read_user_detailed_profile(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    # current_user: models.User = Depends(security.get_current_active_user) # Can be used for permission checks
):
    """
    Fetch a comprehensive, detailed profile of a specific user by their ID.
    Includes profile, company, startup, space, managed space, and current workstation.
    """
    user_db = await crud_user.get_user_details_for_profile(db, user_id=user_id)
    if not user_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    current_workstation_info_dict = None
    if user_db.assignments:
        active_assignment = next(
            (a for a in user_db.assignments if a.end_date is None and a.workstation), 
            None
        )
        if active_assignment and active_assignment.workstation:
            # Ensure start_date exists on WorkstationAssignment model, default if not for safety.
            start_date = getattr(active_assignment, 'start_date', datetime.datetime.utcnow()) 
            current_workstation_info_dict = {
                "workstation_id": active_assignment.workstation.id,
                "workstation_name": active_assignment.workstation.name,
                "assignment_start_date": start_date 
            }

    # Create the UserDetail object from the ORM model
    # The `current_workstation` field will be populated from current_workstation_info_dict if provided
    user_detail_data = UserDetailSchema.model_validate(user_db)
    
    # If UserProfileSchema within UserDetailSchema needs to generate signed URLs,
    # it should handle that upon its own instantiation from user_db.profile.
    # Or, we can manually trigger it here if necessary.
    if user_detail_data.profile and user_db.profile and user_db.profile.profile_picture_url and storage.GCS_BUCKET:
        try:
            blob = storage.GCS_BUCKET.blob(user_db.profile.profile_picture_url)
            signed_url = blob.generate_signed_url(
                version="v4",
                expiration=datetime.timedelta(hours=1),
                method="GET",
            )
            user_detail_data.profile.profile_picture_signed_url = signed_url
        except Exception as e:
            logger.error(f"Error generating signed URL for profile picture in detailed view for user {user_id}: {e}")
            # Do not fail the request, profile_picture_signed_url will remain None or its default

    return user_detail_data

@router.post("/{user_id}/initiate-contact", response_model=Message)
async def initiate_contact_with_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Creates a notification for a user to initiate contact.
    Typically used by a Corp Admin to contact a waitlisted user.
    """
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot initiate contact with yourself.")

    target_user = await crud.crud_user.get_user_by_id(db, user_id=user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="Target user not found.")

    # Get the Corp Admin's space name
    space_name = "their space"
    if current_user.role == 'CORP_ADMIN' and current_user.managed_space:
        space_name = f"the '{current_user.managed_space.name}' space"


    message = f"{current_user.full_name or 'A corporate admin'} from {space_name} would like to discuss having you join their space."

    await crud.crud_notification.create_notification(
        db=db,
        user_id=target_user.id,
        type=NotificationType.INTEREST_EXPRESSED, # Reusing this type, or could create a new one
        message=message,
        related_entity_id=current_user.id, # The entity initiating contact is the current user
        link=f"/chat?with={current_user.id}" # Link to open chat with the admin
    )

    return {"message": "Contact initiation notification sent successfully."}

# Add other user-related endpoints here later (e.g., update profile) 