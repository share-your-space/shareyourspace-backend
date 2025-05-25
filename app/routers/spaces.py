from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy import func
from typing import List
from datetime import datetime

from app.db.session import get_db
from app import models, schemas
from app.security import get_current_active_user, get_current_user_with_roles
from app.schemas.user import User as UserSchema, UserCreate, UserUpdateInternal # Import UserSchema and UserUpdateInternal
from app.schemas.space import (
    ManagedSpaceDetail,
    SpaceTenantResponse,
    SpaceWorkstationListResponse,
    WorkstationAssignmentRequest,
    WorkstationDetail,
    WorkstationUnassignRequest,
    WorkstationStatusUpdateRequest,
    SpaceUsersListResponse, # Added
    BasicUser, # Ensure BasicUser is imported if not already
    SpaceConnectionStatsResponse # Added SpaceConnectionStatsResponse
)
from app.models.organization import Company # Changed from app.models.company import CompanyNode
from app.crud import crud_organization # Import crud_organization
from app.schemas.organization import BasicStartup as BasicStartupSchema # Import BasicStartup schema

router = APIRouter()

async def get_managed_space(
    db: AsyncSession, current_user: models.User
) -> models.SpaceNode:
    """Helper function to get the space managed by the current Corp Admin."""
    # Corp admin might manage a space directly (via space.corporate_admin_id)
    # or they might be linked via their company if the company itself is primary contact for a space
    # For now, assume direct management via corporate_admin_id on SpaceNode
    stmt = select(models.SpaceNode).where(models.SpaceNode.corporate_admin_id == current_user.id)
    result = await db.execute(stmt)
    managed_space = result.scalar_one_or_none()

    if not managed_space:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No space found managed by the current user. Ensure you are a Corporate Admin of a space.",
        )
    return managed_space

@router.get(
    "/me/employees",
    response_model=List[UserSchema],
    dependencies=[Depends(get_current_user_with_roles(required_roles=["CORP_ADMIN"]))],
)
async def list_my_space_employees(
    current_user: models.User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """List users belonging to the Corp Admin's company within their managed space.
    Requires CORP_ADMIN role.
    """
    managed_space = await get_managed_space(db, current_user)

    if not current_user.company_id:
        # If the Corp Admin themselves are not tied to a company, they can't have company employees in the space.
        # Or, this could mean list *all* users in their space if company_id is not the filter.
        # For now, sticking to "Corp Admin's company employees".
        return [] 

    stmt = (
        select(models.User)
        .where(
            models.User.company_id == current_user.company_id,
            models.User.space_id == managed_space.id,
            models.User.id != current_user.id # Exclude the admin themselves
        )
        .options(selectinload(models.User.profile)) # Eager load profile for UserSchema
    )
    result = await db.execute(stmt)
    employees = result.scalars().all()
    return employees 

@router.get(
    "/me/startups-freelancers",
    response_model=schemas.space.SpaceTenantResponse, # Use the new schema
    dependencies=[Depends(get_current_user_with_roles(required_roles=["CORP_ADMIN"]))],
)
async def list_my_space_startups_freelancers(
    current_user: models.User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """List Startups and Freelancers assigned to the Corp Admin's managed space."""
    managed_space = await get_managed_space(db, current_user)
    tenants: List[schemas.space.TenantInfo] = []

    # Fetch Freelancers
    freelancer_stmt = (
        select(models.User)
        .where(
            models.User.space_id == managed_space.id,
            models.User.role == "FREELANCER"
        )
        .options(selectinload(models.User.profile)) # Eager load profile
    )
    freelancer_result = await db.execute(freelancer_stmt)
    freelancers = freelancer_result.scalars().all()
    for f_user in freelancers:
        # Convert the ORM user model (f_user) to BasicUser schema
        basic_user_details = schemas.space.BasicUser.from_orm(f_user)
        tenants.append(schemas.space.FreelancerTenantInfo(details=basic_user_details))

    # Fetch Startups (distinct startup_ids from users in the space)
    startup_users_stmt = (
        select(models.User.startup_id, models.Startup, func.count(models.User.id).label("member_count"))
        .join(models.Startup, models.User.startup_id == models.Startup.id) # Join User with Startup
        .where(
            models.User.space_id == managed_space.id,
            models.User.startup_id.isnot(None),
            # Optionally filter by roles if needed, e.g., only STARTUP_ADMIN or STARTUP_MEMBER
            models.User.role.in_(["STARTUP_ADMIN", "STARTUP_MEMBER"])
        )
        .group_by(models.User.startup_id, models.Startup.id, models.Startup.name)
    )
    startup_result = await db.execute(startup_users_stmt)
    
    # Process results: (startup_id, Startup object, member_count)
    # The direct Startup object from the join might already be loaded if relationship is set up well.
    # If not, we might need another query or rely on from_orm from a fully loaded Startup model.

    for row in startup_result.all(): # Using .all() to get named tuples if columns are selected
        startup_model = row.Startup # Access the Startup model instance from the row
        member_count = row.member_count
        # Ensure BasicStartup or a similar schema is used for details
        tenants.append(schemas.space.StartupTenantInfo(
            details=schemas.organization.Startup.from_orm(startup_model), # Use your actual Startup schema
            member_count=member_count
        ))

    return schemas.space.SpaceTenantResponse(tenants=tenants)

@router.post(
    "/me/workstations/assign",
    response_model=schemas.space.WorkstationAssignmentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(get_current_user_with_roles(required_roles=["CORP_ADMIN"]))],
)
async def assign_workstation_to_user(
    assignment_data: schemas.space.WorkstationAssignmentRequest,
    current_user: models.User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Assign a user to a workstation within the Corp Admin's managed space."""
    managed_space = await get_managed_space(db, current_user)

    # 1. Verify the user to be assigned exists and is part of this space or a startup in this space
    user_to_assign = await db.get(models.User, assignment_data.user_id)
    if not user_to_assign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User to assign not found")

    # Check if user is in the same space or their startup is in the same space
    is_freelancer_in_space = user_to_assign.space_id == managed_space.id and user_to_assign.role == "FREELANCER"
    
    is_startup_member_in_space = False
    if user_to_assign.startup_id:
        startup_of_user = await db.get(models.Startup, user_to_assign.startup_id)
        if startup_of_user and startup_of_user.space_id == managed_space.id:
            is_startup_member_in_space = True

    if not (is_freelancer_in_space or is_startup_member_in_space):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not a freelancer or part of a startup within the managed space."
        )

    # 2. Verify the workstation exists and is part of the managed space and is available
    workstation = await db.get(models.Workstation, assignment_data.workstation_id)
    if not workstation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workstation not found")
    if workstation.space_id != managed_space.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Workstation is not part of the managed space."
        )
    
    # Check if workstation is already assigned (assuming a direct link or an assignment table)
    # This example assumes a `user_id` field on `Workstation` model means it's occupied.
    # A more robust system would use a separate WorkstationAssignment table.
    existing_assignment_stmt = select(models.WorkstationAssignment).where(
        models.WorkstationAssignment.workstation_id == workstation.id,
        models.WorkstationAssignment.end_date.is_(None) # Active assignment
    )
    existing_assignment_result = await db.execute(existing_assignment_stmt)
    if existing_assignment_result.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Workstation is already occupied by another user."
        )
    
    # 3. Create the WorkstationAssignment record
    # This assumes you have a `WorkstationAssignment` model. 
    # If not, you might be directly updating workstation.user_id or workstation.status

    new_assignment = models.WorkstationAssignment(
        user_id=user_to_assign.id,
        workstation_id=workstation.id,
        space_id=managed_space.id,
        # created_by_id=current_user.id # Optional: if you track who made the assignment
    )
    db.add(new_assignment)
    await db.commit()
    await db.refresh(new_assignment)

    # Update workstation status if you have such a field
    # workstation.status = schemas.space.WorkstationStatus.OCCUPIED 
    # db.add(workstation) # Add workstation to session if status changed
    # await db.commit() # Commit workstation status change
    # await db.refresh(workstation) # Refresh workstation if needed

    return new_assignment # Directly return the ORM model, Pydantic will convert it 

@router.get(
    "/me/workstations",
    response_model=schemas.space.SpaceWorkstationListResponse,
    dependencies=[Depends(get_current_user_with_roles(required_roles=["CORP_ADMIN"]))],
)
async def list_my_space_workstations(
    current_user: models.User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """List all workstations within the Corp Admin's managed space, including status and occupant."""
    managed_space = await get_managed_space(db, current_user)

    # Fetch all workstations in the managed space
    stmt_workstations = (
        select(models.Workstation)
        .where(models.Workstation.space_id == managed_space.id)
        .options(
            selectinload(models.Workstation.active_assignment).options(
                selectinload(models.WorkstationAssignment.user).options(
                    selectinload(models.User.profile)
                )
            )
        ) # Eager load active assignment and the assigned user + profile
    )
    result_workstations = await db.execute(stmt_workstations)
    workstations_orm = result_workstations.scalars().unique().all()

    workstation_details_list: List[schemas.space.WorkstationDetail] = []

    for ws_orm in workstations_orm:
        occupant_info = None
        status = schemas.space.WorkstationStatus.AVAILABLE # Default to available

        active_assign = ws_orm.active_assignment # This is a WorkstationAssignment object or None
        
        if active_assign and active_assign.user:
            # User is present in the active assignment
            status = schemas.space.WorkstationStatus.OCCUPIED
            
            # Access full_name directly from the user model, fallback to email
            occupant_full_name = active_assign.user.full_name if active_assign.user.full_name else active_assign.user.email
            
            occupant_info = schemas.space.WorkstationTenantInfo(
                user_id=active_assign.user.id,
                full_name=occupant_full_name, # Corrected: use occupant_full_name
                email=active_assign.user.email # Always include email
            )
        elif ws_orm.status == schemas.space.WorkstationStatus.MAINTENANCE: # Check ws_orm.status directly
            status = schemas.space.WorkstationStatus.MAINTENANCE
        # No specific handling for 'RESERVED' here, defaults to AVAILABLE if not occupied or maintenance

        workstation_details_list.append(
            schemas.space.WorkstationDetail(
                id=ws_orm.id,
                name=ws_orm.name,
                status=status, # Use the determined status
                space_id=ws_orm.space_id,
                occupant=occupant_info,
                # features=ws_orm.features # Assuming features is a field on Workstation model
            )
        )

    return schemas.space.SpaceWorkstationListResponse(workstations=workstation_details_list)

@router.post(
    "/me/workstations/unassign",
    response_model=schemas.Message, # Corrected: Or a specific unassignment success response
    dependencies=[Depends(get_current_user_with_roles(required_roles=["CORP_ADMIN"]))],
)
async def unassign_user_from_workstation(
    unassign_data: schemas.space.WorkstationUnassignRequest,
    current_user: models.User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Unassign a user from a workstation by ending their current assignment."""
    managed_space = await get_managed_space(db, current_user)

    # 1. Find the workstation and verify it's in the managed space
    workstation = await db.get(models.Workstation, unassign_data.workstation_id)
    if not workstation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workstation not found")
    if workstation.space_id != managed_space.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Workstation is not part of the managed space."
        )

    # 2. Find the active assignment for this workstation
    # This assumes active_assignment relationship on Workstation model or querying WorkstationAssignment table
    active_assignment_stmt = (
        select(models.WorkstationAssignment)
        .where(
            models.WorkstationAssignment.workstation_id == workstation.id,
            models.WorkstationAssignment.end_date.is_(None) # Active assignment
        )
    )
    active_assignment_result = await db.execute(active_assignment_stmt)
    assignment_to_end = active_assignment_result.scalars().first()

    if not assignment_to_end:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active assignment found for this workstation."
        )
    
    # 3. End the assignment
    assignment_to_end.end_date = datetime.utcnow()
    db.add(assignment_to_end)
    await db.commit()
    await db.refresh(assignment_to_end)

    # Optional: Update workstation status if it has a status field that changes upon unassignment
    # if workstation.status == schemas.space.WorkstationStatus.OCCUPIED:
    #     workstation.status = schemas.space.WorkstationStatus.AVAILABLE
    #     db.add(workstation)
    #     await db.commit()

    return schemas.Message(message="User successfully unassigned from workstation.")

@router.get(
    "/me",
    response_model=schemas.space.ManagedSpaceDetail,
    dependencies=[Depends(get_current_user_with_roles(required_roles=["CORP_ADMIN"]))],
)
async def get_my_managed_space_details(
    current_user: models.User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed information about the space managed by the current Corp Admin."""
    managed_space = await get_managed_space(db, current_user) # Re-use the helper

    # Count workstations by status
    stmt_total = select(func.count(models.Workstation.id)).where(models.Workstation.space_id == managed_space.id)
    total_workstations = (await db.execute(stmt_total)).scalar_one_or_none() or 0

    stmt_maintenance = select(func.count(models.Workstation.id)).where(
        models.Workstation.space_id == managed_space.id,
        models.Workstation.status == "MAINTENANCE" # Assuming 'MAINTENANCE' is a string status
    )
    maintenance_workstations = (await db.execute(stmt_maintenance)).scalar_one_or_none() or 0

    # Count occupied workstations (active assignments)
    stmt_occupied = (
        select(func.count(models.WorkstationAssignment.id))
        .join(models.Workstation, models.WorkstationAssignment.workstation_id == models.Workstation.id)
        .where(
            models.Workstation.space_id == managed_space.id,
            models.WorkstationAssignment.end_date.is_(None)
        )
    )
    occupied_workstations = (await db.execute(stmt_occupied)).scalar_one_or_none() or 0
    
    available_workstations = total_workstations - occupied_workstations - maintenance_workstations

    return schemas.space.ManagedSpaceDetail(
        id=managed_space.id,
        name=managed_space.name,
        address=managed_space.address, # Assuming Space model has an address field
        total_workstations=total_workstations,
        occupied_workstations=occupied_workstations,
        available_workstations=max(0, available_workstations), # Ensure non-negative
        maintenance_workstations=maintenance_workstations,
        company_id=managed_space.company_id # Assuming Space model has company_id
    ) 

@router.put(
    "/me/workstations/{workstation_id}/status",
    response_model=schemas.space.WorkstationDetail, # Return updated workstation details
    dependencies=[Depends(get_current_user_with_roles(required_roles=["CORP_ADMIN"]))],
)
async def update_workstation_status(
    workstation_id: int,
    status_update: schemas.space.WorkstationStatusUpdateRequest,
    current_user: models.User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Update the status of a specific workstation within the Corp Admin's managed space."""
    managed_space = await get_managed_space(db, current_user)

    # 1. Fetch the workstation
    workstation = await db.get(models.Workstation, workstation_id)
    if not workstation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workstation not found")
    
    # 2. Verify workstation is in the managed space
    if workstation.space_id != managed_space.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Workstation is not part of the managed space."
        )

    new_status = status_update.status

    # 3. Logic for status update
    # Check for active assignment if attempting to set to AVAILABLE or MAINTENANCE when OCCUPIED
    active_assignment_stmt = select(models.WorkstationAssignment).where(
        models.WorkstationAssignment.workstation_id == workstation.id,
        models.WorkstationAssignment.end_date.is_(None)
    )
    active_assignment = (await db.execute(active_assignment_stmt)).scalars().first()

    if new_status == schemas.space.WorkstationStatus.AVAILABLE:
        if active_assignment:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot set to AVAILABLE. Workstation is currently occupied. Unassign first."
            )
        workstation.status = schemas.space.WorkstationStatus.AVAILABLE.value
    elif new_status == schemas.space.WorkstationStatus.MAINTENANCE:
        # Optionally, if setting to MAINTENANCE while occupied, you might want to end the assignment.
        # For now, let's assume you can mark it for maintenance even if assigned, 
        # but it won't be assignable to others.
        workstation.status = schemas.space.WorkstationStatus.MAINTENANCE.value
    elif new_status == schemas.space.WorkstationStatus.OCCUPIED:
        # This status should typically be set implicitly by assigning a user.
        # Explicitly setting to OCCUPIED without an assignment might be disallowed.
        if not active_assignment:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot set to OCCUPIED. No active assignment found. Assign a user instead."
            )
        # If it's already occupied and this is called, it's a bit redundant, but we can just affirm.
        workstation.status = schemas.space.WorkstationStatus.OCCUPIED.value 
        # Note: The `Workstation.status` field might be a direct string representation of the enum.
        # Or it could be derived. The current logic assumes it's a direct field to store these states.

    db.add(workstation)
    await db.commit()
    await db.refresh(workstation)
    
    # Re-fetch occupant details for the response
    occupant_info_resp = None
    if active_assignment and active_assignment.user:
        user_profile = active_assignment.user.profile # Assumes profile is loaded or accessible
        # It might be better to reload the user and profile if not already loaded via workstation relations
        if not user_profile: # Attempt to load if not present (e.g., if active_assignment was just from a simple query)
            await db.refresh(active_assignment.user, relationship_names=["profile"])
            user_profile = active_assignment.user.profile

        occupant_info_resp = schemas.space.WorkstationTenantInfo(
            user_id=active_assignment.user.id,
            full_name=user_profile.full_name if user_profile else active_assignment.user.email,
            email=active_assignment.user.email
        )

    return schemas.space.WorkstationDetail(
        id=workstation.id,
        name=workstation.name,
        status=schemas.space.WorkstationStatus(workstation.status), # Convert string back to Enum for response
        space_id=workstation.space_id,
        occupant=occupant_info_resp if workstation.status == schemas.space.WorkstationStatus.OCCUPIED.value else None
    ) 

@router.get("/me/users", response_model=SpaceUsersListResponse, dependencies=[Depends(get_current_user_with_roles(required_roles=['CORP_ADMIN']))])
async def list_all_users_in_managed_space(
    current_user: models.User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """List all users belonging to the Corp Admin's managed space."""
    managed_space = await get_managed_space(db, current_user)

    stmt = (
        select(models.User)
        .where(models.User.space_id == managed_space.id)
        .options(selectinload(models.User.profile)) # Eager load profile
    )
    result = await db.execute(stmt)
    users_orm = result.scalars().all()
    
    # Convert ORM users to BasicUser schema
    users = [BasicUser.from_orm(user_obj) for user_obj in users_orm]
    
    return SpaceUsersListResponse(users=users) 

@router.get(
    "/me/member-requests",
    response_model=List[schemas.notification.Notification], # Use the existing Notification schema
    dependencies=[Depends(get_current_user_with_roles(required_roles=['CORP_ADMIN']))]
)
async def list_pending_member_requests(
    current_user: models.User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """List pending member requests for the Corporate Admin's managed space.
    These are identified by unread notifications of type 'member_request'.
    """
    # The notification is targeted to the Corp Admin (current_user.id)
    # The type is 'member_request'
    # We only want unread notifications
    pending_requests_stmt = (
        select(models.Notification)
        .where(
            models.Notification.user_id == current_user.id,
            models.Notification.type == "member_request",
            models.Notification.is_read == False
        )
        .order_by(models.Notification.created_at.desc())
    )
    result = await db.execute(pending_requests_stmt)
    member_requests = result.scalars().all()
    return member_requests

@router.post(
    "/me/member-requests/{notification_id}/approve",
    response_model=schemas.Message, # Or a more specific response
    dependencies=[Depends(get_current_user_with_roles(required_roles=['CORP_ADMIN']))]
)
async def approve_member_request(
    notification_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
): 
    managed_space = await get_managed_space(db, current_user)

    notification = await crud.crud_notification.get_notification_by_id(db=db, notification_id=notification_id)

    if not notification or \
       notification.user_id != current_user.id or \
       notification.type != "member_request" or \
       notification.is_read:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Pending member request notification not found or already actioned."
        )

    email_to_add = notification.reference
    startup_id_from_notification = notification.related_entity_id

    if not email_to_add or not startup_id_from_notification:
        # Mark as read to prevent re-processing a bad notification
        await crud.crud_notification.mark_notification_as_read(db=db, notification=notification)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Notification is missing email reference or startup ID."
        )

    # 2. Fetch Startup
    startup_to_join = await crud.crud_organization.get_startup(db, startup_id=startup_id_from_notification)
    if not startup_to_join:
        await crud.crud_notification.mark_notification_as_read(db=db, notification=notification)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Startup with ID {startup_id_from_notification} not found.")

    # 3. Verify Startup is in the Corp Admin's managed space
    # THIS ASSUMES Startup model has a space_id linking it to a SpaceNode
    if startup_to_join.space_id != managed_space.id: 
        await crud.crud_notification.mark_notification_as_read(db=db, notification=notification)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail=f"Startup {startup_to_join.name} is not part of your managed space."
        )

    # 4. Find or Create User
    user_to_add = await crud.user.get_user_by_email(db, email=email_to_add)
    new_user_created = False

    if user_to_add:
        # User exists, update them
        if user_to_add.startup_id and user_to_add.startup_id != startup_to_join.id:
             await crud.crud_notification.mark_notification_as_read(db=db, notification=notification) # Mark original as read
             # Notify original requester (Startup Admin) - find them first
             stmt_startup_admin = select(models.User).where(models.User.startup_id == startup_to_join.id, models.User.role == "STARTUP_ADMIN")
             startup_admin_user_result = await db.execute(stmt_startup_admin)
             startup_admin_user = startup_admin_user_result.scalars().first()
             if startup_admin_user:
                await crud.crud_notification.create_notification(
                    db, user_id=startup_admin_user.id, type="member_request_failed", 
                    message=f"Request to add {email_to_add} failed: User already belongs to another startup."
                )
             raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"User {email_to_add} already belongs to another startup.")
        
        user_to_add.startup_id = startup_to_join.id
        user_to_add.space_id = managed_space.id # Ensure they are in this space
        user_to_add.role = "STARTUP_MEMBER" # Default role for member request
        user_to_add.status = "ACTIVE"
        user_to_add.is_active = True
        db.add(user_to_add)
    else:
        # User does not exist, create them
        # TODO: Secure password generation/handling. For now, placeholder.
        # Consider what full_name should be - perhaps from original request if provided
        placeholder_password = "DefaultPassword123!" # THIS IS INSECURE
        new_user_data = UserCreate(
            email=email_to_add, 
            full_name=email_to_add.split('@')[0], # Basic default full_name
            password=placeholder_password, 
            role="STARTUP_MEMBER"
        )
        try:
            user_to_add = await crud.user.create_user(db, obj_in=new_user_data)
            new_user_created = True
            # Update status, space_id, startup_id for the new user
            # create_user sets initial status and is_active=False
            user_to_add.startup_id = startup_to_join.id
            user_to_add.space_id = managed_space.id
            # user_to_add.status = "ACTIVE" # create_user sets PENDING_VERIFICATION, let's make them active directly
            # user_to_add.is_active = True
            # Use UserUpdateInternal to make them active
            update_payload = UserUpdateInternal(status="ACTIVE", is_active=True)
            user_to_add = await crud.user.update_user_internal(db=db, db_obj=user_to_add, obj_in=update_payload)
            db.add(user_to_add) # Ensure it's added to session if update_user_internal doesn't handle it fully
        except Exception as e:
            # Log error, notify original requester if possible
            await crud.crud_notification.mark_notification_as_read(db=db, notification=notification) # Mark original as read
            # Notify Startup Admin of failure
            stmt_startup_admin_fail = select(models.User).where(models.User.startup_id == startup_to_join.id, models.User.role == "STARTUP_ADMIN")
            startup_admin_user_fail_result = await db.execute(stmt_startup_admin_fail)
            startup_admin_user_fail = startup_admin_user_fail_result.scalars().first()
            if startup_admin_user_fail:
                await crud.crud_notification.create_notification(
                    db, user_id=startup_admin_user_fail.id, type="member_request_failed", 
                    message=f"Request to add {email_to_add} failed: Could not create user account. Error: {str(e)}"
                )
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create user: {str(e)}")

    try:
        await db.commit()
        await db.refresh(user_to_add)
    except Exception as e:
        await db.rollback()
        # Mark original as read to prevent loop if commit fails
        # but be careful with db session state here.
        # Best to try marking read outside a failed transaction context or handle idempotency
        # For now, we assume notification read can proceed or is handled by caller on error.
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error during user update/creation: {str(e)}")

    # 5. Mark original notification as read
    await crud.crud_notification.mark_notification_as_read(db=db, notification=notification)

    # 6. Notify Startup Admin of success
    stmt_startup_admin_success = select(models.User).where(models.User.startup_id == startup_to_join.id, models.User.role == "STARTUP_ADMIN")
    startup_admin_user_success_result = await db.execute(stmt_startup_admin_success)
    startup_admin_user_success = startup_admin_user_success_result.scalars().first()

    if startup_admin_user_success:
        success_message = f"Your request to add {email_to_add} to startup '{startup_to_join.name}' has been approved."
        if new_user_created:
            success_message += " A new account has been created."
        await crud.crud_notification.create_notification(
            db, user_id=startup_admin_user_success.id, type="member_request_approved", 
            message=success_message
        )
    
    return schemas.Message(message=f"User {email_to_add} successfully added to startup {startup_to_join.name}.")

@router.post(
    "/me/member-requests/{notification_id}/deny",
    response_model=schemas.Message,
    dependencies=[Depends(get_current_user_with_roles(required_roles=['CORP_ADMIN']))]
)
async def deny_member_request(
    notification_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    notification = await crud.crud_notification.get_notification_by_id(db=db, notification_id=notification_id)

    if not notification or \
       notification.user_id != current_user.id or \
       notification.type != "member_request" or \
       notification.is_read:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Pending member request notification not found or already actioned."
        )

    email_denied = notification.reference
    startup_id_from_notification = notification.related_entity_id

    # Mark original notification as read first
    await crud.crud_notification.mark_notification_as_read(db=db, notification=notification)

    # Notify Startup Admin of denial
    if startup_id_from_notification:
        startup_involved = await crud.crud_organization.get_startup(db, startup_id=startup_id_from_notification)
        startup_name = startup_involved.name if startup_involved else "the startup"
        
        stmt_startup_admin = select(models.User).where(models.User.startup_id == startup_id_from_notification, models.User.role == "STARTUP_ADMIN")
        startup_admin_user_result = await db.execute(stmt_startup_admin)
        startup_admin_user = startup_admin_user_result.scalars().first()

        if startup_admin_user:
            await crud.crud_notification.create_notification(
                db, 
                user_id=startup_admin_user.id, 
                type="member_request_denied", 
                message=f"Your request to add {email_denied if email_denied else 'a member'} to {startup_name} has been denied."
            )
            # We commit here as mark_notification_as_read also commits.
            # If create_notification also commits, it's fine. If not, this commit covers both.
            await db.commit() 
        else:
            # Log if startup admin not found, but proceed with denial confirmation
            print(f"Warning: Could not find Startup Admin for startup ID {startup_id_from_notification} to notify of denial.")
            await db.commit() # Commit the read status of original notification
    else:
        # If no startup_id, still commit the read status
        await db.commit()

    return schemas.Message(message=f"Member request for {email_denied if email_denied else 'a member'} has been denied.")

@router.get("/me/stats/connections", response_model=SpaceConnectionStatsResponse, dependencies=[Depends(get_current_user_with_roles(required_roles=['CORP_ADMIN']))])
async def get_space_connection_stats(
    current_user: models.User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Calculates the total number of internal connections among startup tenants in the managed space."""
    managed_space = await get_managed_space(db=db, current_user=current_user)

    # This Cypher query will fail if db is an SQLAlchemy session.
    # This endpoint needs to be re-evaluated based on whether it's meant for Neo4j or SQLAlchemy.
    # For now, to prevent startup error, I will comment out the Neo4j logic and return a default.
    # TODO: Implement connection stats logic using SQLAlchemy or ensure Neo4j setup is correct.
    # cypher_query = """
    # MATCH (space:SpaceNode {id: $space_id})
    # // Find startups in this space
    # OPTIONAL MATCH (startup:StartupNode)-[:IN_SPACE]->(space)
    # // Count members for each startup
    # WITH startup, COUNT{(user:UserNode)-[:WORKS_FOR]->(startup)} AS member_count
    # // Calculate connections for this startup: n * (n - 1) / 2
    # // Ensure member_count > 1 to avoid division by zero or negative results if a startup has 0 or 1 member
    # WITH CASE WHEN member_count > 1 THEN member_count * (member_count - 1) / 2 ELSE 0 END AS startup_connections
    # // Sum connections across all startups in the space
    # RETURN sum(startup_connections) AS total_connections
    # """

    # result = await db.run(cypher_query, space_id=managed_space.id) # This would fail
    # data = await result.single()

    # total_connections = data["total_connections"] if data and data["total_connections"] is not None else 0
    total_connections = 0 # Placeholder

    return SpaceConnectionStatsResponse(total_connections=int(total_connections)) 

@router.get(
    "/my-space/startups",
    response_model=List[BasicStartupSchema],
    dependencies=[Depends(get_current_user_with_roles(required_roles=["CORP_ADMIN"]))],
    tags=["spaces", "corp_admin"]
)
async def list_startups_in_my_managed_space(
    current_user: models.User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Lists all startups within the current Corporate Admin's managed space.
    Requires CORP_ADMIN role and the admin to be associated with a space.
    """
    if not current_user.space_id:
        # This check might be redundant if get_managed_space is used and handles it,
        # but it's a good direct check specific to this endpoint's logic.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Corporate Admin is not directly associated with a space."
        )
    
    # Alternative: Use the get_managed_space helper if it aligns with how CORP_ADMIN's space is determined
    # managed_space = await get_managed_space(db, current_user)
    # if not managed_space:
    #     # get_managed_space would raise 404 if no space, this is an additional safeguard or alternative logic.
    #     raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No managed space found for admin.")

    startups_orm = await crud_organization.get_startups_by_space_id(db, space_id=current_user.space_id)
    
    # Convert ORM objects to Pydantic schemas if not automatically handled by FastAPI response_model
    # Pydantic v2 with from_attributes=True should handle this, but explicit conversion is also an option:
    # return [BasicStartupSchema.from_orm(startup) for startup in startups_orm]
    return startups_orm 