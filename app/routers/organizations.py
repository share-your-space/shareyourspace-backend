from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from typing import List, Optional

from app.db.session import get_db
from app import crud, schemas, models
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
    db_company = await crud.crud_organization.get_company(db, company_id=company_id)
    if not db_company:
        raise HTTPException(status_code=404, detail="Company not found")
    return db_company

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
    if not current_user.company_id:
        raise HTTPException(status_code=404, detail="User not associated with a company")

    company = await crud.crud_organization.get_company(db, company_id=current_user.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    updated_company = await crud.crud_organization.update_company(db=db, db_obj=company, obj_in=company_in)
    return updated_company

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
    db_startup = await crud.crud_organization.get_startup(db, startup_id=startup_id)
    if not db_startup:
        raise HTTPException(status_code=404, detail="Startup not found")

    is_own_profile = current_user.startup_id == startup_id
    is_sys_admin = current_user.role == models.enums.UserRole.SYS_ADMIN
    is_active_startup = db_startup.status == models.enums.UserStatus.ACTIVE
    is_corp_admin = current_user.role == models.enums.UserRole.CORP_ADMIN

    if is_active_startup or is_own_profile or is_sys_admin or is_corp_admin:
        return db_startup
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to view this startup profile."
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

    db_startup = await crud.crud_organization.get_startup(
        db, 
        startup_id=current_user.startup_id
    )
    if not db_startup:
        raise HTTPException(status_code=404, detail="Startup not found")

    from app.schemas.organization import Startup
    try:
        # We manually validate and convert to a dict to see the data and bypass FastAPI's response_model issues.
        validated_startup = Startup.model_validate(db_startup)
        startup_dict = validated_startup.model_dump()
        logger.info(f"DEBUG: Startup data being returned: {startup_dict}")
        return startup_dict
    except Exception as e:
        logger.error(f"DEBUG: Pydantic validation FAILED for startup ID {current_user.startup_id}: {e}")
        logger.error(f"DEBUG: Failing Startup raw data: {db_startup.__dict__}")
        raise HTTPException(status_code=500, detail="Server error processing startup data.")

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
    if not current_user.startup_id:
        raise HTTPException(status_code=404, detail="User not associated with a startup")

    startup = await crud.crud_organization.get_startup(db, startup_id=current_user.startup_id)
    if not startup:
        raise HTTPException(status_code=404, detail="Startup not found")

    updated_startup = await crud.crud_organization.update_startup(db=db, db_obj=startup, obj_in=startup_in)
    return updated_startup

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

@router.post("/request-invitation", status_code=202)
async def request_invitation(
    request_data: schemas.organization.InvitationRequest, 
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Handles a user's request for an invitation to an organization.
    """
    org_id = request_data.organization_id
    org_type = request_data.organization_type

    await crud.crud_user.update_user_internal(
        db, db_obj=current_user, obj_in=schemas.user.UserUpdateInternal(status=models.enums.UserStatus.WAITLISTED)
    )

    await create_notification_for_org_admins(
            db=db,
        org_id=org_id,
        org_type=org_type,
        message=f"User '{current_user.full_name or current_user.email}' has requested an invitation to join your organization.",
        related_entity_id=current_user.id
    )
    
    await db.commit()

    return {"message": "Your request for an invitation has been sent."}

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