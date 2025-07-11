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
from app.schemas.organization import Startup as StartupSchema
from app.schemas.dashboard import DashboardStats

router = APIRouter(
    tags=["Corporate Admin"],
    prefix="/corp-admin",
    dependencies=[Depends(require_corp_admin)]
)

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

@router.post("/spaces/{space_id}/add-tenant", response_model=schemas.Message)
async def add_tenant_to_space(
    space_id: int,
    tenant_data: schemas.admin.AddTenantRequest,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Adds a freelancer or startup to a managed space."""
    await services.corp_admin_service.add_tenant_to_space(
        db=db,
        space_id=space_id,
        tenant_data=tenant_data,
        current_user=current_user,
    )
    return {"message": "Tenant successfully added to the space."}


@router.put("/spaces/{space_id}/startups/{startup_id}", response_model=StartupSchema)
async def update_startup_by_corp_admin(
    space_id: int,
    startup_id: int,
    startup_update: StartupUpdateAdmin,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Allows a Corporate Admin to update a startup in one of their managed spaces.
    """
    return await services.corp_admin_service.update_startup_info(
        db,
        space_id=space_id,
        startup_id=startup_id,
        startup_update=startup_update,
        current_user=current_user
    )

@router.put("/spaces/{space_id}/startups/{startup_id}/slots", response_model=schemas.Startup)
async def update_startup_member_slots(
    space_id: int,
    startup_id: int,
    slot_data: MemberSlotUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Allows a Corp Admin to update member slots for a startup in one of their spaces.
    """
    return await services.corp_admin_service.update_startup_slots(
        db,
        space_id=space_id,
        startup_id=startup_id,
        slot_data=slot_data,
        current_user=current_user
    )

@router.get("/spaces/{space_id}/tenants", response_model=schemas.SpaceTenantResponse)
async def list_space_tenants(
    space_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    search: Optional[str] = None,
    sort_by: Optional[str] = None,
):
    """List Startups and Freelancers assigned to a specific managed space."""
    tenants_from_db = await services.corp_admin_service.get_space_tenants(
        db, space_id=space_id, current_user=current_user, search=search, sort_by=sort_by
    )

    tenant_infos = []
    for tenant in tenants_from_db:
        if isinstance(tenant, models.Startup):
            tenant_infos.append(
                schemas.space.StartupTenantInfo(
                    details=tenant,
                    member_count=len(tenant.direct_members)
                )
            )
        elif isinstance(tenant, models.User):
            tenant_infos.append(
                schemas.space.FreelancerTenantInfo(
                    details=tenant
                )
            )

    return schemas.SpaceTenantResponse(tenants=tenant_infos)

@router.post("/spaces/{space_id}/workstations", response_model=schemas.Workstation)
async def create_workstation(
    space_id: int,
    workstation_in: schemas.WorkstationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Allows a Corporate Admin to create a new workstation in a managed space.
    """
    return await services.workstation_service.create_workstation(
        db=db, space_id=space_id, workstation_in=workstation_in, current_user=current_user
    )

@router.put("/spaces/{space_id}/workstations/{workstation_id}", response_model=schemas.Workstation)
async def update_workstation_details(
    space_id: int,
    workstation_id: int,
    workstation_in: schemas.WorkstationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Allows a Corporate Admin to update a workstation's details (e.g., name).
    """
    return await services.workstation_service.update_workstation_details(
        db=db,
        space_id=space_id,
        workstation_id=workstation_id,
        workstation_in=workstation_in,
        current_user=current_user
    )

@router.post("/spaces/{space_id}/workstations/{workstation_id}/assign", response_model=schemas.WorkstationAssignment)
async def assign_workstation(
    space_id: int,
    workstation_id: int,
    assignment_data: schemas.WorkstationAssignmentRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Assigns a user to a workstation in a managed space.
    """
    # Ensure the request body matches the workstation_id in the path
    if assignment_data.workstation_id != workstation_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Workstation ID in path does not match ID in request body.",
        )

    return await services.workstation_service.assign_workstation(
        db=db,
        request=request,
        space_id=space_id,
        assignment_data=assignment_data,
        current_user=current_user,
    )

@router.put("/spaces/{space_id}/workstations/{workstation_id}/status", response_model=schemas.Workstation)
async def update_workstation_status(
    space_id: int,
    workstation_id: int,
    status_update: schemas.WorkstationStatusUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Updates the status of a specific workstation.
    """
    return await services.workstation_service.update_workstation_status(
        db=db,
        space_id=space_id,
        workstation_id=workstation_id,
        status_update=status_update,
        current_user=current_user
    )

@router.get("/spaces/{space_id}/workstations", response_model=schemas.SpaceWorkstationListResponse)
async def list_space_workstations(
    space_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    search: Optional[str] = None,
    sort_by: Optional[str] = None,
):
    """List all workstations in a specific managed space."""
    workstations = await services.corp_admin_service.list_space_workstations(
        db, space_id=space_id, current_user=current_user, search=search, sort_by=sort_by
    )
    
    response_workstations = []
    for ws in workstations:
        ws_data = schemas.Workstation.model_validate(ws).model_dump()
        assigned_user = None
        if ws.active_assignment and ws.active_assignment.user:
            assigned_user = schemas.UserSimple.model_validate(ws.active_assignment.user)
        
        ws_detail = schemas.SpaceWorkstationDetail(
            **ws_data,
            occupant=assigned_user
        )
        response_workstations.append(ws_detail)

    return schemas.SpaceWorkstationListResponse(workstations=response_workstations)

@router.get("/spaces/{space_id}/users", response_model=schemas.SpaceUsersListResponse)
async def list_space_users(
    space_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    search: Optional[str] = None,
    sort_by: Optional[str] = None,
):
    """List all users in a specific managed space."""
    users = await services.corp_admin_service.list_users_in_space(
        db, space_id=space_id, current_user=current_user, search=search, sort_by=sort_by
    )
    
    response_users = []
    for user in users:
        user_data = schemas.User.model_validate(user).model_dump()
        assigned_workstation = None
        # Ensure there is an active assignment before trying to access it
        if user.assignments and user.assignments[0].end_date is None and user.assignments[0].workstation:
            assigned_workstation = schemas.Workstation.model_validate(user.assignments[0].workstation)

        user_detail = schemas.SpaceUserDetail(
            **user_data,
            assigned_workstation=assigned_workstation
        )
        response_users.append(user_detail)

    return schemas.SpaceUsersListResponse(users=response_users)

@router.post("/spaces/{space_id}/users", response_model=schemas.UserDetail)
async def add_user_to_managed_space(
    space_id: int,
    add_user_request: schemas.AddUserToSpaceRequest,
    current_user: models.User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Allows a Corporate Admin to add a waitlisted user to a managed space."""
    updated_user = await services.corp_admin_service.add_or_move_user_to_space(
        db, space_id=space_id, add_user_request=add_user_request, current_user=current_user
    )
    return schemas.UserDetail.model_validate(updated_user)

@router.post("/invite-admin", response_model=schemas.Invitation)
async def invite_admin(
    invite_data: schemas.AdminInviteCreate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Invite a new corporate admin to the company."""
    return await services.invitation_service.create_admin_invitation(
        db, invite_data=invite_data, current_user=current_user
    )

@router.put("/spaces/{space_id}/profile", response_model=schemas.Space)
async def update_space_profile(
    space_id: int,
    profile_data: schemas.SpaceProfileUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Update the profile for a managed space."""
    updated_space = await services.space_service.update_space_profile(
        db, space_id=space_id, profile_data=profile_data, current_user=current_user
    )
    return updated_space

@router.post("/spaces/{space_id}/images", response_model=schemas.SpaceImageSchema)
async def upload_space_image(
    space_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Upload an image for a managed space."""
    return await services.space_service.add_image_to_space(
        db, space_id=space_id, image_file=file, current_user=current_user
    )

@router.delete("/spaces/{space_id}/images/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_space_image(
    space_id: int,
    image_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Delete an image from a managed space."""
    await services.space_service.delete_image_from_space(
        db, space_id=space_id, image_id=image_id, current_user=current_user
    )
    return None

@router.post("/spaces/{space_id}/workstations/{workstation_id}/unassign", response_model=schemas.Message)
async def unassign_workstation(
    space_id: int,
    workstation_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Unassigns a user from a workstation in a managed space.
    """
    return await services.workstation_service.unassign_workstation(
        db=db,
        request=request,
        space_id=space_id,
        workstation_id=workstation_id,
        current_user=current_user,
    )

@router.delete("/spaces/{space_id}/workstations/{workstation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workstation(
    space_id: int,
    workstation_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Allows a Corporate Admin to delete a workstation.
    If the workstation is occupied, the user will be unassigned.
    """
    await services.workstation_service.delete_workstation_by_id(
        db=db,
        space_id=space_id,
        workstation_id=workstation_id,
        current_user=current_user
    )
    return None

@router.delete("/spaces/{space_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_space(
    space_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Allows a Corporate Admin to delete a managed space.
    This will move all tenants back to the waitlist and remove the space.
    """
    await services.corp_admin_service.delete_space_and_handle_tenants(
        db=db, space_id=space_id, current_user=current_user
    )
    return None