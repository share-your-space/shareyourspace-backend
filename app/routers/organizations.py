from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from typing import List, Optional

from app.db.session import get_db
from app import crud, schemas, models, services
from app.security import get_current_active_user, get_current_user_with_roles, get_current_user, get_current_verified_user_with_roles
from app.schemas.user import User as UserSchema
from app.models.enums import NotificationType, UserRole
from app.models.organization import Company, Startup
from app.crud.crud_notification import create_notification_for_org_admins
import logging

logger = logging.getLogger(__name__)
router = APIRouter(
    tags=["Organizations"]
)

@router.get(
    "/companies/{company_id}",
    response_model=schemas.organization.Company,
    dependencies=[Depends(get_current_user)]
)
async def read_company_profile(
    company_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieve a specific company's profile by its ID.
    """
    return await services.organization_service.get_company_profile(db, company_id=company_id)

@router.put(
    "/companies/me",
    response_model=schemas.organization.Company,
    dependencies=[Depends(get_current_user_with_roles(["CORP_ADMIN"]))],
)
async def update_my_company(
    company_in: schemas.organization.CompanyUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user_with_roles(["CORP_ADMIN"])),
):
    """
    Update the current user's company profile.
    """
    return await services.organization_service.update_company_profile(
        db, company_in=company_in, current_user=current_user
    )

@router.get(
    "/startups/{startup_id}",
    response_model=schemas.organization.Startup,
    dependencies=[Depends(get_current_user)]
)
async def read_startup_profile(
    startup_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Retrieve a specific startup's profile by its ID.
    """
    return await services.organization_service.get_startup_profile(
        db, startup_id=startup_id, current_user=current_user
    )

@router.get(
    "/startups/me",
    # response_model=schemas.organization.Startup, # Temporarily removed for debugging
    dependencies=[Depends(get_current_user_with_roles(["STARTUP_ADMIN"]))],
)
async def read_my_startup(
    current_user: models.User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get the current startup admin's own startup details.
    """
    if not current_user.startup_id:
        raise HTTPException(status_code=404, detail="User is not associated with a startup.")

    return await services.organization_service.get_startup_profile(
        db, startup_id=current_user.startup_id, current_user=current_user
    )

@router.put(
    "/startups/me",
    response_model=schemas.organization.Startup,
    dependencies=[Depends(get_current_verified_user_with_roles([UserRole.STARTUP_ADMIN]))],
)
async def update_my_startup(
    startup_in: schemas.organization.StartupUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_verified_user_with_roles([UserRole.STARTUP_ADMIN])),
):
    """
    Update the current user's startup profile.
    """
    return await services.organization_service.update_startup_profile(
        db, startup_in=startup_in, current_user=current_user
    )

@router.get(
    "/startups/me/members",
    response_model=List[UserSchema],
    dependencies=[Depends(get_current_user_with_roles(required_roles=["STARTUP_ADMIN"]))],
)
async def read_my_startup_members(
    current_user: models.User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve members of the current Startup Admin's team.
    """
    if not current_user.startup_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current user is not associated with a startup.",
        )

    stmt = (
        select(models.User)
        .where(
            models.User.startup_id == current_user.startup_id,
            models.User.id != current_user.id
        )
        .options(
            selectinload(models.User.profile), 
            selectinload(models.User.managed_space),
            selectinload(models.User.space).selectinload(models.SpaceNode.admin).selectinload(models.User.profile)
        )
    )
    result = await db.execute(stmt)
    team_members = result.scalars().all()

    return team_members

@router.delete(
    "/startups/me/members/{member_id}",
    response_model=UserSchema,
    dependencies=[Depends(get_current_user_with_roles(required_roles=["STARTUP_ADMIN"]))],
    status_code=status.HTTP_200_OK,
    summary="Remove a member from a startup",
)
async def remove_startup_member(
    member_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Allows a Startup Admin to remove a member from their startup.
    """
    member_to_remove = await crud.crud_user.get_user_by_id(db, user_id=member_id)
    if not member_to_remove:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    if not current_user.startup_id or member_to_remove.startup_id != current_user.startup_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This user is not a member of your startup.")

    try:
        updated_user = await crud.crud_organization.remove_startup_member(
            db, member_to_remove=member_to_remove, removing_admin=current_user
        )
        return updated_user
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to remove startup member {member_id} by admin {current_user.id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred.") 