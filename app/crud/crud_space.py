import datetime
from typing import Optional, List, Tuple

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.crud.crud_notification import create_notification
from app.crud import crud_user, crud_connection
from app.models.space import SpaceNode, Workstation, WorkstationAssignment
from app.models.user import User
from app.models.enums import UserRole, UserStatus, WorkstationStatus, NotificationType
from app.schemas.space import WorkstationCreate, WorkstationUpdate
from app.schemas.admin import SpaceCreate, SpaceUpdate
from app import models

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# CRUD for SpaceNode
async def create_space(db: AsyncSession, *, obj_in: SpaceCreate) -> SpaceNode:
    logger.info(f"Creating new space: {obj_in.name}")
    db_obj = SpaceNode(
        name=obj_in.name,
        address=obj_in.address,
        corporate_admin_id=obj_in.corporate_admin_id,
        company_id=obj_in.company_id,
        total_workstations=obj_in.total_workstations
    )
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    
    admin_user = await crud_user.get_user_by_id(db, user_id=obj_in.corporate_admin_id)
    if admin_user and admin_user.space_id is None:
        admin_user.space_id = db_obj.id
        db.add(admin_user)
        await db.commit()
        await db.refresh(admin_user)
        
    logger.info(f"Space '{db_obj.name}' created with ID: {db_obj.id}")
    return db_obj

async def get_space_by_id(db: AsyncSession, space_id: int) -> Optional[SpaceNode]:
    """Fetch a single space by its ID with its admin and company relationships loaded."""
    result = await db.execute(
        select(SpaceNode)
        .options(
            selectinload(SpaceNode.corporate_admin),
            selectinload(SpaceNode.company)
        )
        .filter(SpaceNode.id == space_id)
    )
    return result.scalars().first()

async def get_spaces(db: AsyncSession, skip: int = 0, limit: int = 100) -> List[SpaceNode]:
    logger.debug(f"Fetching list of spaces with skip={skip}, limit={limit}")
    stmt = (
        select(SpaceNode)
        .options(selectinload(SpaceNode.company))
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return result.scalars().all()

async def get_space_by_corporate_admin_id(db: AsyncSession, admin_id: int) -> Optional[SpaceNode]:
    logger.debug(f"Fetching space managed by admin ID: {admin_id}")
    result = await db.execute(select(SpaceNode).filter(SpaceNode.corporate_admin_id == admin_id))
    return result.scalar_one_or_none()

async def update_space(
    db: AsyncSession, *, space_obj: SpaceNode, obj_in: SpaceUpdate
) -> SpaceNode:
    logger.info(f"Updating space ID: {space_obj.id}")
    update_data = obj_in.model_dump(exclude_unset=True)

    changed_fields = False
    for field, value in update_data.items():
        if hasattr(space_obj, field) and getattr(space_obj, field) != value:
            setattr(space_obj, field, value)
            changed_fields = True
            logger.debug(f"Space {space_obj.id}: Set {field} to {value}")

    if not changed_fields:
        logger.info(f"No actual changes for space {space_obj.id}. Skipping commit.")
        return space_obj

    db.add(space_obj)
    try:
        await db.commit()
        await db.refresh(space_obj)
        logger.info(f"Space {space_obj.id} updated successfully.")
        return space_obj
    except Exception as e:
        await db.rollback()
        logger.error(f"Database error updating space {space_obj.id}: {e}", exc_info=True)
        raise

async def delete_space(db: AsyncSession, *, space_id: int) -> bool:
    """Deletes a space. Returns True if deleted, False otherwise."""
    logger.info(f"Attempting to delete space ID: {space_id}")
    space = await get_space_by_id(db, space_id=space_id)
    if not space:
        logger.warning(f"Delete failed: Space with ID {space_id} not found.")
        return False
    
    try:
        await db.delete(space)
        await db.commit()
        logger.info(f"Space ID: {space_id} deleted successfully.")
        return True
    except Exception as e: 
        await db.rollback()
        logger.error(f"Database error deleting space {space_id}: {e}", exc_info=True)
        return False

async def assign_admin_to_space(
    db: AsyncSession, *, space_obj: SpaceNode, new_admin_id: int
) -> Optional[SpaceNode]:
    """Assigns a new corporate admin to a space."""
    logger.info(f"Attempting to assign new admin ID: {new_admin_id} to space ID: {space_obj.id}")

    new_admin = await crud_user.get_user_by_id(db, user_id=new_admin_id)
    if not new_admin:
        logger.warning(f"Assign admin failed: User with ID {new_admin_id} not found.")
        raise ValueError(f"User with ID {new_admin_id} not found to be assigned as admin.")

    space_obj.corporate_admin_id = new_admin_id
    db.add(space_obj)
    try:
        await db.commit()
        await db.refresh(space_obj)
        logger.info(f"Admin ID: {new_admin_id} successfully assigned to space ID: {space_obj.id}.")
        return space_obj
    except Exception as e:
        await db.rollback()
        logger.error(f"Database error assigning admin to space {space_obj.id}: {e}", exc_info=True)
        raise

# New CRUD operations for Workstations
async def create_workstation(db: AsyncSession, *, workstation_in: WorkstationCreate, space_id: int) -> Optional[Workstation]:
    logger.info(f"Creating workstation '{workstation_in.name}' in space ID: {space_id}")
    space = await get_space_by_id(db, space_id=space_id)
    if not space:
        logger.warning(f"Create workstation failed: Space with ID {space_id} not found.")
        return None

    db_workstation = Workstation(
        name=workstation_in.name,
        status=workstation_in.status,
        space_id=space_id
    )
    db.add(db_workstation)
    
    space.total_workstations = (space.total_workstations or 0) + 1
    db.add(space)
    
    try:
        await db.commit()
        await db.refresh(db_workstation)
        await db.refresh(space)
        logger.info(f"Workstation ID: {db_workstation.id} ('{db_workstation.name}') created successfully in space ID: {space_id}.")
        return db_workstation
    except Exception as e:
        await db.rollback()
        logger.error(f"Database error creating workstation '{workstation_in.name}' in space {space_id}: {e}", exc_info=True)
        raise

async def get_workstation_by_id_and_space_id(db: AsyncSession, *, workstation_id: int, space_id: int) -> Optional[Workstation]:
    from sqlalchemy.orm import selectinload
    logger.debug(f"Fetching workstation ID: {workstation_id} from space ID: {space_id}")
    result = await db.execute(
        select(Workstation)
        .options(
            selectinload(Workstation.active_assignment).selectinload(WorkstationAssignment.user)
        )
        .where(Workstation.id == workstation_id, Workstation.space_id == space_id)
    )
    workstation = result.scalars().first()
    if not workstation:
        logger.warning(f"Workstation ID {workstation_id} not found in space ID {space_id}.")
    return workstation

async def update_workstation(db: AsyncSession, *, workstation_obj: Workstation, workstation_in: WorkstationUpdate) -> Workstation:
    from sqlalchemy.orm import selectinload
    logger.info(f"Updating workstation ID: {workstation_obj.id} ('{workstation_obj.name}')")
    update_data = workstation_in.model_dump(exclude_unset=True)
    
    changed_fields = False
    previous_status = workstation_obj.status
    previous_name = workstation_obj.name

    for field, value in update_data.items():
        if hasattr(workstation_obj, field) and getattr(workstation_obj, field) != value:
            setattr(workstation_obj, field, value)
            changed_fields = True
            logger.debug(f"Workstation {workstation_obj.id}: Set {field} to {value}")

    if not changed_fields:
        logger.info(f"No actual changes for workstation {workstation_obj.id}. Skipping commit.")
        return workstation_obj

    db.add(workstation_obj)
    try:
        await db.commit()
        await db.refresh(workstation_obj, attribute_names=['active_assignment'])

        if workstation_obj.active_assignment and workstation_obj.active_assignment.user_id:
            assigned_user_id = workstation_obj.active_assignment.user_id
            
            if workstation_obj.status != previous_status:
                await create_notification(
                    db=db,
                    user_id=assigned_user_id,
                    type=NotificationType.WORKSTATION_STATUS_UPDATED,
                    message=f"The status of your workstation '{workstation_obj.name}' has been updated to {workstation_obj.status.value}.",
                    reference=f"workstation:{workstation_obj.id}",
                    link=f"/dashboard"
                )
            
            if workstation_obj.name != previous_name:
                await create_notification(
                    db=db,
                    user_id=assigned_user_id,
                    type=NotificationType.WORKSTATION_DETAILS_CHANGED,
                    message=f"The name of your workstation has been changed from '{previous_name}' to '{workstation_obj.name}'.",
                    reference=f"workstation:{workstation_obj.id}",
                    link=f"/dashboard"
                )

        await db.commit()
        await db.refresh(workstation_obj)
        logger.info(f"Workstation {workstation_obj.id} updated successfully.")
        return workstation_obj
    except Exception as e:
        await db.rollback()
        logger.error(f"Database error updating workstation {workstation_obj.id}: {e}", exc_info=True)
        raise

async def get_active_assignment_for_workstation(db: AsyncSession, *, workstation_id: int) -> Optional[WorkstationAssignment]:
    stmt = select(WorkstationAssignment).where(
        WorkstationAssignment.workstation_id == workstation_id,
        WorkstationAssignment.end_date.is_(None)
    )
    result = await db.execute(stmt)
    return result.scalars().first()

async def delete_workstation(db: AsyncSession, *, workstation_id: int, space_id: int) -> bool:
    """
    Deletes a workstation by its ID, ensuring it belongs to the correct space.
    If the workstation is occupied, it will be unassigned before deletion.
    """
    workstation_to_delete = await get_workstation_by_id_and_space_id(
        db, workstation_id=workstation_id, space_id=space_id
    )
    if not workstation_to_delete:
        return False

    # If workstation is occupied, find and remove the active assignment first
    if workstation_to_delete.status == WorkstationStatus.OCCUPIED:
        active_assignment = await get_active_assignment_for_workstation(db, workstation_id=workstation_id)
        if active_assignment:
            await db.delete(active_assignment)
            # The user's `current_workstation` info will become stale until their auth token is refreshed,
            # which is an acceptable trade-off. We can also emit a socket event here if needed.
    
    await db.delete(workstation_to_delete)
    await db.commit()
    return True

async def assign_user_to_workstation(
    db: AsyncSession,
    *, 
    user_id: int, 
    workstation_id: int, 
    space_id: int,
    assigning_admin_id: Optional[int] = None
) -> Optional[Tuple[WorkstationAssignment, str]]:
    logger.info(f"Attempting to assign user ID: {user_id} to workstation ID: {workstation_id} in space ID: {space_id}")

    user = await crud_user.get_user_by_id(db, user_id=user_id)
    if not user:
        logger.warning(f"Assign workstation failed: User ID {user_id} not found.")
        raise ValueError(f"User ID {user_id} not found.")

    workstation = await get_workstation_by_id_and_space_id(db, workstation_id=workstation_id, space_id=space_id)
    if not workstation:
        logger.warning(f"Assign workstation failed: Workstation ID {workstation_id} not found in space ID {space_id}.")
        raise ValueError(f"Workstation ID {workstation_id} not found in space ID {space_id}.")

    current_workstation_name = workstation.name if workstation else "Unknown"

    if workstation.status == WorkstationStatus.OCCUPIED or workstation.active_assignment:
        if workstation.active_assignment and workstation.active_assignment.user_id == user_id:
            logger.info(f"User {user_id} is already actively assigned to workstation {workstation_id} ('{current_workstation_name}'). No action needed.")
            return workstation.active_assignment, current_workstation_name
        logger.warning(f"Assign workstation failed: Workstation ID {workstation_id} ('{current_workstation_name}') is already {workstation.status.value}.")
        raise ValueError(f"Workstation ID {workstation_id} ('{current_workstation_name}') is already occupied or has an active assignment.")

    existing_user_assignments_stmt = select(WorkstationAssignment).where(
        WorkstationAssignment.user_id == user_id,
        WorkstationAssignment.space_id == space_id,
        WorkstationAssignment.end_date.is_(None)
    )
    existing_user_assignments_result = await db.execute(existing_user_assignments_stmt)
    for old_assignment in existing_user_assignments_result.scalars().all():
        if old_assignment.workstation_id != workstation_id:
            logger.info(f"Ending previous assignment ID {old_assignment.id} for user {user_id} at workstation {old_assignment.workstation_id}")
            old_assignment.end_date = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
            db.add(old_assignment)
            prev_workstation = await get_workstation_by_id_and_space_id(db, workstation_id=old_assignment.workstation_id, space_id=space_id)
            if prev_workstation:
                prev_workstation.status = WorkstationStatus.AVAILABLE
                db.add(prev_workstation)

    new_assignment = WorkstationAssignment(
        user_id=user_id,
        workstation_id=workstation_id,
        space_id=space_id,
        start_date=datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    )
    db.add(new_assignment)
    workstation.status = WorkstationStatus.OCCUPIED
    db.add(workstation)

    try:
        await db.commit()
        await db.refresh(new_assignment)
        await db.refresh(workstation)
        
        workstation_name_for_notification = workstation.name
        space_name_for_notification = "the space"
        if workstation.space and workstation.space.name:
             space_name_for_notification = workstation.space.name
        elif workstation.space:
             space_name_for_notification = f"space ID {workstation.space.id}"

        logger.info(f"User ID: {user_id} successfully assigned to workstation ID: {workstation_id} ('{workstation_name_for_notification}'). Assignment ID: {new_assignment.id}")
        
        await create_notification(
            db=db,
            user_id=user_id,
            type=NotificationType.WORKSTATION_ASSIGNED,
            message=f"You have been assigned to workstation '{workstation_name_for_notification}' in {space_name_for_notification}.",
            reference=f"workstation_assignment:{new_assignment.id}",
            link=f"/dashboard"
        )
        await db.commit()

        return new_assignment, workstation_name_for_notification
    except Exception as e:
        await db.rollback()
        logger.error(f"Database error assigning user {user_id} to workstation {workstation_id}: {e}", exc_info=True)
        raise

async def unassign_user_from_workstation(
    db: AsyncSession, 
    *, 
    user_id: int, 
    workstation_id: int, 
    space_id: int, 
    unassigning_admin_id: Optional[int] = None
) -> bool:
    logger.info(f"Attempting to unassign user ID: {user_id} from workstation ID: {workstation_id} in space ID: {space_id}")

    active_assignment_stmt = select(WorkstationAssignment).where(
        WorkstationAssignment.user_id == user_id,
        WorkstationAssignment.workstation_id == workstation_id,
        WorkstationAssignment.space_id == space_id,
        WorkstationAssignment.end_date.is_(None)
    )
    active_assignment_result = await db.execute(active_assignment_stmt)
    assignment_to_end = active_assignment_result.scalars().first()

    if not assignment_to_end:
        logger.warning(f"Unassign workstation failed: No active assignment found for user ID {user_id} at workstation ID {workstation_id} in space {space_id}.")
        return False 

    assignment_to_end.end_date = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) 
    db.add(assignment_to_end)

    workstation = await get_workstation_by_id_and_space_id(db, workstation_id=workstation_id, space_id=space_id)
    workstation_name_for_notification = "your workstation"
    space_name_for_notification = "the space"
    if workstation:
        workstation.status = WorkstationStatus.AVAILABLE
        db.add(workstation)
        workstation_name_for_notification = workstation.name
        if workstation.space and workstation.space.name:
            space_name_for_notification = workstation.space.name
        elif workstation.space:
            space_name_for_notification = f"space ID {workstation.space.id}"
    else: 
        logger.error(f"Critical: Workstation ID {workstation_id} not found during unassignment for user {user_id} despite active assignment.")

    try:
        await db.commit()
        await db.refresh(assignment_to_end)
        if workstation: await db.refresh(workstation)
        logger.info(f"User ID: {user_id} successfully unassigned from workstation ID: {workstation_id}. Assignment ID: {assignment_to_end.id} ended.")

        await create_notification(
            db=db,
            user_id=user_id,
            type=NotificationType.WORKSTATION_UNASSIGNED,
            message=f"You have been unassigned from workstation '{workstation_name_for_notification}' in {space_name_for_notification}.",
            reference=f"workstation_assignment:{assignment_to_end.id}",
            link=f"/dashboard"
        )
        await db.commit() 
        return True
    except Exception as e:
        await db.rollback()
        logger.error(f"Database error unassigning user {user_id} from workstation {workstation_id}: {e}", exc_info=True)
        raise 

async def unassign_user_from_all_workstations_in_space(db: AsyncSession, *, user_id: int, space_id: int) -> bool:
    """
    Finds and ends all active workstation assignments for a given user within a specific space.
    This is useful when a user is removed from a space entirely.
    """
    logger.info(f"Unassigning user ID: {user_id} from all workstations in space ID: {space_id}")
    
    active_assignments_stmt = select(WorkstationAssignment).where(
        WorkstationAssignment.user_id == user_id,
        WorkstationAssignment.space_id == space_id,
        WorkstationAssignment.end_date.is_(None)
    )
    active_assignments_result = await db.execute(active_assignments_stmt)
    assignments_to_end = active_assignments_result.scalars().all()

    if not assignments_to_end:
        logger.info(f"No active assignments found for user {user_id} in space {space_id}. No action needed.")
        return True

    for assignment in assignments_to_end:
        assignment.end_date = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        db.add(assignment)
        
        workstation = await get_workstation_by_id_and_space_id(db, workstation_id=assignment.workstation_id, space_id=space_id)
        if workstation:
            workstation.status = WorkstationStatus.AVAILABLE
            db.add(workstation)
            logger.info(f"Ended assignment {assignment.id} for user {user_id} at workstation {workstation.id}. Set workstation status to AVAILABLE.")

    try:
        await db.commit()
        logger.info(f"Successfully unassigned user {user_id} from all workstations in space {space_id}.")
        return True
    except Exception as e:
        await db.rollback()
        logger.error(f"Database error during bulk unassignment for user {user_id} in space {space_id}: {e}", exc_info=True)
        raise 

async def remove_user_from_space(db: AsyncSession, *, user_to_remove: "User", removing_admin: "User") -> "User":
    from sqlalchemy.orm import selectinload
    """
    Removes a user from a space managed by a Corporate Admin.
    """
    managed_space = await get_space_by_corporate_admin_id(db, admin_id=removing_admin.id)
    if not managed_space:
        raise ValueError("Admin does not manage a space.")

    if user_to_remove.space_id != managed_space.id:
        raise ValueError("User is not in the admin's managed space.")

    if removing_admin.id == user_to_remove.id:
        raise ValueError("Admins cannot remove themselves from their own space.")

    user_id = user_to_remove.id
    space_name = managed_space.name
    await unassign_user_from_all_workstations_in_space(db=db, user_id=user_id, space_id=managed_space.id)

    user_to_remove.space_id = None
    user_to_remove.status = UserStatus.WAITLISTED
    db.add(user_to_remove)

    await create_notification(
        db=db,
        user_id=user_id,
        type=NotificationType.REMOVED_FROM_SPACE,
        message=f"You have been removed from the space '{space_name}' and your status has been updated to waitlisted.",
        reference=f"space_id:{managed_space.id}",
        link="/dashboard"
    )

    await db.commit()
    
    refreshed_user = await crud_user.get_user_by_id(db, user_id=user_id, options=[
        selectinload(User.profile),
        selectinload(User.space),
        selectinload(User.managed_space),
        selectinload(User.company),
        selectinload(User.startup),
    ])

    if refreshed_user is None:
        logger.error(f"Failed to re-fetch user {user_id} after removing from space.")
        raise Exception("Could not retrieve user details after update.")

    return refreshed_user

async def add_user_to_space(db: AsyncSession, *, user_to_add: User, space: SpaceNode, role: UserRole, company_id: Optional[int] = None, startup_id: Optional[int] = None) -> User:
    from sqlalchemy.orm import selectinload
    """
    Adds a user to a space with a specific role.
    """
    occupied_workstations = await get_occupied_workstation_count(db, space_id=space.id)
    if space.total_workstations is not None and occupied_workstations >= space.total_workstations:
        raise ValueError("No available workstations in the space.")

    user_to_add.space_id = space.id
    user_to_add.status = UserStatus.ACTIVE
    user_to_add.role = role
    user_to_add.is_active = True

    if role == UserRole.CORP_EMPLOYEE and company_id:
        user_to_add.company_id = company_id
        user_to_add.startup_id = None
    elif role in [UserRole.STARTUP_ADMIN, UserRole.STARTUP_MEMBER] and startup_id:
        user_to_add.startup_id = startup_id
        user_to_add.company_id = None
    elif role == UserRole.FREELANCER:
        user_to_add.company_id = None
        user_to_add.startup_id = None

    db.add(user_to_add)
    await db.commit()

    refreshed_user = await crud_user.get_user_by_id(db, user_id=user_to_add.id, options=[
        selectinload(User.profile),
        selectinload(User.space),
        selectinload(User.managed_space),
        selectinload(User.company),
        selectinload(User.startup),
        selectinload(User.assignments).selectinload(models.WorkstationAssignment.workstation)
    ])

    if not refreshed_user:
        raise Exception("Could not retrieve user details after adding to space.")
    
    # Automatically create a connection with the space's corporate admin
    if space.corporate_admin_id and space.corporate_admin_id != refreshed_user.id:
        try:
            await crud_connection.create_accepted_connection(
                db=db,
                user_one_id=refreshed_user.id,
                user_two_id=space.corporate_admin_id
            )
            logger.info(f"Automatically created connection between user {refreshed_user.id} and corporate admin {space.corporate_admin_id}")
        except Exception as e:
            logger.error(f"Failed to create automatic connection for user {refreshed_user.id} with admin {space.corporate_admin_id}: {e}")
            # Do not re-raise, as adding the user to the space is the primary goal.

    await create_notification(
        db=db,
        user_id=refreshed_user.id,
        type=NotificationType.ADDED_TO_SPACE,
        message=f"You have been added to the space '{space.name}'. Welcome!",
        reference=f"space_id:{space.id}",
        link="/dashboard"
    )

    return refreshed_user

async def get_occupied_workstation_count(db: AsyncSession, space_id: int) -> int:
    """Gets the count of occupied workstations in a space."""
    stmt = select(func.count(WorkstationAssignment.id)).where(
        WorkstationAssignment.space_id == space_id,
        WorkstationAssignment.end_date.is_(None)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none() or 0 

async def get_space_admin(db: AsyncSession, space_id: int) -> Optional[User]:
    """Gets the corporate admin for a given space."""
    space = await get_space_by_id(db, space_id=space_id)
    if not space or not space.corporate_admin_id:
        return None
    
    admin = await crud_user.get_user_by_id(db, user_id=space.corporate_admin_id)
    return admin

async def get_managed_space(
    db: AsyncSession, current_user: models.User
) -> Optional[models.SpaceNode]:
    """
    Helper function to get the space managed by the current Corp Admin.
    Returns None if no space is managed.
    """
    stmt = select(models.SpaceNode).where(models.SpaceNode.corporate_admin_id == current_user.id)
    result = await db.execute(stmt)
    managed_space = result.scalar_one_or_none()
    return managed_space 