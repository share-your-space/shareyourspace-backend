from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from typing import List, Optional, Union
import re
from sqlalchemy.orm import selectinload
import logging

from app import crud, models, schemas
from app.models.enums import UserRole, UserStatus, NotificationType, InterestStatus, InvitationStatus
from app.schemas.admin import StartupUpdateAdmin, MemberSlotUpdate, AddTenantRequest
from app.schemas.dashboard import DashboardStats

logger = logging.getLogger(__name__)

async def get_dashboard_stats(db: AsyncSession, *, company_id: int) -> DashboardStats:
    """
    Gathers key statistics for the corporate admin dashboard.
    """
    # Total spaces for the company
    spaces_query = select(func.count(models.SpaceNode.id)).where(models.SpaceNode.company_id == company_id)
    total_spaces = await db.scalar(spaces_query)

    # Get all space IDs for the company to use in subsequent queries
    space_ids_query = select(models.SpaceNode.id).where(models.SpaceNode.company_id == company_id)
    space_ids = (await db.execute(space_ids_query)).scalars().all()

    total_workstations = 0
    occupied_workstations = 0
    active_bookings = 0
    if space_ids:
        # Total workstations in all spaces
        workstations_query = select(func.count(models.Workstation.id)).where(models.Workstation.space_id.in_(space_ids))
        total_workstations = await db.scalar(workstations_query)

        # Occupied workstations
        occupied_query = select(func.count(models.Workstation.id)).where(
            models.Workstation.space_id.in_(space_ids),
            models.Workstation.status == 'OCCUPIED'
        )
        occupied_workstations = await db.scalar(occupied_query)

        # Active bookings
        active_bookings_query = select(func.count(models.Booking.id)).where(
            models.Booking.workstation_id.in_(
                select(models.Workstation.id).where(models.Workstation.space_id.in_(space_ids))
            ),
            models.Booking.end_date >= func.now(),
            models.Booking.status == 'CONFIRMED'
        )
        active_bookings = await db.scalar(active_bookings_query)

    # Total tenants (freelancers + startups)
    freelancers_query = select(func.count(models.User.id)).where(
        models.User.space_id.in_(space_ids),
        models.User.role == UserRole.FREELANCER
    )
    startups_query = select(func.count(models.organization.Startup.id)).where(
        models.organization.Startup.space_id.in_(space_ids)
    )
    total_freelancers = await db.scalar(freelancers_query)
    total_startups = await db.scalar(startups_query)
    total_tenants = total_freelancers + total_startups

    # Pending invites sent by any admin of this company
    pending_invites_query = select(func.count(models.Invitation.id)).where(
        models.Invitation.company_id == company_id,
        models.Invitation.status == InvitationStatus.PENDING
    )
    pending_invites = await db.scalar(pending_invites_query)

    return DashboardStats(
        total_spaces=total_spaces,
        total_workstations=total_workstations,
        occupied_workstations=occupied_workstations,
        available_workstations=total_workstations - occupied_workstations,
        total_tenants=total_tenants,
        pending_invites=pending_invites,
        active_bookings=active_bookings,
    )


async def get_all_company_workstations(db: AsyncSession, *, company_id: int) -> List[models.Workstation]:
    """
    Retrieves all workstations across all spaces for a given company.
    """
    # Get all space IDs for the company
    space_ids_query = select(models.SpaceNode.id).where(models.SpaceNode.company_id == company_id)
    space_ids_result = await db.execute(space_ids_query)
    space_ids = space_ids_result.scalars().all()

    if not space_ids:
        return []

    # Get all workstations in those spaces
    workstations_query = (
        select(models.Workstation)
        .options(
            selectinload(models.Workstation.space),
            selectinload(models.Workstation.current_booking).options(
                selectinload(models.Booking.user)
            )
        )
        .where(models.Workstation.space_id.in_(space_ids))
        .order_by(models.Workstation.name)
    )
    workstations_result = await db.execute(workstations_query)
    workstations = workstations_result.scalars().unique().all()

    return workstations


async def get_all_company_tenants(db: AsyncSession, *, company_id: int) -> List[Union[models.User, models.organization.Startup]]:
    """
    Retrieves all tenants (freelancers and startups) across all spaces for a given company.
    """
    # Get all space IDs for the company
    space_ids_query = select(models.SpaceNode.id).where(models.SpaceNode.company_id == company_id)
    space_ids_result = await db.execute(space_ids_query)
    space_ids = space_ids_result.scalars().all()

    if not space_ids:
        return []

    # Get all freelancers in those spaces
    freelancers_query = (
        select(models.User)
        .options(selectinload(models.User.profile))
        .where(
            models.User.space_id.in_(space_ids),
            models.User.role == UserRole.FREELANCER
        )
    )
    freelancers_result = await db.execute(freelancers_query)
    freelancers = freelancers_result.scalars().unique().all()

    # Get all startups in those spaces
    startups_query = (
        select(models.organization.Startup)
        .options(
            selectinload(models.organization.Startup.profile),
            selectinload(models.organization.Startup.direct_members).options(
                selectinload(models.User.profile)
            )
        )
        .where(models.organization.Startup.space_id.in_(space_ids))
    )
    startups_result = await db.execute(startups_query)
    startups = startups_result.scalars().unique().all()

    return freelancers + startups


async def add_tenant_to_space(
    db: AsyncSession,
    *,
    space_id: int,
    tenant_data: AddTenantRequest,
    current_user: models.User,
) -> None:
    """
    Adds a tenant to a space or invites them if no prior interest was expressed.
    """
    space = await check_admin_space_permission(db, current_user=current_user, space_id=space_id)

    user_id_to_check = None
    startup_id_to_check = None
    
    if tenant_data.user_id:
        user = await crud.crud_user.get_user_by_id(db, user_id=tenant_data.user_id)
        if not user or user.role != UserRole.FREELANCER:
            raise HTTPException(status_code=404, detail="Freelancer not found.")
        user_id_to_check = user.id
        
    elif tenant_data.startup_id:
        startup = await crud.crud_organization.get_startup(db, startup_id=tenant_data.startup_id)
        if not startup:
            raise HTTPException(status_code=404, detail="Startup not found.")
        startup_id_to_check = startup.id
        # The user associated with the interest/invitation is the startup admin
        startup_admin = next((m for m in startup.direct_members if m.role == UserRole.STARTUP_ADMIN), None)
        if not startup_admin:
            raise HTTPException(status_code=400, detail="Startup has no admin to invite.")
        user_id_to_check = startup_admin.id

    # Check for existing interest from the user/startup for THIS space
    existing_interest = await crud.crud_interest.interest.get_by_tenant_and_space(
        db, user_id=user_id_to_check, startup_id=startup_id_to_check, space_id=space_id
    )

    if existing_interest and existing_interest.status == InterestStatus.PENDING:
        # User expressed interest, so add them directly
        if startup_id_to_check:
            await crud.crud_organization.add_startup_to_space(db, startup_id=startup_id_to_check, space_id=space.id)
        else: # It's a freelancer
            await crud.crud_user.add_user_to_space(db, user_id=user_id_to_check, space_id=space.id)
        
        existing_interest.status = InterestStatus.ACCEPTED
        db.add(existing_interest)
        
        await crud.crud_notification.create_notification(
            db, user_id=user_id_to_check, type=NotificationType.ADDED_TO_SPACE,
            message=f"Your interest was accepted and you've been added to the space '{space.name}'!",
            link=f"/spaces/{space.id}/profile"
        )
    else:
        # No prior interest, so send an invitation
        new_invite = models.Interest(
            space_id=space_id,
            user_id=user_id_to_check,
            startup_id=startup_id_to_check,
            status=InterestStatus.INVITED
        )
        db.add(new_invite)
        
        await crud.crud_notification.create_notification(
            db, user_id=user_id_to_check, type=NotificationType.INVITATION_TO_SPACE,
            message=f"You have been invited to join the space '{space.name}' by {current_user.full_name}.",
            link="/notifications" # Or a dedicated invitations page
        )

    await db.commit()

async def check_admin_space_permission(db: AsyncSession, *, current_user: models.User, space_id: int) -> models.SpaceNode:
    """
    Checks if a Corp Admin has permission to manage a space.
    Returns the space if they have permission, otherwise raises HTTPException.
    """
    if current_user.role != UserRole.CORP_ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is not a Corporate Admin.")
    if not current_user.company_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin is not associated with a company.")
        
    space = await crud.crud_space.get_space_by_id(db, space_id=space_id)
    if not space:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Space not found.")
    
    if space.company_id != current_user.company_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin does not have permission for this space.")
        
    return space

async def search_waitlisted_profiles(db: AsyncSession, *, query: str) -> List[models.User]:
    similar_profiles_with_distance = await crud.crud_user_profile.ai_search_waitlisted_profiles(db, query=query)
    users = [profile.user for profile, distance in similar_profiles_with_distance]
    return users

async def browse_waitlist(
    db: AsyncSession,
    *,
    search: Optional[str],
    type: Optional[str],
    sort_by: Optional[str],
    skip: int,
    limit: int,
    current_user: models.User,
    space_id: Optional[int] = None,
) -> List[Union[schemas.admin.WaitlistedUser, schemas.admin.WaitlistedStartup]]:
    logger.info(f"--- Starting browse_waitlist execution for space_id: {space_id} ---")
    
    filter_by_interest = sort_by == "interest"
    
    results = []
    if not type or type == 'freelancer':
        freelancers_data = await crud.crud_user.get_waitlisted_freelancers(
            db,
            search_term=search,
            space_id=space_id,
            filter_by_interest=filter_by_interest,
        )
        for data in freelancers_data:
            results.append(schemas.admin.WaitlistedUser.model_validate(data))

    if not type or type == 'startup':
        startups_data = await crud.crud_organization.get_waitlisted_startups(
            db,
            search_term=search,
            space_id=space_id,
            filter_by_interest=filter_by_interest,
        )
        for data in startups_data:
            results.append(schemas.admin.WaitlistedStartup.model_validate(data))
            
    # Sorting logic
    if sort_by == "name_asc":
        results.sort(key=lambda x: getattr(x, 'name', getattr(x, 'full_name', '') or ''))
    elif sort_by == "name_desc":
        results.sort(key=lambda x: getattr(x, 'name', getattr(x, 'full_name', '') or ''), reverse=True)
    else:  # Default to sorting by interest
        # Sort by name first for a stable secondary sort order
        results.sort(key=lambda x: getattr(x, 'name', getattr(x, 'full_name', '') or ''))
        # Then sort by interest status, which becomes the primary sort order
        results.sort(key=lambda x: x.expressed_interest, reverse=True)
    
    logger.info("--- Finished browse_waitlist execution ---")
    
    # Apply pagination AFTER sorting
    paginated_results = results[skip : skip + limit]
    return paginated_results

async def update_startup_info(
    db: AsyncSession, *, space_id: int, startup_id: int, startup_update: StartupUpdateAdmin, current_user: models.User
) -> models.organization.Startup:
    await check_admin_space_permission(db, current_user=current_user, space_id=space_id)
    
    startup = await crud.crud_organization.get_startup(db, startup_id=startup_id)
    if not startup or startup.space_id != space_id:
        raise HTTPException(status_code=404, detail="Startup not found in this space.")

    update_data = startup_update.model_dump(exclude_unset=True)
    
    if 'approved_member_slots' in update_data:
        startup.approved_member_slots = update_data['approved_member_slots']

    db.add(startup)
    await db.commit()
    await db.refresh(startup)
    return startup

async def update_startup_slots(
    db: AsyncSession, *, space_id: int, startup_id: int, slot_data: MemberSlotUpdate, current_user: models.User
) -> models.organization.Startup:
    await check_admin_space_permission(db, current_user=current_user, space_id=space_id)
    
    startup = await crud.crud_organization.get_startup(db, startup_id=startup_id)
    if not startup or startup.space_id != space_id:
        raise HTTPException(status_code=404, detail="Startup not found in this space.")

    update_data = {"member_slots_allocated": slot_data.member_slots_allocated}
    updated_startup = await crud.crud_organization.update_startup(
        db, db_obj=startup, obj_in=schemas.organization.StartupUpdate(**update_data)
    )

    startup_admin = next((member for member in startup.direct_members if member.role == UserRole.STARTUP_ADMIN), None)
    if startup_admin:
        await crud.crud_notification.create_notification(
            db=db,
            user_id=startup_admin.id,
            type=NotificationType.SLOT_ALLOCATION_UPDATED,
            message=f"Your allocated member slots have been updated.",
            link="/dashboard/startup-admin/profile/edit"
        )
    return updated_startup

async def get_space_tenants(
    db: AsyncSession, *, space_id: int, current_user: models.User, search: Optional[str] = None, sort_by: Optional[str] = None
) -> List[Union[models.User, models.organization.Startup]]:
    await check_admin_space_permission(db, current_user=current_user, space_id=space_id)
    tenants = await crud.crud_space.get_tenants_in_space(db, space_id=space_id, search=search, sort_by=sort_by)
    return tenants

async def list_space_workstations(
    db: AsyncSession, *, space_id: int, current_user: models.User, search: Optional[str] = None, sort_by: Optional[str] = None
) -> List[models.Workstation]:
    await check_admin_space_permission(db, current_user=current_user, space_id=space_id)
    workstations = await crud.crud_space.space.get_workstations_in_space(db, space_id=space_id, search=search)

    def natural_sort_key(s):
        return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', s.name)]

    if sort_by == 'alphabetic':
        workstations.sort(key=lambda w: w.name)
    else: # Default to natural sort
        workstations.sort(key=natural_sort_key)
        
    return workstations

async def list_users_in_space(
    db: AsyncSession, *, space_id: int, current_user: models.User, search: Optional[str] = None, sort_by: Optional[str] = None
) -> List[models.User]:
    space = await check_admin_space_permission(db, current_user=current_user, space_id=space_id)
    
    # Get users directly assigned to the space
    space_users = await crud.crud_user.get_users_by_space_id(db, space_id=space_id, search=search)
    
    # Get corporate admins from the company that owns the space
    company_admins = []
    if space.company_id:
        company_admins = await crud.crud_user.get_users_by_company_and_role(
            db, company_id=space.company_id, role=UserRole.CORP_ADMIN, search=search
        )
        
    # Combine lists and remove duplicates
    combined_users_dict = {user.id: user for user in space_users}
    for admin in company_admins:
        combined_users_dict[admin.id] = admin
        
    combined_users = list(combined_users_dict.values())

    # Sort the final list
    if sort_by == "name_desc":
        combined_users.sort(key=lambda u: u.full_name or "", reverse=True)
    else: # Default to name_asc
        combined_users.sort(key=lambda u: u.full_name or "")
        
    return combined_users

async def add_or_move_user_to_space(
    db: AsyncSession, *, space_id: int, add_user_request: schemas.space.AddUserToSpaceRequest, current_user: models.User
) -> models.User:
    space = await check_admin_space_permission(db, current_user=current_user, space_id=space_id)

    user_to_move = await crud.crud_user.get_user_by_id(db, user_id=add_user_request.user_id)
    if not user_to_move:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    # Allow adding users who are waitlisted OR active (but in another space)
    if user_to_move.status not in [UserStatus.WAITLISTED, UserStatus.PENDING_VERIFICATION, UserStatus.ACTIVE]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"User's current status ({user_to_move.status.value}) does not permit being added to a space.")

    # --- This is the new "Move" logic ---
    if user_to_move.status == UserStatus.ACTIVE and user_to_move.space_id is not None:
        # User is active and in another space, so we are moving them.
        if user_to_move.role == UserRole.FREELANCER:
            # Terminate old workstation assignment for the freelancer
            await crud.crud_space.terminate_workstation_assignments_for_user_ids(db, user_ids=[user_to_move.id])
        elif user_to_move.role == UserRole.STARTUP_ADMIN:
            # Move the entire startup
            startup_to_move = await crud.crud_organization.get_startup(db, startup_id=user_to_move.startup_id)
            if not startup_to_move:
                raise HTTPException(status_code=404, detail="Associated startup not found.")
            
            # Terminate assignments for all members of the startup
            member_ids = [member.id for member in startup_to_move.direct_members]
            await crud.crud_space.terminate_workstation_assignments_for_user_ids(db, user_ids=member_ids)
            
            # Update the startup's space
            startup_to_move.space_id = space.id
            db.add(startup_to_move)

    company_id = current_user.company_id if add_user_request.role == UserRole.CORP_EMPLOYEE else None

    # This function now also handles updating the space_id for the user
    updated_user = await crud.crud_space.add_user_to_space(
        db,
        user_to_add=user_to_move,
        space=space,
        role=add_user_request.role,
        company_id=company_id,
        startup_id=add_user_request.startup_id
    )

    await crud.crud_connection.create_accepted_connection(
        db, user_one_id=updated_user.id, user_two_id=current_user.id
    )
    
    await db.commit()
    await db.refresh(updated_user)
    return updated_user

async def delete_space_and_handle_tenants(db: AsyncSession, *, space_id: int, current_user: models.User):
    """
    Orchestrates the deletion of a space, including permission checks,
    tenant handling, and notifications.
    """
    # 1. Check permissions and get the space object
    space = await check_admin_space_permission(db, current_user=current_user, space_id=space_id)

    # 2. Enforce "last space" rule
    company_spaces = await crud.crud_space.get_by_company_id(db, company_id=current_user.company_id)
    if len(company_spaces) <= 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot delete the last space of your company. A company must have at least one space."
        )

    # 3. Get all tenants (freelancers and startups)
    tenants = await crud.crud_space.get_tenants_in_space(db, space_id=space_id)
    freelancers = [t for t in tenants if isinstance(t, models.User)]
    startups = [t for t in tenants if isinstance(t, models.organization.Startup)]

    # 4. Collect all users who will be affected
    user_ids_to_notify = [f.id for f in freelancers]
    for startup in startups:
        user_ids_to_notify.extend([member.id for member in startup.direct_members])

    # 5. Terminate all workstation assignments in the space
    await crud.crud_space.terminate_all_workstation_assignments_in_space(db, space_id=space.id)

    # 6. Update user statuses and remove space association
    if user_ids_to_notify:
        await crud.crud_user.bulk_update_user_status_and_space(
            db, user_ids=user_ids_to_notify, status=UserStatus.WAITLISTED, space_id=None
        )

    # 7. Update startup space association
    startup_ids_to_update = [s.id for s in startups]
    if startup_ids_to_update:
        await crud.crud_organization.bulk_update_startup_space(
            db, startup_ids=startup_ids_to_update, space_id=None
        )

    # 8. Send notifications to all affected users
    notification_message = f"The space '{space.name}' has been deleted. Your status has been updated to Waitlisted while you find a new space."
    for user_id in user_ids_to_notify:
        await crud.crud_notification.create_notification(
            db=db,
            user_id=user_id,
            type=NotificationType.REMOVED_FROM_SPACE,
            message=notification_message,
        )

    # 9. Delete the space itself
    await crud.crud_space.space.remove(db=db, id=space.id)
    # The CRUD remove method handles the commit

from app.crud.crud_booking import crud_booking

async def get_all_company_bookings(db: AsyncSession, *, company_id: int) -> List[models.WorkstationAssignment]:
    """
    Retrieves all bookings across all spaces for a given company.
    """
    bookings = await crud_booking.get_bookings_by_company_id(db, company_id=company_id)
    return bookings

async def get_all_company_invites(db: AsyncSession, *, company_id: int) -> List[models.Invitation]:
    """
    Retrieves all invites sent by any admin of this company.
    """
    invites = await crud.crud_invitation.get_by_company_id(db, company_id=company_id)
    return invites

async def get_company_spaces(db: AsyncSession, *, company_id: int) -> List[models.SpaceNode]:
    """
    Retrieves all spaces for a given company.
    """
    return await crud.crud_space.space.get_by_company_id(db, company_id=company_id)