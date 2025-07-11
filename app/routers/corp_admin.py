from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional, Union

from app import schemas, models, crud, services
from app.db.session import get_db
from app.dependencies import require_corp_admin, get_current_active_user, get_current_user_with_roles
from app.models.enums import UserRole, UserStatus, NotificationType
from app.schemas.admin import (
    AISearchRequest,
    StartupUpdateAdmin,
    MemberSlotUpdate,
    SpaceCreate as AdminSpaceCreate,
)
from app.schemas.user import User as UserSchema
from app.schemas.organization import Startup as StartupSchema, Company as CompanySchema, CompanyUpdate
from app.schemas.dashboard import DashboardStats
from app.schemas.billing import BillingInfo
from app.services import billing_service, company_service

router = APIRouter(
    tags=["Corporate Admin"],
    prefix="/corp-admin",
    dependencies=[Depends(require_corp_admin)]
)

@router.get("/tenants", response_model=List[Union[schemas.User, schemas.Startup]])
async def get_company_tenants(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Get all tenants (freelancers and startups) in all spaces of the admin's company."""
    if not current_user.company_id:
        raise HTTPException(status_code=403, detail="Admin not associated with a company.")
    
    return await services.corp_admin_service.get_all_company_tenants(db, company_id=current_user.company_id)

@router.get("/workstations", response_model=List[schemas.Workstation])
async def get_company_workstations(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Get all workstations in all spaces of the admin's company."""
    if not current_user.company_id:
        raise HTTPException(status_code=403, detail="Admin not associated with a company.")
    
    return await services.corp_admin_service.get_all_company_workstations(db, company_id=current_user.company_id)

@router.get("/invites", response_model=List[schemas.Invitation])
async def get_company_invites(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Get all pending invitations for the admin's company."""
    if not current_user.company_id:
        raise HTTPException(status_code=403, detail="Admin not associated with a company.")
    
    return await crud.crud_invitation.get_by_company_id(db, company_id=current_user.company_id)

@router.get("/company-members", response_model=List[schemas.User])
async def get_company_members(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Get all members (employees) of the admin's company."""
    if not current_user.company_id:
        raise HTTPException(status_code=403, detail="Admin not associated with a company.")
        
    return await crud.crud_user.get_users_by_company_id(db, company_id=current_user.company_id)

@router.get("/dashboard/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Get key statistics for the corporate admin dashboard."""
    if not current_user.company_id:
        raise HTTPException(status_code=403, detail="Admin not associated with a company.")
    
    stats = await services.corp_admin_service.get_dashboard_stats(db, company_id=current_user.company_id)
    return stats

@router.get("/spaces", response_model=List[schemas.Space])
async def get_company_spaces(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Get all spaces belonging to the current admin's company."""
    if not current_user.company_id:
        raise HTTPException(status_code=403, detail="Admin not associated with a company.")
    return await services.space_service.get_spaces_by_company_id(
        db=db, company_id=current_user.company_id
    )

@router.post("/spaces", response_model=schemas.Space)
async def create_space_for_company(
    space_in: AdminSpaceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Allows a Corporate Admin to create a new space for their own company.
    """
    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not associated with a company.",
        )
    
    return await services.space_service.create_space(
        db=db, space_in=space_in, company_id=current_user.company_id
    )

@router.put("/spaces/{space_id}", response_model=schemas.Space)
async def update_space_details(
    space_id: int,
    space_update: schemas.SpaceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Allows a Corporate Admin to update the details of one of their spaces.
    """
    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not associated with a company.",
        )

    # The service function will handle checking if the space belongs to the user's company
    return await services.space_service.update_space_details(
        db=db,
        space_id=space_id,
        space_update=space_update,
        company_id=current_user.company_id,
    )

@router.post("/spaces/{space_id}/images", response_model=schemas.SpaceImage)
async def add_image_to_space(
    space_id: int,
    image_file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Allows a Corporate Admin to add an image to one of their spaces.
    """
    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not associated with a company.",
        )

    # Check if the space belongs to the user's company
    space = await crud.crud_space.get(db, id=space_id)
    if not space or space.company_id != current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to add images to this space.",
        )

    return await services.space_service.add_image_to_space(
        db=db,
        space_id=space_id,
        image_file=image_file,
        current_user=current_user,
    )

@router.post(
    "/ai-search-waitlist",
    response_model=List[schemas.user.UserDetail],
    status_code=status.HTTP_200_OK,
    summary="Perform AI search on waitlisted user profiles",
)
async def ai_search_waitlist(
    search_request: AISearchRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Performs an AI-powered vector search on waitlisted user profiles.
    """
    if not search_request.query:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    return await services.corp_admin_service.search_waitlisted_profiles(db, query=search_request.query)

@router.get("/browse-waitlist", response_model=List[Union[schemas.WaitlistedUser, schemas.WaitlistedStartup]])
async def browse_waitlist(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
    search: Optional[str] = None,
    type: Optional[str] = None,
    sort_by: Optional[str] = Query(None, alias="sortBy"),
    space_id: Optional[int] = Query(None, alias="spaceId"),
    skip: int = 0,
    limit: int = 20,
):
    """Allows Corporate Admins to browse waitlisted users and startups, ranked by interest."""
    return await services.corp_admin_service.browse_waitlist(
        db=db, search=search, type=type, sort_by=sort_by, skip=skip, limit=limit, current_user=current_user, space_id=space_id,
    )

@router.get("/billing", response_model=BillingInfo)
async def get_billing_details(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Get billing details for the admin's company."""
    if not current_user.company_id:
        raise HTTPException(status_code=403, detail="Admin not associated with a company.")
    
    return billing_service.get_billing_info(company_id=current_user.company_id)

@router.get("/settings/details", response_model=CompanySchema)
async def get_company_settings_details(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Get detailed information about the admin's company for the settings page."""
    if not current_user.company_id:
        raise HTTPException(status_code=403, detail="Admin not associated with a company.")
    
    return await company_service.get_company_details(db, company_id=current_user.company_id)

@router.put("/settings/details", response_model=CompanySchema)
async def update_company_settings_details(
    company_update: CompanyUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Update the details of the admin's company."""
    if not current_user.company_id:
        raise HTTPException(status_code=403, detail="Admin not associated with a company.")
        
    return await company_service.update_company_details(
        db=db,
        company_id=current_user.company_id,
        company_update=company_update,
        current_user=current_user
    )

@router.post("/settings/logo", response_model=CompanySchema)
async def upload_company_logo(
    logo_file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Upload a new logo for the admin's company."""
    if not current_user.company_id:
        raise HTTPException(status_code=403, detail="Admin not associated with a company.")

    return await company_service.upload_company_logo(
        db=db,
        company_id=current_user.company_id,
        logo_file=logo_file,
        current_user=current_user
    )

@router.get("/bookings", response_model=List[schemas.Booking])
async def get_company_bookings(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Get all bookings in all spaces of the admin's company."""
    if not current_user.company_id:
        raise HTTPException(status_code=403, detail="Admin not associated with a company.")
    
    return await services.corp_admin_service.get_all_company_bookings(db, company_id=current_user.company_id)

from app.services.analytics_service import analytics_service

@router.get("/analytics", response_model=schemas.AnalyticsData)
async def get_company_analytics(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Get analytics data for the admin's company."""
    if not current_user.company_id:
        raise HTTPException(status_code=403, detail="Admin not associated with a company.")
    
    return await analytics_service.get_analytics_data(db, company_id=current_user.company_id)