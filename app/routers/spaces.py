from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload, noload
from sqlalchemy import func, Text
from typing import List, Optional, Dict
from datetime import datetime, timedelta
import logging # Added for detailed logging
import re # Add re for parsing
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.db.session import get_db
from app import crud, models, schemas
from app.security import get_current_active_user, get_current_user_with_roles, get_current_user, get_current_email_verified_user
from app.schemas.user import User as UserSchema, UserCreate, UserUpdateInternal, UserDetail as UserDetailSchema
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
    SpaceConnectionStatsResponse, # Added SpaceConnectionStatsResponse
    WorkstationCreate, # Added WorkstationCreate
    WorkstationUpdate, # Added WorkstationUpdate
    WorkstationAssignmentResponse, # Ensure this is imported if not already
    AddUserToSpaceRequest, # Added AddUserToSpaceRequest
    BrowseableSpaceListResponse, # Added BrowseableSpaceListResponse
    BrowseableSpace, # Added BrowseableSpace
    BasicSpace, # Added BasicSpace
    UserWorkstationInfo, # Added UserWorkstationInfo
)
from app.models.organization import Company, Startup # Changed from app.models.company import CompanyNode
from app.crud import crud_organization # Import crud_organization
from app.schemas.organization import BasicStartup as BasicStartupSchema, Company as CompanySchema, Startup as StartupSchema # Import BasicStartup schema
from app.models.enums import UserRole, NotificationType, UserStatus # Import UserRole, NotificationType, and UserStatus Enums
from app.utils.email import send_email, send_employee_invitation_email # Import the send_email utility
from app.core.config import settings # Import settings for FRONTEND_URL
from app.crud.crud_space import assign_user_to_workstation as crud_assign_user_to_workstation # Added
from app.crud.crud_space import unassign_user_from_workstation as crud_unassign_user_from_workstation # Added
from app.crud import crud_space, crud_interest, crud_notification # Add imports
from app.schemas.user_profile import UserProfile as UserProfileSchema
from app.schemas.interest import InterestResponse, InterestDetail
# It's good practice to import sio if type hinting or direct use in module scope is needed,
# but for request.app.state.sio, it's accessed at runtime.
from app.socket_instance import sio # Example if direct import was used

router = APIRouter()
logger = logging.getLogger(__name__)

async def get_managed_space(
    stmt: select,
    db: AsyncSession,
    current_user: models.User
):
    result = await db.execute(stmt)
    managed_space = result.scalar_one_or_none()
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
    managed_space = await crud.crud_space.get_managed_space(db, current_user)
    if not managed_space:
        return []

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
        .options(
            selectinload(models.User.profile), # Eager load profile for UserSchema
            noload(models.User.managed_space)  # Do not attempt to load managed_space for these users
        )
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
    logger.info(f"User {current_user.email} (ID: {current_user.id}) fetching startups & freelancers.")

    managed_space = await crud.crud_space.get_managed_space(db, current_user)
    if not managed_space:
        return schemas.space.SpaceTenantResponse(tenants=[])
        
    logger.info(f"Managed space ID: {managed_space.id}, Name: {managed_space.name}")

    tenants: List[schemas.space.TenantInfo] = []

    # Fetch Freelancers
    freelancer_stmt = (
        select(models.User)
        .where(
            models.User.space_id == managed_space.id,
            func.lower(models.User.role.cast(Text)) == "freelancer"  # Case-insensitive with cast
        )
        .options(selectinload(models.User.profile)) # Eager load profile
    )
    freelancer_result = await db.execute(freelancer_stmt)
    freelancers = freelancer_result.scalars().all()
    for f_user in freelancers:
        # Convert the ORM user model (f_user) to BasicUser schema
        basic_user_details = schemas.space.BasicUser.from_orm(f_user)
        tenants.append(schemas.space.FreelancerTenantInfo(details=basic_user_details))

    # Fetch Startups directly assigned to the managed space
    startups_in_space_stmt = (
        select(models.Startup)
        .where(models.Startup.space_id == managed_space.id)
        .options(selectinload(models.Startup.direct_members).selectinload(models.User.profile)) # Eager load members and their profiles
    )
    startups_in_space_result = await db.execute(startups_in_space_stmt)
    startups_orm = startups_in_space_result.scalars().unique().all()
    logger.info(f"Found {len(startups_orm)} startups linked to space ID {managed_space.id}.")

    for startup_model in startups_orm:
        logger.info(f"Processing startup ID: {startup_model.id}, Name: {startup_model.name}")
        logger.info(f"  Number of direct_members for startup {startup_model.id}: {len(startup_model.direct_members)}")
        # Filter active members with correct roles for the count
        current_startup_members_for_count = []
        for member in startup_model.direct_members:
            is_correct_role = member.role in [UserRole.STARTUP_ADMIN, UserRole.STARTUP_MEMBER]
            logger.info(f"  Member ID: {member.id}, Email: {member.email}, is_active: {member.is_active}, role: {member.role} (type: {type(member.role)}), is_correct_role: {is_correct_role}")
            if member.is_active and is_correct_role:
                current_startup_members_for_count.append(member)
        
        member_count = len(current_startup_members_for_count)
        logger.info(f"  Calculated member_count for startup {startup_model.id}: {member_count} (after filtering)")
        
        if member_count > 0: # Only include startups that have active members with specified roles
            logger.info(f"  Adding startup {startup_model.id} to tenants list.")
            tenants.append(schemas.space.StartupTenantInfo(
                details=schemas.organization.Startup.from_orm(startup_model),
                member_count=member_count
            ))
        else:
            logger.info(f"  Skipping startup {startup_model.id} as member_count is 0.")
            
    logger.info(f"Total tenants (freelancers + startups) to return: {len(tenants)}")
    return schemas.space.SpaceTenantResponse(tenants=tenants)

@router.post(
    "/me/workstations/assign",
    response_model=schemas.space.WorkstationAssignmentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(get_current_user_with_roles(required_roles=["CORP_ADMIN"]))],
)
async def assign_workstation_to_user(
    assignment_data: schemas.space.WorkstationAssignmentRequest,
    request: Request, 
    current_user: models.User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Assign a user to a workstation within the Corp Admin's managed space."""
    managed_space = await crud.crud_space.get_managed_space(db, current_user)
    if not managed_space:
        raise HTTPException(status_code=404, detail="Cannot assign workstation: No managed space found.")

    try:
        assignment_result = await crud_assign_user_to_workstation(
            db=db,
            user_id=assignment_data.user_id,
            workstation_id=assignment_data.workstation_id,
            space_id=managed_space.id,
            assigning_admin_id=current_user.id
        )
        if not assignment_result:
            # This implies an issue like user/workstation not found as per CRUD logic
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to assign workstation. User or workstation might not be valid.")
        
        new_assignment, workstation_name_for_event = assignment_result

        if not new_assignment or not workstation_name_for_event:
             # Should not happen if CRUD returns valid tuple or raises error
            logging.error(f"CRUD assign_user_to_workstation returned unexpected None for assignment or name. Assignment: {new_assignment}, Name: {workstation_name_for_event}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to get all assignment details.")

        # Emit Socket.IO event to the assigned user
        try:
            sio_server = request.app.state.sio
            target_user_id_str = str(assignment_data.user_id)
            event_data = {"status": "assigned", "workstation_name": workstation_name_for_event}
            await sio_server.emit('workstation_changed', data=event_data, room=target_user_id_str)
            logging.info(f"Emitted 'workstation_changed' event to user room: {target_user_id_str} with data: {event_data}")
        except AttributeError:
            logging.error("Socket.IO server (sio) not found in request.app.state")
        except Exception as e:
            logging.error(f"Failed to emit Socket.IO event for workstation assignment: {e}", exc_info=True)

        return WorkstationAssignmentResponse(
            id=new_assignment.id, 
            user_id=new_assignment.user_id, 
            workstation_id=new_assignment.workstation_id, 
            space_id=new_assignment.space_id,
            start_date=new_assignment.start_date,
            end_date=new_assignment.end_date
        )

    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        # Log the exception details for debugging
        logging.getLogger(__name__).error(f"Error assigning workstation: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred while assigning the workstation.")

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
    managed_space = await crud.crud_space.get_managed_space(db, current_user)
    if not managed_space:
        return schemas.space.SpaceWorkstationListResponse(workstations=[])

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
            
            # Use from_orm to correctly handle aliases
            occupant_info = schemas.space.WorkstationTenantInfo.from_orm(active_assign.user)
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
    request: Request, # Added request
    current_user: models.User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Unassign a user from a workstation within the Corp Admin's managed space."""
    logger.info(
        f"Corp Admin {current_user.email} (ID: {current_user.id}) attempting to unassign workstation ID: {unassign_data.workstation_id}"
    )
    managed_space = await crud.crud_space.get_managed_space(db, current_user)
    if not managed_space:
        raise HTTPException(status_code=404, detail="Cannot unassign workstation: No managed space found.")

    try:
        # 1. Fetch the workstation to ensure it's in the managed space
        #    and to get its active assignment.
        #    The crud.crud_space.get_workstation_by_id_and_space_id function already loads
        #    active_assignment and active_assignment.user via selectinload options.
        workstation_to_unassign = await crud.crud_space.get_workstation_by_id_and_space_id(
            db,
            workstation_id=unassign_data.workstation_id,
            space_id=managed_space.id
        )

        if not workstation_to_unassign:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workstation not found in your managed space."
            )

        # 2. Check for an active assignment on this workstation.
        active_assignment = workstation_to_unassign.active_assignment

        if not active_assignment or not hasattr(active_assignment, 'user_id') or not active_assignment.user_id:
            # Handle cases where active_assignment might be None or not have a user_id
            logger.warning(f"Workstation '{workstation_to_unassign.name}' (ID: {workstation_to_unassign.id}) is not actively assigned to any user.")
        raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Workstation '{workstation_to_unassign.name}' is not currently assigned to any user."
            )
        
        assigned_user_id = active_assignment.user_id
        logger.info(f"Found active assignment for user ID: {assigned_user_id} on workstation ID: {workstation_to_unassign.id}")

        # 3. Now call the CRUD function with the determined user_id
        success = await crud_unassign_user_from_workstation(
            db=db,
            user_id=assigned_user_id,
            workstation_id=workstation_to_unassign.id, # Use ID from fetched workstation for consistency
            space_id=managed_space.id,
            unassigning_admin_id=current_user.id,
        )

        if success:
            # Emit Socket.IO event to the unassigned user
            try:
                sio_server = request.app.state.sio
                target_user_id_str = str(assigned_user_id)
                event_data = {"status": "unassigned", "workstation_name": workstation_to_unassign.name}
                await sio_server.emit('workstation_changed', data=event_data, room=target_user_id_str)
                logging.info(f"Emitted 'workstation_changed' event to user room: {target_user_id_str} with data: {event_data}")
            except AttributeError:
                logging.error("Socket.IO server (sio) not found in request.app.state for unassign")
            except Exception as e:
                logging.error(f"Failed to emit Socket.IO event for workstation unassignment: {e}", exc_info=True)
            
            return schemas.Message(message=f"User successfully unassigned from workstation '{workstation_to_unassign.name}'.")
        else:
            logger.error(
                f"crud_unassign_user_from_workstation returned False unexpectedly for user {assigned_user_id} from w_id {workstation_to_unassign.id}"
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to unassign user from workstation due to an unexpected issue.",
            )
    except ValueError as ve: 
        logger.warning(f"ValueError during unassign: {str(ve)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except HTTPException: 
        raise
    except Exception as e:
        logger.error(f"Error unassigning workstation: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while unassigning the workstation.",
        )

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
    managed_space = await crud.crud_space.get_managed_space(db, current_user) # Re-use the helper
    if not managed_space:
        raise HTTPException(status_code=404, detail="No managed space details found.")

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
    managed_space = await crud.crud_space.get_managed_space(db, current_user)
    if not managed_space:
        raise HTTPException(status_code=404, detail="Cannot update workstation: No managed space found.")

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
            await db.refresh(active_assignment.user, attribute_names=["profile"])
            user_profile = active_assignment.user.profile

        occupant_info_resp = schemas.space.WorkstationTenantInfo.from_orm(active_assignment.user)

    return schemas.space.WorkstationDetail(
        id=workstation.id,
        name=workstation.name,
        status=schemas.space.WorkstationStatus(workstation.status), # Convert string back to Enum for response
        space_id=workstation.space_id,
        occupant=occupant_info_resp if workstation.status == schemas.space.WorkstationStatus.OCCUPIED.value else None
    ) 

@router.get("/me/users", response_model=SpaceUsersListResponse, dependencies=[Depends(get_current_user_with_roles(['CORP_ADMIN']))])
async def list_all_users_in_managed_space(
    current_user: models.User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Lists all users within the current Corporate Admin's managed space, including the admin."""
    managed_space = await crud.crud_space.get_managed_space(db, current_user)
    if not managed_space:
        return SpaceUsersListResponse(users=[])

    stmt = (
        select(models.User)
        .where(models.User.space_id == managed_space.id)
        .options(
            selectinload(models.User.profile) # Only load what's needed for BasicUser, which is not much.
        )
    )
    result = await db.execute(stmt)
    users_in_space_orm = result.scalars().unique().all()
    
    users_data = []
    user_ids_in_space = set()

    for user in users_in_space_orm:
        users_data.append({
            "id": user.id,
            "full_name": user.full_name,
            "email": user.email,
            "role": user.role.value if user.role else None,
        })
        user_ids_in_space.add(user.id)

    # Ensure the admin is in the list, as they might not have the space_id set directly
    if current_user.id not in user_ids_in_space:
        # The current_user object from dependency is fully loaded
        users_data.append({
            "id": current_user.id,
            "full_name": current_user.full_name,
            "email": current_user.email,
            "role": current_user.role.value if current_user.role else None,
        })
        
    return SpaceUsersListResponse(users=jsonable_encoder(users_data))

@router.delete(
    "/me/users/{user_id}",
    response_model=UserSchema,
    dependencies=[Depends(get_current_user_with_roles(required_roles=["CORP_ADMIN"]))],
    status_code=status.HTTP_200_OK,
    summary="Remove a user from the managed space",
    responses={
        400: {"description": "Invalid request, e.g., admin trying to remove self"},
        403: {"description": "User is not a member of the admin's managed space"},
        404: {"description": "User not found"},
    }
)
async def remove_user_from_managed_space(
    user_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Allows a Corporate Admin to remove any user (employee, startup member, or freelancer)
    from their managed space. This action disassociates the user from the space.
    """
    user_to_remove = await crud.crud_user.get_user_by_id(db, user_id=user_id)
    if not user_to_remove:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    try:
        updated_user = await crud.crud_space.remove_user_from_space(
            db, user_to_remove=user_to_remove, removing_admin=current_user
        )
        # TODO: Send a notification to the removed user.
        return updated_user
    except ValueError as e:
        # Check for specific error messages to return appropriate status codes
        if "not in the admin's managed space" in str(e):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to remove user {user_id} from space by admin {current_user.id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred.")

@router.get(
    "/me/member-requests",
    response_model=List[schemas.notification.Notification], # Use the existing Notification schema
    dependencies=[Depends(get_current_user_with_roles(['CORP_ADMIN']))]
)
async def list_pending_member_requests(
    current_user: models.User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """List member requests for the Corporate Admin's managed space.
    These are identified by notifications of type 'member_request' and that are unread.
    Once actioned (approved/denied), the notification is marked as read and will no longer appear in this list.
    """
    member_request_notifications_stmt = (
        select(models.Notification)
        .where(
            models.Notification.user_id == current_user.id,
            models.Notification.type == NotificationType.member_request.value,
            models.Notification.is_read == False  # Only fetch unread member requests
        )
        .order_by(models.Notification.created_at.desc())
    )
    result = await db.execute(member_request_notifications_stmt)
    member_requests = result.scalars().all()
    return member_requests

def _parse_member_request_reference(reference: Optional[str]) -> Dict[str, str]:
    """
    Parses the notification reference string for member requests.
    Handles formats like "key1=value1,key2=value2" or "key1:value1;key2:value2".
    It also handles cases where "requested_email" might be used instead of "email".
    """
    parsed_data = {}
    if not reference:
        return parsed_data

    # Normalize separators: replace semicolons with commas
    normalized_reference = reference.replace(';', ',')

    pairs = normalized_reference.split(',')
    for pair in pairs:
        if '=' in pair:
            key, value = pair.split('=', 1)
            parsed_data[key.strip()] = value.strip()
        elif ':' in pair: # Fallback for colon, though equals is preferred after normalization
            key, value = pair.split(':', 1)
            parsed_data[key.strip()] = value.strip()
    
    # Ensure 'email' key is present if 'requested_email' was used
    if "requested_email" in parsed_data and "email" not in parsed_data:
        parsed_data["email"] = parsed_data["requested_email"]

    return parsed_data

@router.post(
    "/me/member-requests/{notification_id}/approve",
    response_model=schemas.Message, # Or a more specific response
    dependencies=[Depends(get_current_user_with_roles(['CORP_ADMIN']))]
)
async def approve_member_request(
    notification_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    logger.info(f"Corp Admin {current_user.email} attempting to approve member request via notification ID: {notification_id}")

    original_notification = await crud.notification.get_notification(db, notification_id=notification_id)
    if not original_notification:
        logger.warning(f"Approve failed: Original member_request notification ID {notification_id} not found.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Original member request notification not found")

    if original_notification.user_id != current_user.id:
        logger.warning(f"Approve failed: Corp Admin {current_user.email} does not own notification ID {notification_id}.")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You are not authorized to action this notification")

    if original_notification.type != NotificationType.member_request: # Ensure it's accessing .value if NotificationType is an Enum
        logger.warning(f"Approve failed: Notification ID {notification_id} is not of type 'member_request', but '{original_notification.type}'.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Notification is not a member request type")

    # Parse reference: "user_id:X,startup_id:Y,requested_by_user_id:Z"
    parsed_ref = _parse_member_request_reference(original_notification.reference)
    user_to_activate_id_str = parsed_ref.get("user_id")
    startup_id_str = parsed_ref.get("startup_id")
    requesting_startup_admin_id_str = parsed_ref.get("requested_by_user_id")

    if not user_to_activate_id_str or not startup_id_str or not requesting_startup_admin_id_str:
        logger.error(f"Approve failed: Could not parse all required IDs from notification {notification_id} reference: '{original_notification.reference}'. Parsed: {parsed_ref}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not parse member request details")

    try:
        user_to_activate_id = int(user_to_activate_id_str)
        startup_id = int(startup_id_str)
        requesting_startup_admin_id = int(requesting_startup_admin_id_str)
    except ValueError:
        logger.error(f"Approve failed: Invalid ID format in notification {notification_id} reference: '{original_notification.reference}'.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Invalid ID format in member request")

    managed_space = await crud.crud_space.get_managed_space(db, current_user) # Corp Admin's space

    user_to_activate = await crud.user.get_user(db, user_id=user_to_activate_id)
    if not user_to_activate:
        logger.warning(f"Approve failed: User to activate (ID: {user_to_activate_id}) not found.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User to activate not found")

    startup_to_join = await crud.organization.get_startup(db, startup_id=startup_id)
    if not startup_to_join:
        logger.warning(f"Approve failed: Startup (ID: {startup_id}) not found for user {user_to_activate.email}.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Startup to join not found")

    if startup_to_join.space_id != managed_space.id:
        logger.warning(f"Approve failed: Startup {startup_to_join.name} (ID: {startup_id}) is not in Corp Admin {current_user.email}'s space (Space ID: {managed_space.id}). Startup's space ID: {startup_to_join.space_id}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Startup is not managed by you or in your space.")

    occupied_workstations = await crud.space.get_occupied_workstation_count(db, space_id=managed_space.id)
    if managed_space.total_workstations is not None and occupied_workstations >= managed_space.total_workstations:
        logger.warning(f"Approve failed for user {user_to_activate.email}: No available workstations in space {managed_space.name} (ID: {managed_space.id}). Total: {managed_space.total_workstations}, Occupied: {occupied_workstations}")
        await crud.notification.create_notification(
            db,
            user_id=requesting_startup_admin_id,
            type=NotificationType.member_request_denied,
            message=f"Could not approve member for {startup_to_join.name}: No available workstations in space '{managed_space.name}'.",
            reference=f"user_id:{user_to_activate_id},startup_id:{startup_id},reason:no_workstations"
        )
        await crud.notification.mark_as_read(db, notification_id=original_notification.id)
        await db.commit() # Corrected first indentation
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No available workstations to approve this member.")

    try:
        updated_user_data = UserUpdateInternal(
            status=models.UserStatus.ACTIVE,
            is_active=True,
            startup_id=startup_id,
            space_id=managed_space.id
        )
        user_to_activate = await crud.user.update_user_internal(db=db, db_obj=user_to_activate, obj_in=updated_user_data)
        logger.info(f"User {user_to_activate.email} (ID: {user_to_activate_id}) activated and assigned to startup {startup_to_join.name} (ID: {startup_id}) and space {managed_space.name} (ID: {managed_space.id}).")

        original_notification.type = NotificationType.member_request_completed.value
        original_notification.is_read = True
        db.add(original_notification)
        logger.info(f"Updated original member_request notification ID {original_notification.id} to type 'member_request_completed' and marked as read.")

        approval_message = f"Your request to add {user_to_activate.full_name or user_to_activate.email} to {startup_to_join.name} has been approved."
        await crud.notification.create_notification(
            db,
            user_id=requesting_startup_admin_id,
            type=NotificationType.member_request_approved,
            message=approval_message,
            reference=f"approved_user_id:{user_to_activate_id},startup_id:{startup_id}"
        )
        logger.info(f"Created 'member_request_approved' notification for Startup Admin ID {requesting_startup_admin_id}.")

        # Automatically create a connection between the new user and the space admin
        try:
            await crud.crud_connection.create_accepted_connection(
                db, user_one_id=user_to_activate.id, user_two_id=current_user.id
            )
            logger.info(f"Successfully created an accepted connection between new user {user_to_activate.email} and space admin {current_user.email}.")
        except Exception as e:
            # Log the error but don't fail the entire approval process
            logger.error(f"Failed to create automatic connection for user {user_to_activate.email} and admin {current_user.email}. Error: {e}", exc_info=True)

        await db.commit()
        logger.info(f"Database committed successfully for approval of user {user_to_activate.email}.")

        try:
            if user_to_activate.hashed_password:
                email_subject = "Welcome to ShareYourSpace!"
                login_url = f"{settings.FRONTEND_URL}/login"
                profile_url = f"{settings.FRONTEND_URL}/profile"
                html_content = f'''
                <p>Hi {user_to_activate.full_name or user_to_activate.email},</p>
                <p>Welcome to ShareYourSpace! Your account has been activated, and you\'ve been added to the startup "{startup_to_join.name}" in the "{managed_space.name}" space.</p>
                <p>Please <a href="{login_url}">log in</a> to complete your profile and start exploring.</p>
                <p>You can update your profile details <a href="{profile_url}">here</a>.</p>
                <p>Thanks,<br>The ShareYourSpace Team</p>
                '''
                send_email(to=user_to_activate.email, subject=email_subject, html_content=html_content)
                logger.info(f"Standard welcome email successfully sent to activated user {user_to_activate.email}.")
            else:
                # Ensure crud_set_password_token and send_set_initial_password_email are correctly imported or defined
                # For now, assuming they exist as per original file structure to focus on indentation.
                # from app.crud import crud_set_password_token # Example: if it should be imported
                # from app.utils.email import send_set_initial_password_email # Example: if it should be imported
                
                set_pwd_token = await crud.crud_set_password_token.create_set_password_token(db, user_id=user_to_activate.id) # Check 'crud.crud_set_password_token'
                await db.commit()
                await db.refresh(set_pwd_token)

                await crud.send_set_initial_password_email( # Check 'crud.send_set_initial_password_email'
                    to_email=user_to_activate.email,
                    token=set_pwd_token.token,
                    user_full_name=user_to_activate.full_name
                )
                logger.info(f"'Set initial password' email successfully sent to new user {user_to_activate.email}.")

        except AttributeError as ae: # Catch if crud_set_password_token or send_set_initial_password_email are missing
            logger.error(f"Email sending utilities missing or misconfigured: {ae}", exc_info=True)
        except Exception as e:
            logger.error(f"Failed to send email to {user_to_activate.email} after approval. Error: {e}", exc_info=True)

        return schemas.Message(message=f"Member {user_to_activate.email} approved and activated for startup {startup_to_join.name}.")

    except HTTPException: 
        raise
    except Exception as e:
        logger.error(f"An unexpected error occurred during member request approval for notification ID {notification_id}. User: {current_user.email}. Error: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred while approving the member request.")

@router.post(
    "/me/member-requests/{notification_id}/deny",
    response_model=schemas.Message,
    dependencies=[Depends(get_current_user_with_roles(['CORP_ADMIN']))]
)
async def deny_member_request(
    notification_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    logger.info(f"Corp Admin {current_user.email} attempting to deny member request via notification ID: {notification_id}")

    original_notification = await crud.notification.get_notification(db=db, notification_id=notification_id)

    if not original_notification or \
       original_notification.user_id != current_user.id or \
       original_notification.type != NotificationType.member_request: # Check current type is member_request
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pending member request notification not found or not applicable for denial."
        )

    # Parse reference before committing changes to notification type
    parsed_ref = _parse_member_request_reference(original_notification.reference)
    # user_to_deny_id_str = parsed_ref.get("user_id") # If needed for denial logic/logging
    email_denied = parsed_ref.get("email") # Kept for message consistency if needed, though user_id is primary
    startup_id_str = parsed_ref.get("startup_id")
    requesting_startup_admin_id_str = parsed_ref.get("requested_by_user_id")
    
    startup_id_from_notification: Optional[int] = None
    if startup_id_str:
        try:
            startup_id_from_notification = int(startup_id_str)
        except ValueError:
            logger.warning(f"Deny request: Invalid startup_id format in notification {notification_id} reference: '{startup_id_str}'.")
            # Decide if this is critical enough to stop or just log

    requesting_startup_admin_id: Optional[int] = None
    if requesting_startup_admin_id_str:
        try:
            requesting_startup_admin_id = int(requesting_startup_admin_id_str)
        except ValueError:
            logger.warning(f"Deny request: Invalid requesting_startup_admin_id format in notification {notification_id} reference: '{requesting_startup_admin_id_str}'.")

    startup_name = "the startup" # Fallback name
    if startup_id_from_notification:
        startup_involved = await crud.organization.get_startup(db, startup_id=startup_id_from_notification)
        if startup_involved:
            startup_name = startup_involved.name

    # Update the original notification's type to completed and mark as read
    original_notification.type = NotificationType.member_request_completed.value
    original_notification.is_read = True
    db.add(original_notification)
    logger.info(f"Updated original member_request notification ID {original_notification.id} to type 'member_request_completed' and marked as read for denial.")

    # Create a new notification for the Startup Admin who made the request
    if requesting_startup_admin_id:
        try:
            await crud.notification.create_notification(
                    db,
                user_id=requesting_startup_admin_id,
                    type=NotificationType.member_request_denied,
                message=f"Your request to add {email_denied if email_denied else 'a member'} to '{startup_name}' has been denied by the Space Admin.",
                reference=f"denied_user_email:{email_denied},startup_id:{startup_id_from_notification}" # Reference original identifiers
                )
            logger.info(f"Created 'member_request_denied' notification for Startup Admin ID {requesting_startup_admin_id}.")
        except Exception as e: 
            logger.error(f"Failed to create 'member_request_denied' notification for user {requesting_startup_admin_id}. Error: {e}")
            # Non-critical, main action is denying the request by changing original notification type
    try:
        await db.commit()
        logger.info(f"Denial for member request (original notification ID {notification_id}) committed.")
    except Exception as e:
        await db.rollback()
        logger.error(f"Database error during member request denial for notification ID {notification_id}. Error: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to process denial due to a database error.")

    return schemas.Message(message=f"Member request for '{email_denied if email_denied else 'a user'}' to join '{startup_name}' has been denied.")

@router.get("/me/stats", response_model=SpaceConnectionStatsResponse, dependencies=[Depends(get_current_user_with_roles(required_roles=['CORP_ADMIN']))])
async def get_space_connection_stats(
    current_user: models.User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Calculates and returns key statistics for the corporate admin's managed space."""
    managed_space = await crud.crud_space.get_managed_space(db=db, current_user=current_user)
    if not managed_space:
        return SpaceConnectionStatsResponse(
            total_tenants=0,
            total_workstations=0,
            occupied_workstations=0,
            connections_this_month=0,
        )

    # Get total tenants (Startups + Freelancers in the space)
    freelancer_count_stmt = select(func.count(models.User.id)).where(
        models.User.space_id == managed_space.id,
        models.User.role == 'FREELANCER',
        models.User.is_active == True
    )
    freelancer_count = (await db.execute(freelancer_count_stmt)).scalar_one_or_none() or 0

    startup_count_stmt = select(func.count(models.Startup.id)).where(models.Startup.space_id == managed_space.id)
    startup_count = (await db.execute(startup_count_stmt)).scalar_one_or_none() or 0
    
    total_tenants = freelancer_count + startup_count

    # Calculate occupied workstations
    occupied_workstations_stmt = select(func.count(models.Workstation.id)).where(
        models.Workstation.space_id == managed_space.id,
        models.Workstation.status == 'OCCUPIED'
    )
    occupied_workstations = (await db.execute(occupied_workstations_stmt)).scalar_one_or_none() or 0

    # Get connections in the last 30 days for that space
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    
    # This counts users who were added or became active in the space recently
    # Note: This is a proxy for "connections". A true "connection" might be defined differently (e.g., user-to-user)
    connections_stmt = select(func.count(models.User.id)).where(
        models.User.space_id == managed_space.id,
        models.User.is_active == True,
        models.User.updated_at >= thirty_days_ago # Assuming updated_at reflects activation/addition date
    )
    connections_this_month = (await db.execute(connections_stmt)).scalar_one_or_none() or 0

    return SpaceConnectionStatsResponse(
        total_tenants=total_tenants,
        total_workstations=managed_space.total_workstations,
        occupied_workstations=occupied_workstations,
        connections_this_month=connections_this_month,
    )

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
    Requires CORP_ADMIN role. Returns an empty list if no space is managed.
    """
    managed_space = await crud.crud_space.get_managed_space(db, current_user)
    if not managed_space:
        return []
    
    startups_orm = await crud_organization.get_startups_by_space_id(db, space_id=managed_space.id)
    return startups_orm

# --- New Workstation Management Endpoints by Corp Admin ---

@router.post(
    "/me/workstations",
    response_model=WorkstationDetail,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(get_current_user_with_roles(required_roles=["CORP_ADMIN"]))],
    tags=["corp_admin", "workstations"]
)
async def create_new_workstation(
    workstation_in: WorkstationCreate,
    current_user: models.User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Allows a Corporate Admin to create a new workstation in their managed space."""
    managed_space = await crud.crud_space.get_managed_space(db, current_user)
    if not managed_space:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create workstation")
    
    created_workstation = await crud.crud_space.create_workstation(
        db=db, workstation_in=workstation_in, space_id=managed_space.id
    )
    if not created_workstation:
        # This case should ideally be handled by specific exceptions in CRUD if space not found
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create workstation")
    
    # Prepare response - WorkstationDetail needs occupant info, which will be None for new workstations
    return WorkstationDetail(
        id=created_workstation.id,
        name=created_workstation.name,
        status=created_workstation.status,
        space_id=created_workstation.space_id,
        occupant=None
    )

@router.put(
    "/me/workstations/{workstation_id}",
    response_model=WorkstationDetail,
    dependencies=[Depends(get_current_user_with_roles(required_roles=["CORP_ADMIN"]))],
    tags=["corp_admin", "workstations"]
)
async def update_existing_workstation(
    workstation_id: int,
    workstation_in: WorkstationUpdate,
    current_user: models.User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Allows a Corporate Admin to update a workstation in their managed space."""
    managed_space = await crud.crud_space.get_managed_space(db, current_user)
    if not managed_space:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No managed space found.")
    
    workstation_obj = await crud.crud_space.get_workstation_by_id_and_space_id(
        db=db, workstation_id=workstation_id, space_id=managed_space.id
    )
    if not workstation_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workstation not found in your managed space")

    updated_workstation = await crud.crud_space.update_workstation(
        db=db, workstation_obj=workstation_obj, workstation_in=workstation_in
    )
    
    # Refetch occupant details if needed for the response, or pass from workstation_obj if already loaded
    # For simplicity, if status changes to AVAILABLE, occupant is None. Otherwise, it might still have an occupant.
    occupant_info = None
    if updated_workstation.status == schemas.space.WorkstationStatus.OCCUPIED and workstation_obj.active_assignment:
         # This simplified logic assumes active_assignment is readily available and has user details.
         # A more robust way would be to query user details based on active_assignment.user_id
        if workstation_obj.active_assignment.user:
            occupant_info = schemas.space.WorkstationTenantInfo.from_orm(workstation_obj.active_assignment.user)

    return WorkstationDetail(
        id=updated_workstation.id,
        name=updated_workstation.name,
        status=updated_workstation.status,
        space_id=updated_workstation.space_id,
        occupant=occupant_info
    )

@router.delete(
    "/me/workstations/{workstation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(get_current_user_with_roles(required_roles=["CORP_ADMIN"]))],
    tags=["corp_admin", "workstations"]
)
async def delete_existing_workstation(
    workstation_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Allows a Corporate Admin to delete a workstation from their managed space."""
    managed_space = await crud.crud_space.get_managed_space(db, current_user)
    if not managed_space:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No managed space found.")
    
    try:
        success = await crud.crud_space.delete_workstation(
            db=db, workstation_id=workstation_id, space_id=managed_space.id
        )
        if not success:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workstation not found or could not be deleted")
    except Exception as e:
        logger.error(f"Error deleting workstation {workstation_id} by user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred while deleting the workstation.")

    return # Returns 204 No Content on success

@router.post(
    "/me/invite-employee",
    response_model=schemas.Message,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(get_current_user_with_roles(required_roles=["CORP_ADMIN"]))],
    tags=["corp_admin", "invitations"]
)
async def invite_employee_to_space(
    invite_in: schemas.invitation.EmployeeInviteCreate,
    current_user: models.User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Allows a Corporate Admin to invite a new employee to their company and managed space."""
    managed_space = await crud.crud_space.get_managed_space(db, current_user)
    if not managed_space or not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="You do not manage a space or are not associated with a company."
        )

    existing_user = await crud.crud_user.get_user_by_email(db, email=invite_in.email)
    if existing_user and existing_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An active user with this email already exists."
        )

    invitation_create_schema = schemas.invitation.InvitationCreate(
        email=invite_in.email,
        company_id=current_user.company_id,
        space_id=managed_space.id,
        invited_by_user_id=current_user.id
    )
    invitation = await crud.invitation.create(db, obj_in=invitation_create_schema)

    try:
        await send_employee_invitation_email(
            to_email=invite_in.email,
            invitation_token=invitation.invitation_token,
            admin_name=current_user.full_name or "The Admin",
            company_name=managed_space.company.name if managed_space.company else "our company"
        )
    except Exception as e:
        logger.error(f"Failed to send invitation email to {invite_in.email}: {e}", exc_info=True)
        return schemas.Message(
            message=f"Invitation created for {invite_in.email}, but failed to send email. Please try resending."
        )

    return schemas.Message(message=f"Invitation successfully sent to {invite_in.email}.")

# --- End New Workstation Management Endpoints --- 

@router.post(
    "/me/add-user",
    response_model=UserDetailSchema,
    dependencies=[Depends(get_current_user_with_roles(required_roles=["CORP_ADMIN"]))],
    status_code=status.HTTP_200_OK,
    summary="Add a user to the managed space",
)
async def add_user_to_managed_space(
    add_user_request: schemas.space.AddUserToSpaceRequest,
    current_user: models.User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Allows a Corporate Admin to add an existing waitlisted user to their managed space.
    """
    managed_space = await crud.crud_space.get_managed_space(db, current_user)
    if not managed_space:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No managed space found.")

    user_to_add = await crud.crud_user.get_user_by_id(db, user_id=add_user_request.user_id)
    if not user_to_add:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    if user_to_add.status not in [UserStatus.WAITLISTED, UserStatus.PENDING_VERIFICATION]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"User is not waitlisted. Current status: {user_to_add.status.value}")

    company_id = None
    if add_user_request.role == UserRole.CORP_EMPLOYEE:
        if not current_user.company_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Admin is not associated with a company.")
        company_id = current_user.company_id

    # Store IDs before try block to avoid lazy loading issues in exception handler
    user_id_to_add = add_user_request.user_id
    admin_id = current_user.id
    try:
        updated_user = await crud.crud_space.add_user_to_space(
            db,
            user_to_add=user_to_add,
            space=managed_space,
            role=add_user_request.role,
            company_id=company_id,
            startup_id=add_user_request.startup_id
        )

        # Update the interest status from PENDING to ACCEPTED
        interest = await crud_interest.interest.get_by_user_and_space(
            db, user_id=user_to_add.id, space_id=managed_space.id
        )
        if interest and interest.status == models.interest.InterestStatus.PENDING:
            interest.status = models.interest.InterestStatus.ACCEPTED
            db.add(interest)
            logger.info(f"Updated interest {interest.id} to ACCEPTED for user {user_to_add.id}")
            
        # Auto-connect the new user with the admin
        await crud.crud_connection.create_accepted_connection(
            db, user_one_id=updated_user.id, user_two_id=current_user.id
        )
        logger.info(f"Auto-connected user {updated_user.email} with admin {current_user.email}")
        
        await db.commit()
        
        user_data = {
            "id": updated_user.id,
            "email": updated_user.email,
            "full_name": updated_user.full_name,
            "is_active": updated_user.is_active,
            "status": updated_user.status,
            "role": updated_user.role,
            "company_id": updated_user.company_id,
            "startup_id": updated_user.startup_id,
            "space_id": updated_user.space_id,
            "created_at": updated_user.created_at,
            "updated_at": updated_user.updated_at,
            "referral_code": updated_user.referral_code,
            "community_badge": updated_user.community_badge,
            "profile": None,
            "space": None,
            "company": None,
            "startup": None,
            "managed_space": None,
            "current_workstation": None,
        }

        if updated_user.profile:
            user_data['profile'] = UserProfileSchema.model_validate(updated_user.profile).model_dump()

        if updated_user.space:
            user_data['space'] = BasicSpace.model_validate(updated_user.space).model_dump()

        if updated_user.company:
            user_data['company'] = CompanySchema.model_validate(updated_user.company).model_dump()
        
        if updated_user.startup:
            user_data['startup'] = StartupSchema.model_validate(updated_user.startup).model_dump()

        active_assignment = next((a for a in updated_user.assignments if a.end_date is None and a.workstation), None)
        if active_assignment and active_assignment.workstation:
            user_data['current_workstation'] = UserWorkstationInfo(
                workstation_id=active_assignment.workstation.id,
                workstation_name=active_assignment.workstation.name,
                assignment_start_date=active_assignment.start_date
            ).model_dump()

        return JSONResponse(content=jsonable_encoder(user_data))
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to add user {user_id_to_add} to space by admin {admin_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred.") 

@router.post("", response_model=schemas.space.SpaceCreationResponse, status_code=status.HTTP_201_CREATED)
async def create_space_node(
    space_in: schemas.admin.SpaceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Create a new SpaceNode.
    Accessible by an authenticated user, typically a new Corp Admin creating their first space.
    Returns both the new space and the updated user details.
    """
    if current_user.id != space_in.corporate_admin_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only create a space for yourself as the admin."
        )

    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User does not have a company associated. Cannot create a space."
        )

    if space_in.company_id != current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only create a space for your own company."
        )

    company = await crud.crud_organization.get_company(db, company_id=current_user.company_id)
    if not company:
        raise HTTPException(status_code=404, detail=f"Company with id {current_user.company_id} not found.")

    space_in.company_id = current_user.company_id

    new_space = await crud.crud_space.create_space(db=db, obj_in=space_in)

    # After creating the space, update the user's status to ACTIVE
    user_update = UserUpdateInternal(status=UserStatus.ACTIVE, space_id=new_space.id)
    updated_user = await crud.crud_user.update_user_internal(db=db, db_obj=current_user, obj_in=user_update)
    
    # Eager load all necessary details for the user response
    refreshed_user = await crud.crud_user.get_user_details_for_profile(db, user_id=updated_user.id)
    
    # Explicitly reload the company relationship to ensure it's up-to-date
    if refreshed_user:
        await db.refresh(refreshed_user, attribute_names=["company"])

    return {"space": new_space, "user": refreshed_user}

@router.post(
    "/{space_id}/express-interest",
    response_model=schemas.message.Message,
    status_code=status.HTTP_201_CREATED,
    tags=["interests", "spaces"]
)
async def express_interest_in_space(
    space_id: int,
    current_user: models.User = Depends(get_current_email_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Allows a user to express interest in joining a space.
    This creates an Interest object and notifies the space admin.
    """
    if current_user.status != UserStatus.WAITLISTED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only waitlisted users can express interest in a space."
        )

    space = await crud_space.get_space_by_id(db, space_id=space_id)
    
    if not space:
        raise HTTPException(status_code=404, detail="Space not found")
    
    if not space.corporate_admin_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This space is not ready to accept expressions of interest yet."
        )

    if not space.company:
        raise HTTPException(status_code=404, detail="Space is not associated with a company")

    existing_interest = await crud_interest.interest.get_by_user_and_space(
        db, user_id=current_user.id, space_id=space_id
    )
    if existing_interest:
        raise HTTPException(
            status_code=400,
            detail="You have already expressed interest in this space."
        )

    interest = await crud_interest.interest.create_with_user_and_space(
        db, obj_in=schemas.interest.InterestCreate(space_id=space_id), user_id=current_user.id
    )

    # Create a notification for the space admin
    await crud_notification.create_notification(
        db=db,
        user_id=space.corporate_admin_id,
        type=NotificationType.INTEREST_EXPRESSED,
        message=f"{current_user.full_name or current_user.email} has expressed interest in your space: {space.name}.",
        related_entity_id=current_user.id,
    )

    return {"message": "Your interest has been registered successfully."}

@router.get("/browseable", response_model=schemas.space.BrowseableSpaceListResponse)
async def list_browseable_spaces(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Lists all spaces available for users to browse and express interest in.
    Also indicates the current user's interest status for each space.
    """
    all_spaces = await crud_space.get_spaces(db, skip=0, limit=100)
    user_interests = await crud_interest.interest.get_interests_by_user(db, user_id=current_user.id)
    
    interest_map = {interest.space_id: interest for interest in user_interests}
    
    browseable_spaces = []
    for space in all_spaces:
        status = 'not_interested'
        if space.id in interest_map:
            # You could have more detailed statuses if you track accepted/rejected
            status = 'interested'
            
        browseable_spaces.append(
            schemas.space.BrowseableSpace(
                id=space.id,
                name=space.name,
                address=space.address,
                company_name=space.company.name if space.company else "N/A",
                company_id=space.company.id if space.company else None,
                interest_status=status
            )
        )
        
    return {"spaces": browseable_spaces} 

@router.post(
    "/me/add-startup/{startup_id}",
    response_model=BasicStartupSchema,
    dependencies=[Depends(get_current_user_with_roles(required_roles=["CORP_ADMIN"]))],
    status_code=status.HTTP_200_OK
)
async def add_startup_to_my_space(
    startup_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Allows a Corporate Admin to add a waitlisted startup to their managed space.
    """
    managed_space = await crud.crud_space.get_managed_space(db, current_user)
    if not managed_space:
        raise HTTPException(status_code=404, detail="No managed space found.")

    startup = await crud.crud_organization.get_startup(db, startup_id=startup_id)
    if not startup:
        raise HTTPException(status_code=404, detail="Startup not found.")

    if startup.status != UserStatus.WAITLISTED:
        raise HTTPException(status_code=400, detail="Startup is not on the waitlist.")

    updated_startup = await crud.crud_organization.add_startup_to_space(
        db, startup=startup, space_id=managed_space.id
    )

    return updated_startup 

@router.get(
    "/me/interests",
    response_model=InterestResponse,
    dependencies=[Depends(get_current_user_with_roles(required_roles=["CORP_ADMIN"]))],
)
async def list_my_space_interests(
    current_user: models.User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """List pending interests for the Corp Admin's managed space."""
    managed_space = await crud.crud_space.get_managed_space(db, current_user)
    if not managed_space:
        return InterestResponse(interests=[])

    all_interests = await crud_interest.interest.get_interests_for_space(db, space_id=managed_space.id)
    
    pending_interests = [
        interest for interest in all_interests if interest.status == models.interest.InterestStatus.PENDING
    ]

    detailed_interests = []
    for interest in pending_interests:
        user = interest.user
        startup_details = None
        if user.role == UserRole.STARTUP_ADMIN and user.startup_id:
            startup = await crud_organization.get_startup(db, startup_id=user.startup_id)
            if startup:
                startup_details = StartupSchema.from_orm(startup)

        detailed_interests.append(
            InterestDetail(
                id=interest.id,
                status=interest.status,
                user=user, # Pass the user object with profile loaded
                startup=startup_details,
            )
        )

    return InterestResponse(interests=detailed_interests) 

@router.get(
    "/{space_id}/admin",
    response_model=Optional[schemas.user.BasicUserInfo],
    dependencies=[Depends(get_current_active_user)]
)
async def get_space_admin_details(
    space_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Gets the basic details of the corporate admin for a given space."""
    admin = await crud.crud_space.get_space_admin(db, space_id=space_id)
    if not admin:
        # It's okay for a space to not have an admin, so return null instead of 404
        return None
    return schemas.user.BasicUserInfo(id=admin.id, full_name=admin.full_name) 