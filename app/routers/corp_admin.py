import logging
from fastapi import APIRouter, Depends, HTTPException, Query, status, UploadFile, File, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional, Union

from app import schemas, models, crud, services
from app.db.session import get_db
from app.dependencies import require_corp_admin, get_current_active_user
from app.models.enums import UserRole
from app.schemas.admin import AISearchRequest
from app.schemas.organization import CompanyUpdate
from app.schemas.dashboard import DashboardStats
from app.schemas.billing import BillingInfo
from app.schemas.activity import PaginatedActivityResponse
from app.services import (
    billing_service,
    company_service,
    corp_admin_service,
    space_service,
    analytics_service,
    activity_service,
)

router = APIRouter(
    tags=["Corporate Admin"],
    # prefix="/company/{company_id}", # This prefix was causing a double path issue
    dependencies=[Depends(require_corp_admin)]
)

logger = logging.getLogger(__name__)

@router.get(
    "/{company_id}/dashboard/stats",
    response_model=DashboardStats,
    summary="Get key statistics for the corporate admin dashboard",
)
async def get_dashboard_stats(
    company_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Retrieves key statistics for the corporate admin dashboard.
    """
    if not current_user.company_id or current_user.company_id != company_id:
        raise HTTPException(status_code=403, detail="Admin not associated with this company.")
    
    try:
        stats = await corp_admin_service.get_dashboard_stats(db, company_id=company_id)
        return stats
    except Exception as e:
        logger.error(f"Error fetching dashboard stats for company {company_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get(
    "/{company_id}/dashboard/activity",
    response_model=PaginatedActivityResponse,
    summary="Get Recent Company Activity",
)
async def get_company_activity(
    company_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
    limit: int = Query(10, ge=1, le=50)
):
    """
    Retrieves a feed of recent activities for the specified company.
    """
    if not current_user.company_id or current_user.company_id != company_id:
        raise HTTPException(status_code=403, detail="Admin not associated with this company.")
    try:
        activities = await activity_service.get_recent_activity(db, company_id=company_id, limit=limit)
        return PaginatedActivityResponse(activities=activities, total=len(activities))
    except Exception as e:
        logger.error(f"Error fetching activity for company {company_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{company_id}/settings", response_model=schemas.Company)
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

@router.put("/{company_id}/settings", response_model=schemas.Company)
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


@router.get("/{company_id}/tenants", response_model=List[Union[schemas.User, schemas.Startup]])
async def get_company_tenants(
    company_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Get all tenants (freelancers and startups) in all spaces of the admin's company."""
    if not current_user.company_id or current_user.company_id != company_id:
        raise HTTPException(status_code=403, detail="Admin not associated with this company.")
    
    return await corp_admin_service.get_all_company_tenants(db, company_id=current_user.company_id)

@router.get("/{company_id}/workstations", response_model=List[schemas.Workstation])
async def get_company_workstations(
    company_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Get all workstations in all spaces of the admin's company."""
    if not current_user.company_id or current_user.company_id != company_id:
        raise HTTPException(status_code=403, detail="Admin not associated with this company.")
    
    return await corp_admin_service.get_all_company_workstations(db, company_id=current_user.company_id)

@router.get("/{company_id}/invites", response_model=List[schemas.Invitation])
async def get_company_invites(
    company_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Get all pending invitations for the admin's company."""
    if not current_user.company_id or current_user.company_id != company_id:
        raise HTTPException(status_code=403, detail="Admin not associated with this company.")
    
    return await crud.crud_invitation.get_by_company_id(db, company_id=current_user.company_id)

@router.get("/{company_id}/company-members", response_model=List[schemas.User])
async def get_company_members(
    company_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Get all members (employees) of the admin's company."""
    if not current_user.company_id or current_user.company_id != company_id:
        raise HTTPException(status_code=403, detail="Admin not associated with this company.")
        
    return await crud.crud_user.get_users_by_company_id(db, company_id=current_user.company_id)

@router.get("/{company_id}/spaces", response_model=List[schemas.Space])
async def get_company_spaces(
    company_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Get all spaces belonging to the current admin's company."""
    if not current_user.company_id or current_user.company_id != company_id:
        raise HTTPException(status_code=403, detail="Admin not associated with this company.")
    return await space_service.get_spaces_by_company_id(
        db=db, company_id=current_user.company_id
    )

@router.post("/{company_id}/spaces", response_model=schemas.Space)
async def create_space_for_company(
    company_id: int,
    space_in: schemas.admin.SpaceCreate,
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

    return await space_service.create_space(db=db, space_in=space_in)

@router.put("/{company_id}/spaces/{space_id}", response_model=schemas.Space)
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

    return await space_service.update_space_details(
        db=db, space_id=space_id, space_update=space_update, company_id=current_user.company_id
    )

@router.post("/{company_id}/spaces/{space_id}/upload-image", response_model=schemas.SpaceImage)
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

    return await space_service.add_image_to_space(db, space_id=space_id, image_file=file)

@router.post(
    "/{company_id}/ai-search-waitlist",
    response_model=List[schemas.user.UserDetail],
    status_code=status.HTTP_200_OK,
    summary="Perform AI search on waitlisted user profiles",
)
async def ai_search_waitlist(
    company_id: int,
    search_request: AISearchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Performs an AI-powered vector search on waitlisted user profiles.
    """
    if not current_user.company_id or current_user.company_id != company_id:
        raise HTTPException(status_code=403, detail="Admin not associated with this company.")
        
    if not search_request.query:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    return await corp_admin_service.search_waitlisted_profiles(db, query=search_request.query)

@router.get("/{company_id}/analytics/overview", response_model=schemas.AnalyticsOverview)
async def get_analytics_overview(
    company_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Get analytics overview for the company."""
    if not current_user.company_id or current_user.company_id != company_id:
        raise HTTPException(status_code=403, detail="Admin not associated with this company.")
    return await analytics_service.get_company_analytics_overview(db, company_id=current_user.company_id)

@router.get("/{company_id}/billing", response_model=BillingInfo)
async def get_billing_info(
    company_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Retrieve billing information for the company."""
    if not current_user.company_id or current_user.company_id != company_id:
        raise HTTPException(status_code=403, detail="Admin not associated with this company.")
    
    return await billing_service.get_billing_info_for_company(db, company_id=current_user.company_id)

@router.post("/{company_id}/billing/subscription", status_code=status.HTTP_204_NO_CONTENT)
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

@router.get("/{company_id}/bookings", response_model=List[schemas.Booking])
async def get_company_bookings(
    company_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Get all bookings across all spaces for the company."""
    if not current_user.company_id or current_user.company_id != company_id:
        raise HTTPException(status_code=403, detail="Admin not associated with this company.")
    
    return await crud.crud_booking.get_bookings_by_company_id(db, company_id=current_user.company_id)

@router.get("/{company_id}/browse-waitlist", response_model=List[Union[schemas.WaitlistedUser, schemas.WaitlistedStartup]])
async def get_browse_waitlist(
    company_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Get the waitlist of users/startups who want to be browsed by this company."""
    if not current_user.company_id or current_user.company_id != company_id:
        raise HTTPException(status_code=403, detail="Admin not associated with this company.")
    
    return await company_service.get_browse_waitlist(db, company_id=current_user.company_id)