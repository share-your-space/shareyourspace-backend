from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
import uuid
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import selectinload

from app import crud, models, schemas, services
from app.models.enums import UserStatus, UserRole
from app.models.organization import Company
from app.schemas.user import UserUpdateInternal
from app.services import corp_admin_service
from app.utils.storage import gcs_storage
from fastapi import UploadFile

async def create_space(
    db: AsyncSession, *, space_in: schemas.admin.SpaceCreate, company_id: int
) -> models.SpaceNode:
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not associated with a company."
        )

    space_in.company_id = company_id

    company = await crud.crud_organization.get_company(db, company_id=company_id)
    if not company:
        raise HTTPException(status_code=404, detail=f"Company with id {company_id} not found.")

    new_space = await crud.crud_space.create_space(db=db, obj_in=space_in)

    # Automatically create the workstations for the new space
    if new_space.total_workstations > 0:
        await crud.crud_space.bulk_create_workstations(
            db=db, space_id=new_space.id, count=new_space.total_workstations
        )
    
    return new_space


async def get_browseable_spaces(db: AsyncSession, *, current_user: models.User) -> schemas.space.BrowseableSpaceListResponse:
    all_spaces = await crud.crud_space.get_spaces(db, skip=0, limit=100)  # Assuming a reasonable limit
    user_interests = await crud.crud_interest.interest.get_interests_by_user(db, user_id=current_user.id)

    interest_map = {interest.space_id: interest.status for interest in user_interests}

    browseable_spaces = []
    for space in all_spaces:
        status = interest_map.get(space.id, 'not_interested')
        cover_image_url = None
        if space.images and space.images[0].image_url:
            # Generate a signed URL for the first image as a cover
            cover_image_url = gcs_storage.generate_signed_url(space.images[0].image_url)

        browseable_spaces.append(
            schemas.space.BrowseableSpace(
                id=space.id,
                name=space.name,
                address=space.address,
                headline=space.headline,
                cover_image_url=cover_image_url,
                total_workstations=space.total_workstations,
                company_name=space.company.name if space.company else "N/A",
                company_id=space.company.id if space.company else None,
                interest_status=status.value if hasattr(status, 'value') else status
            )
        )

    return schemas.space.BrowseableSpaceListResponse(spaces=browseable_spaces)

async def get_spaces_by_company_id(db: AsyncSession, company_id: int) -> List[models.SpaceNode]:
    """Get all spaces for a given company."""
    return await crud.crud_space.get_by_company_id(db, company_id=company_id)

async def update_space_details(
    db: AsyncSession,
    *,
    space_id: int,
    space_update: schemas.SpaceUpdate,
    company_id: int,
) -> models.SpaceNode:
    """
    Update a space's details, ensuring the space belongs to the specified company.
    """
    space = await crud.crud_space.get(db, id=space_id)
    if not space:
        raise HTTPException(status_code=404, detail="Space not found")
    if space.company_id != company_id:
        raise HTTPException(
            status_code=403, detail="Not authorized to update this space"
        )

    return await crud.crud_space.update(db, db_obj=space, obj_in=space_update)


async def get_space_admins(db: AsyncSession, space_id: int) -> List[models.User]:
    space = await crud.crud_space.get(db, id=space_id, options=[selectinload(models.SpaceNode.company, Company.corporate_admins)])
    if not space or not space.company:
        return []
    return space.company.corporate_admins

async def get_space_profile(db: AsyncSession, *, space_id: int) -> models.SpaceNode:
    space = await crud.crud_space.space.get_space_with_images(db=db, space_id=space_id)
    if not space:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Space not found",
        )
    return space

async def update_space_profile(
    db: AsyncSession, *, space_id: int, profile_data: schemas.space.SpaceProfileUpdate, current_user: models.User
) -> models.SpaceNode:
    space = await corp_admin_service.check_admin_space_permission(db, current_user=current_user, space_id=space_id)
    return await crud.crud_space.update_space(db, space_obj=space, obj_in=profile_data)

async def add_image_to_space(
    db: AsyncSession, *, space_id: int, image_file: UploadFile, current_user: models.User
) -> models.SpaceImage:
    space = await corp_admin_service.check_admin_space_permission(db, current_user=current_user, space_id=space_id)
    
    unique_filename = f"spaces/{space.id}/{uuid.uuid4()}_{image_file.filename}"
    
    blob_name = await gcs_storage.upload_file_async(
        file=image_file, 
        blob_name=unique_filename,
        content_type=image_file.content_type
    )

    if not blob_name:
        raise HTTPException(status_code=500, detail="Failed to upload image to storage.")

    image_create = schemas.space.SpaceImageCreate(space_id=space.id, image_url=blob_name)
    
    db_obj = await crud.crud_space.create_space_image(db=db, obj_in=image_create)
    
    db_obj.image_url = gcs_storage.generate_signed_url(db_obj.image_url)
        
    return db_obj

async def delete_image_from_space(
    db: AsyncSession, *, space_id: int, image_id: int, current_user: models.User
) -> None:
    await corp_admin_service.check_admin_space_permission(db, current_user=current_user, space_id=space_id)
    
    image = await crud.crud_space.get_space_image(db, image_id=image_id)
    if not image or image.space_id != space_id:
        raise HTTPException(status_code=404, detail="Image not found in this space.")
        
    gcs_storage.delete_blob(blob_name=image.image_url)
    await crud.crud_space.delete_space_image(db, image_id=image_id)