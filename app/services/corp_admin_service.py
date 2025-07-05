from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional, Union
import re
from sqlalchemy.orm import selectinload

from app import crud, models, schemas
from app.models.enums import UserRole, UserStatus, NotificationType, InterestStatus
from app.schemas.admin import StartupUpdateAdmin, MemberSlotUpdate

async def approve_interest(
    db: AsyncSession, *, interest_id: int, space_id: int, current_user: models.User
) -> None:
    """
    Approves an interest request, moving the user or startup into the specified space.
    """
    # First, verify the admin has permission for this specific space
    await check_admin_space_permission(db=db, space_id=space_id, current_user=current_user)

    interest = await db.get(
        models.Interest,
        interest_id,
        options=[selectinload(models.Interest.user), selectinload(models.Interest.space)],
    )
    if not interest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Interest not found"
        )
    
    if interest.space_id != space_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Interest does not belong to this space."
        )

    user_to_add = interest.user
    if not user_to_add:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User associated with interest not found",
        )

    add_request = schemas.admin.AddUserToSpaceRequest(user_id=user_to_add.id)

    # Use the centralized function to handle adding/moving the user
    await add_or_move_user_to_space(db=db, space_id=space_id, add_user_request=add_request, current_user=current_user)

    # Update interest status
    interest.status = models.InterestStatus.ACCEPTED
    db.add(interest)

    # Create a notification for the user
    await crud.crud_notification.create_notification(
        db,
        user_id=user_to_add.id,
        type=models.enums.NotificationType.INTEREST_ACCEPTED,
        message=f"Your interest in the space '{interest.space.name}' has been accepted!",
        reference=f"space:{interest.space_id}",
        link=f"/spaces/{interest.space_id}/profile"
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
    db: AsyncSession, *, search: Optional[str], type: Optional[str], sort_by: Optional[str], skip: int, limit: int, current_user: models.User
) -> List[Union[schemas.admin.WaitlistedUser, schemas.admin.WaitlistedStartup]]:
    # Get all spaces for the admin's company to find relevant interests
    company_spaces = await crud.crud_space.get_by_company_id(db, company_id=current_user.company_id)
    space_ids = [space.id for space in company_spaces]
    
    interest_map = {}
    if space_ids:
        interests = await crud.crud_interest.interest.get_interests_for_spaces(db, space_ids=space_ids)
        for interest in interests:
            if interest.status == InterestStatus.PENDING:
                interest_map[interest.user_id] = interest.id

    results = []
    # Fetch freelancers
    if type == 'freelancer' or not type:
        freelancers = await crud.crud_user.get_users(
            db, skip=skip, limit=limit, user_type=UserRole.FREELANCER,
            status=UserStatus.WAITLISTED, search_term=search
        )
        for user in freelancers:
            waitlisted_user = schemas.admin.WaitlistedUser.model_validate(user)
            if user.id in interest_map:
                waitlisted_user.expressed_interest = True
                waitlisted_user.interest_id = interest_map[user.id]
            results.append(waitlisted_user)

    # Fetch startups
    if type == 'startup' or not type:
        startups = await crud.crud_organization.get_startups_by_status(
            db, status=UserStatus.WAITLISTED, skip=skip, limit=limit, search_term=search
        )
        for startup in startups:
            # The "interest" is expressed by the startup admin
            startup_admin = next((member for member in startup.direct_members if member.role == UserRole.STARTUP_ADMIN), None)
            waitlisted_startup = schemas.admin.WaitlistedStartup.model_validate(startup)
            if startup_admin and startup_admin.id in interest_map:
                waitlisted_startup.expressed_interest = True
                waitlisted_startup.interest_id = interest_map[startup_admin.id]
            results.append(waitlisted_startup)

    # Sort results
    if sort_by == "name_desc":
        results.sort(key=lambda x: x.full_name if hasattr(x, 'full_name') else x.name, reverse=True)
    elif sort_by == "name_asc":
        results.sort(key=lambda x: x.full_name if hasattr(x, 'full_name') else x.name)
    else: # Default sort: expressed interest first
        results.sort(key=lambda x: x.expressed_interest, reverse=True)
    
    return results[:limit]

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