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
    prefix="/company/{company_id}",
    dependencies=[Depends(require_corp_admin)]
)

@router.get("/settings", response_model=CompanySchema)
async def get_company_settings(
    company_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Get company settings."""
    if current_user.company_id != company_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    
    company = await company_service.get_company_by_id(db, company_id=company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company

@router.put("/settings", response_model=CompanySchema)
async def update_company_settings(
    company_id: int,
    company_update: CompanyUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Update company settings."""
    if current_user.company_id != company_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    return await company_service.update_company(db, company_id=company_id, company_update=company_update)


@router.get("/tenants", response_model=List[Union[schemas.User, schemas.Startup]])
async def get_company_tenants(
    company_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Get all tenants (freelancers and startups) in all spaces of the admin's company."""
    if not current_user.company_id or current_user.company_id != company_id:
        raise HTTPException(status_code=403, detail="Admin not associated with this company.")
    
    return await services.corp_admin_service.get_all_company_tenants(db, company_id=current_user.company_id)

@router.get("/workstations", response_model=List[schemas.Workstation])
async def get_company_workstations(
    company_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Get all workstations in all spaces of the admin's company."""
    if not current_user.company_id or current_user.company_id != company_id:
        raise HTTPException(status_code=403, detail="Admin not associated with this company.")
    
    return await services.corp_admin_service.get_all_company_workstations(db, company_id=current_user.company_id)

@router.get("/invites", response_model=List[schemas.Invitation])
async def get_company_invites(
    company_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Get all pending invitations for the admin's company."""
    if not current_user.company_id or current_user.company_id != company_id:
        raise HTTPException(status_code=403, detail="Admin not associated with this company.")
    
    return await crud.crud_invitation.get_by_company_id(db, company_id=current_user.company_id)

@router.get("/company-members", response_model=List[schemas.User])
async def get_company_members(
    company_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Get all members (employees) of the admin's company."""
    if not current_user.company_id or current_user.company_id != company_id:
        raise HTTPException(status_code=403, detail="Admin not associated with this company.")
        
    return await crud.crud_user.get_users_by_company_id(db, company_id=current_user.company_id)

@router.get("/dashboard/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    company_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Get key statistics for the corporate admin dashboard."""
    if not current_user.company_id or current_user.company_id != company_id:
        raise HTTPException(status_code=403, detail="Admin not associated with this company.")
    
    stats = await services.corp_admin_service.get_dashboard_stats(db, company_id=current_user.company_id)
    return stats

@router.get("/spaces", response_model=List[schemas.Space])
async def get_company_spaces(
    company_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Get all spaces belonging to the current admin's company."""
    if not current_user.company_id or current_user.company_id != company_id:
        raise HTTPException(status_code=403, detail="Admin not associated with this company.")
    return await services.space_service.get_spaces_by_company_id(
        db=db, company_id=current_user.company_id
    )

@router.post("/spaces", response_model=schemas.Space)
async def create_space_for_company(
    company_id: int,
    space_in: AdminSpaceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Allows a Corporate Admin to create a new space for their own company.
    """
    if not current_user.company_id or current_user.company_id != company_id:
        raise HTTPException(status_code=403, detail="Admin not associated with this company.")
    
    # Ensure the space is created for the correct company
    space_in.company_id = current_user.company_id

    return await services.space_service.create_space(db=db, space_in=space_in)

@router.put("/spaces/{space_id}", response_model=schemas.Space)
async def update_space_details(
    company_id: int,
    space_id: int,
    space_update: schemas.SpaceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Allows a Corporate Admin to update the details of one of their spaces.
    """
    if not current_user.company_id or current_user.company_id != company_id:
        raise HTTPException(status_code=403, detail="Admin not associated with this company.")

    return await services.space_service.update_space_details(
        db=db, space_id=space_id, space_update=space_update, company_id=current_user.company_id
    )

@router.post("/spaces/{space_id}/upload-image", response_model=schemas.SpaceImage)
async def upload_space_image(
    company_id: int,
    space_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Allows a Corporate Admin to add an image to one of their spaces.
    """
    if not current_user.company_id or current_user.company_id != company_id:
        raise HTTPException(status_code=403, detail="Admin not associated with this company.")

    # First, verify the space belongs to the company
    space = await crud.crud_space.get(db, id=space_id)
    if not space or space.company_id != current_user.company_id:
        raise HTTPException(status_code=404, detail="Space not found or not owned by company.")

    return await services.space_service.add_image_to_space(db, space_id=space_id, image_file=file)

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

@router.get("/analytics/overview", response_model=schemas.AnalyticsOverview)
async def get_analytics_overview(
    company_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Get analytics overview for the company."""
    if not current_user.company_id or current_user.company_id != company_id:
        raise HTTPException(status_code=403, detail="Admin not associated with this company.")
    return await services.analytics_service.get_company_analytics_overview(db, company_id=current_user.company_id)

@router.get("/billing", response_model=BillingInfo)
async def get_billing_info(
    company_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Retrieve billing information for the company."""
    if not current_user.company_id or current_user.company_id != company_id:
        raise HTTPException(status_code=403, detail="Admin not associated with this company.")
    
    return await billing_service.get_billing_info_for_company(db, company_id=current_user.company_id)

@router.post("/billing/subscription", status_code=status.HTTP_204_NO_CONTENT)
async def update_subscription(
    company_id: int,
    subscription_update: schemas.SubscriptionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Update company's subscription plan."""
    if not current_user.company_id or current_user.company_id != company_id:
        raise HTTPException(status_code=403, detail="Admin not associated with this company.")
    
    await billing_service.update_subscription_plan(
        db, company_id=current_user.company_id, plan_id=subscription_update.plan_id
    )
    return

@router.get("/bookings", response_model=List[schemas.Booking])
async def get_company_bookings(
    company_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Get all bookings across all spaces for the company."""
    if not current_user.company_id or current_user.company_id != company_id:
        raise HTTPException(status_code=403, detail="Admin not associated with this company.")
    
    return await crud.crud_booking.get_bookings_by_company(db, company_id=current_user.company_id)

@router.get("/browse-waitlist", response_model=List[Union[schemas.WaitlistedUser, schemas.WaitlistedStartup]])
async def get_browse_waitlist(
    company_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Get the waitlist of users/startups who want to be browsed by this company."""
    if not current_user.company_id or current_user.company_id != company_id:
        raise HTTPException(status_code=403, detail="Admin not associated with this company.")
    
    return await company_service.get_browse_waitlist(db, company_id=current_user.company_id)