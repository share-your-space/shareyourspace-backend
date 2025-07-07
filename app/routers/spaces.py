from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional

from app.db.session import get_db
from app import models, schemas, services
from app.dependencies import get_current_user, get_current_active_user
from app.utils.storage import gcs_storage

router = APIRouter()

@router.post("", response_model=schemas.space.SpaceCreationResponse, status_code=status.HTTP_201_CREATED)
async def create_space_node(
    space_in: schemas.admin.SpaceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Create a new SpaceNode."""
    return await services.space_service.create_space(
        db=db, space_in=space_in, current_user=current_user
    )

@router.get("/browseable", response_model=schemas.space.BrowseableSpaceListResponse)
async def list_browseable_spaces(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Lists all spaces available for users to browse."""
    return await services.space_service.get_browseable_spaces(db=db, current_user=current_user)

@router.get("/{space_id}/admins", response_model=List[schemas.user.BasicUserInfo])
async def get_space_admins_details(
    space_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Gets the basic details of the corporate admins for a given space."""
    admins = await services.space_service.get_space_admins(db, space_id=space_id)
    return [schemas.user.BasicUserInfo(id=admin.id, full_name=admin.full_name) for admin in admins]

@router.get("/{space_id}/profile", response_model=schemas.space.SpaceProfile)
async def get_space_profile(
    space_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Gets the public profile for a specific space, including images."""
    space = await services.space_service.get_space_profile(db, space_id=space_id)
    response = schemas.space.SpaceProfile.model_validate(space)
    if response.images:
        for img in response.images:
            img.image_url = gcs_storage.generate_signed_url(img.image_url)

    if response.company and response.company.logo_url:
        response.company.logo_url = gcs_storage.generate_signed_url(
            response.company.logo_url
        )

    return response