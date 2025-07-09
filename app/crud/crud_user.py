from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import Select, update, and_, or_
from sqlalchemy.orm import Load, selectinload, joinedload, subqueryload
import logging
from sqlalchemy.sql import func

from app.models.user import User
from app.models.space import WorkstationAssignment, SpaceNode
from app.models.enums import UserRole, UserStatus
from app.schemas.user import UserCreate, UserUpdateInternal
from app.security import get_password_hash, verify_password
from typing import List, Optional, Sequence, Any, Dict, Union
from fastapi import HTTPException
from app.core.config import settings
from app.models.organization import Company, Startup
from app.schemas.organization import CompanyCreate, CompanyUpdate, StartupCreate, StartupUpdate
from app import models
from app.models.interest import Interest

logger = logging.getLogger(__name__)

async def get_waitlisted_freelancers(
    db: AsyncSession,
    *,
    search_term: Optional[str] = None,
    space_id: Optional[int] = None,
    filter_by_interest: bool = False,
) -> List[Dict[str, Any]]:
    """
    Fetches waitlisted freelancers with optional filtering and annotates them
    with interest information for a specific space.
    """
    # Base join condition for the outerjoin
    join_conditions = [
        Interest.user_id == User.id,
        Interest.status == "PENDING",
    ]
    if space_id is not None:
        join_conditions.append(Interest.space_id == space_id)

    # Base statement for waitlisted freelancers
    stmt = (
        select(
            User,
            Interest.id.label("interest_id"),
            (Interest.id != None).label("expressed_interest"),
        )
        .outerjoin(
            Interest,
            and_(*join_conditions),
        )
        .where(User.role == UserRole.FREELANCER, User.status == UserStatus.WAITLISTED)
    )

    if filter_by_interest:
        stmt = stmt.where(Interest.id.isnot(None))

    if search_term:
        stmt = stmt.where(
            or_(
                User.full_name.ilike(f"%{search_term}%"),
                User.email.ilike(f"%{search_term}%"),
            )
        )

    result = await db.execute(stmt)
    
    # Process results into a list of dictionaries to preserve annotations
    freelancers = []
    for row in result.all():
        user_data = row.User.__dict__
        user_data["expressed_interest"] = row.expressed_interest
        user_data["interest_id"] = row.interest_id
        freelancers.append(user_data)
        
    return freelancers

async def get_user_by_id(
    db: AsyncSession, 
    *, 
    user_id: int, 
    options: Optional[Sequence[Load]] = None
) -> User | None:
    logger.debug(f"Fetching user by ID: {user_id} with options: {options}")
    try:
        stmt = select(User).filter(User.id == user_id)
        if options:
            stmt = stmt.options(*options)
        result = await db.execute(stmt)
        user = result.scalars().first()
        if not user:
            logger.warning(f"User with ID {user_id} not found.")
        return user
    except SQLAlchemyError as e:
        logger.error(f"Database error fetching user by ID {user_id}: {e}", exc_info=True)
        return None

async def get_user_by_email(db: AsyncSession, *, email: str) -> User | None:
    logger.debug(f"Fetching user by email: {email}")
    try:
        result = await db.execute(select(User).filter(User.email == email))
        user = result.scalars().first()
        if not user:
            logger.warning(f"User with email {email} not found.")
        return user
    except SQLAlchemyError as e:
        logger.error(f"Database error fetching user by email {email}: {e}", exc_info=True)
        return None

async def create_user(db: AsyncSession, *, obj_in: UserCreate) -> User:
    user_data = obj_in.model_dump()
    # Hash the password
    hashed_password = get_password_hash(user_data.pop("password"))
    user_data["hashed_password"] = hashed_password

    # Create the user object
    db_user = User(
        email=user_data.get("email"),
        hashed_password=user_data.get("hashed_password"),
        role=user_data.get("role"),
        full_name=user_data.get("full_name"),
        company_id=user_data.get("company_id")
    )

    # Add to session and commit
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)
    return db_user

async def update_user_internal(db: AsyncSession, *, db_obj: User, obj_in: UserUpdateInternal) -> User:
    db_obj = await db.merge(db_obj)
    update_data = obj_in.model_dump(exclude_unset=True)
    logger.info(f"Internally updating user {db_obj.id}. Update data: {update_data}")
    for field, value in update_data.items():
        if hasattr(db_obj, field):
            setattr(db_obj, field, value)
    db.add(db_obj)
    try:
        await db.commit()
        await db.refresh(db_obj)
        logger.info(f"User {db_obj.id} internal update successful.")
        return db_obj
    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(f"Database error during internal update for user {db_obj.id}: {e}", exc_info=True)
        raise

async def add_user_to_space(db: AsyncSession, *, user_id: int, space_id: int) -> User:
    """
    Activates a user and assigns them to a space.
    """
    user = await get_user_by_id(db, user_id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    user.space_id = space_id
    user.status = UserStatus.ACTIVE
    db.add(user)
    # The commit will be handled by the calling service function.
    return user

async def update_user_password(db: AsyncSession, *, user: User, new_password: str) -> User:
    logger.info(f"Updating password for user {user.id}")
    user.hashed_password = get_password_hash(new_password)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    logger.info(f"Password updated successfully for user {user.id}")
    return user

async def get_users_by_status(db: AsyncSession, status: UserStatus) -> List[User]:
    logger.debug(f"Fetching users with status: {status.value}")
    try:
        result = await db.execute(select(User).filter(User.status == status))
        return result.scalars().all()
    except SQLAlchemyError as e:
        logger.error(f"Database error fetching users by status {status.value}: {e}", exc_info=True)
        return []

async def get_users_by_role_and_startup(db: AsyncSession, *, role: UserRole, startup_id: int) -> List[User]:
    logger.debug(f"Fetching users with role: {role.value} for startup ID: {startup_id}")
    try:
        stmt = select(User).where(User.role == role, User.startup_id == startup_id)
        result = await db.execute(stmt)
        return result.scalars().all()
    except SQLAlchemyError as e:
        logger.error(f"Database error fetching users by role {role.value} and startup {startup_id}: {e}", exc_info=True)
        return []

async def get_users_by_role_and_space_id(db: AsyncSession, *, role: UserRole, space_id: int) -> List[User]:
    logger.debug(f"Fetching users with role: {role.value} for space ID: {space_id}")
    try:
        stmt = select(User).where(User.role == role, User.space_id == space_id)
        result = await db.execute(stmt)
        return result.scalars().all()
    except SQLAlchemyError as e:
        logger.error(f"Database error fetching users by role {role.value} and space {space_id}: {e}", exc_info=True)
        return []

async def get_user_by_email_and_startup(db: AsyncSession, *, email: str, startup_id: int) -> Optional[User]:
    logger.debug(f"Fetching user by email: {email} for startup ID: {startup_id}")
    try:
        stmt = select(User).where(User.email == email, User.startup_id == startup_id)
        result = await db.execute(stmt)
        user = result.scalars().first()
        if not user:
            logger.warning(f"User with email {email} and startup ID {startup_id} not found.")
        return user
    except SQLAlchemyError as e:
        logger.error(f"Database error fetching user by email {email} for startup {startup_id}: {e}", exc_info=True)
        return None

async def activate_corporate_user(db: AsyncSession, *, user_id: int, space_id: Optional[int] = None) -> Optional[User]:
    logger.info(f"Attempting to activate corporate user ID: {user_id} for space ID: {space_id}")
    load_options = [
        selectinload(User.profile),
        selectinload(User.managed_space),
        selectinload(User.space)
    ]
    user = await get_user_by_id(db, user_id=user_id, options=load_options)
    if not user:
        logger.warning(f"Corporate activation failed: User ID {user_id} not found.")
        return None
    if user.status != UserStatus.PENDING_VERIFICATION:
        logger.warning(f"Corporate activation failed: User ID {user_id} has status {user.status.value}, not PENDING_VERIFICATION.")
        return None
    update_data = {
        "status": UserStatus.ACTIVE,
        "role": UserRole.CORP_ADMIN,
        "is_active": True,
        "space_id": space_id
    }
    updated_user = await update_user_internal(db, db_obj=user, obj_in=UserUpdateInternal(**update_data))
    if updated_user:
        logger.info(f"Corporate user ID: {user_id} activated successfully. New role: {updated_user.role.value}, status: {updated_user.status.value}")
    return updated_user

async def assign_user_to_space(db: AsyncSession, *, user_id: int, space_id: Optional[int]) -> Optional[User]:
    logger.info(f"Assigning user ID: {user_id} to space ID: {space_id}")
    # Import locally to avoid circular dependency
    from app.crud import crud_space
    user = await get_user_by_id(db, user_id=user_id)
    if not user:
        logger.warning(f"Assign to space failed: User ID {user_id} not found.")
        return None
    if space_id is not None:
        space = await crud_space.get_space_by_id(db, space_id=space_id)
        if not space:
            logger.error(f"Assign to space failed: Space with ID {space_id} not found for user {user_id}.")
            raise ValueError(f"Space with ID {space_id} not found.") 
    user.space_id = space_id
    db.add(user)
    try:
        await db.commit()
        await db.refresh(user)
        logger.info(f"User ID: {user_id} successfully assigned to space ID: {space_id}.")
        return user
    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(f"Database error assigning user {user_id} to space {space_id}: {e}", exc_info=True)
        raise

async def activate_user_for_startup_invitation(db: AsyncSession, *, user_to_activate: User) -> Optional[User]:
    logger.info(f"Activating user ID: {user_to_activate.id} via startup invitation.")
    if user_to_activate:
        update_data = UserUpdateInternal(
            is_active=True,
            status=UserStatus.ACTIVE
        )
        updated_user = await update_user_internal(db, db_obj=user_to_activate, obj_in=update_data)
        if updated_user:
            logger.info(f"User {updated_user.id} activated via startup invitation. Status: {updated_user.status.value}, Active: {updated_user.is_active}")
        return updated_user
    logger.warning("activate_user_for_startup_invitation called with no user.")
    return None

async def get_user_details_for_profile(db: AsyncSession, user_id: int) -> Optional[User]:
    logger.debug(f"Fetching full user details for profile page for user ID: {user_id}")
    stmt = (
        select(User)
        .where(User.id == user_id)
        .options(
            selectinload(User.profile),
            selectinload(User.company),
            selectinload(User.startup).selectinload(Startup.direct_members),
            selectinload(User.space),
            selectinload(User.assignments).selectinload(WorkstationAssignment.workstation)
        )
    )
    try:
        result = await db.execute(stmt)
        user = result.scalars().first()
        if not user:
            logger.warning(f"User details for profile not found for user ID: {user_id}.")
        return user
    except SQLAlchemyError as e:
        logger.error(f"Database error fetching user details for profile {user_id}: {e}", exc_info=True)
        return None

async def get_users_by_startup_and_space(
    db: AsyncSession, *, startup_id: int, space_id: int, exclude_user_id: Optional[int] = None
) -> List[User]:
    stmt = select(User).options(selectinload(User.profile)).where(
        User.startup_id == startup_id,
        User.space_id == space_id,
        User.status == UserStatus.ACTIVE
    )
    if exclude_user_id:
        stmt = stmt.where(User.id != exclude_user_id)
    result = await db.execute(stmt)
    return result.scalars().all()

async def update_user_password_by_email(db: AsyncSession, *, email: str, new_password: str) -> bool:
    user = await get_user_by_email(db, email=email)
    if not user:
        return False
    user.hashed_password = get_password_hash(new_password)
    db.add(user)
    await db.commit()
    logger.info(f"User {user.id} password updated.")
    return True

async def get_users(
    db: AsyncSession,
    *,
    skip: int = 0,
    limit: int = 100,
    user_type: Optional[UserRole] = None,
    status: Optional[UserStatus] = None,
    space_id: Optional[int] = None,
    search_term: Optional[str] = None,
    include_ids: Optional[List[int]] = None,
) -> List[User]:
    stmt = select(User)
    if user_type:
        stmt = stmt.where(User.role == user_type)
    if status:
        stmt = stmt.where(User.status == status)
    if space_id:
        stmt = stmt.where(User.space_id == space_id)
    if search_term:
        stmt = stmt.where(
            or_(
                User.full_name.ilike(f"%{search_term}%"),
                User.email.ilike(f"%{search_term}%"),
            )
        )
    
    if include_ids is not None:
        if not include_ids:
            return []
        stmt = stmt.where(User.id.in_(include_ids))

    stmt = stmt.offset(skip).limit(limit)
    # Always eager load relationships to prevent lazy loading issues
    stmt = stmt.options(
        selectinload(User.profile),
        selectinload(User.company),
        selectinload(User.startup),
        selectinload(User.space),
        selectinload(User.assignments).selectinload(WorkstationAssignment.workstation)
    )
    result = await db.execute(stmt)
    return result.scalars().all()

async def get_total_users_count(
    db: AsyncSession,
    *,
    user_type: Optional[UserRole] = None,
    status: Optional[UserStatus] = None,
    space_id: Optional[int] = None,
    search_term: Optional[str] = None
) -> int:
    logger.debug(
        f"Counting users with user_type={user_type}, "
        f"status={status}, space_id={space_id}, search_term='{search_term}'"
    )
    try:
        stmt = select(func.count(User.id))
        if user_type:
            stmt = stmt.filter(User.role == user_type)
        if status:
            stmt = stmt.filter(User.status == status)
        if space_id is not None:
            stmt = stmt.filter(User.space_id == space_id)
        if search_term:
            search_filter = or_(
                User.email.ilike(f"%{search_term}%"),
                User.full_name.ilike(f"%{search_term}%"),
            )
            stmt = stmt.filter(search_filter)
        result = await db.execute(stmt)
        count = result.scalar_one_or_none() or 0
        logger.debug(f"Total {count} users found matching criteria.")
        return count
    except SQLAlchemyError as e:
        logger.error(f"Database error counting users: {e}", exc_info=True)
        return 0

async def get_active_assignment_for_user(db: AsyncSession, *, user_id: int) -> Optional[WorkstationAssignment]:
    from app.models.space import WorkstationAssignment
    stmt = select(WorkstationAssignment).where(
        WorkstationAssignment.user_id == user_id,
        WorkstationAssignment.end_date.is_(None)
    )
    result = await db.execute(stmt)
    return result.scalars().first()

async def remove_user_from_space_and_deactivate(db: AsyncSession, *, user: User) -> User:
    from app.crud import crud_space
    if user.space_id:
        logger.info(f"User {user.id} is in space {user.space_id}. Unassigning from all workstations in that space.")
        await crud_space.unassign_user_from_all_workstations_in_space(db=db, user_id=user.id, space_id=user.space_id)
    user.space_id = None
    user.status = UserStatus.WAITLISTED
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user

async def get_admin_for_company(db: AsyncSession, *, company_id: int) -> Optional[User]:
    result = await db.execute(
        select(User).where(
            User.company_id == company_id,
            User.role == UserRole.CORP_ADMIN
        )
    )
    return result.scalars().first()

async def get_admin_for_startup(db: AsyncSession, *, startup_id: int) -> Optional[User]:
    result = await db.execute(
        select(User).where(
            User.startup_id == startup_id,
            User.role == UserRole.STARTUP_ADMIN
        )
    )
    return result.scalars().first()

async def get_users_by_space_id(db: AsyncSession, *, space_id: int, search: Optional[str] = None) -> List[User]:
    """
    Retrieves all users assigned to a specific space.
    """
    stmt = (
        select(User)
        .options(
            selectinload(User.profile),
            selectinload(User.assignments).selectinload(models.WorkstationAssignment.workstation),
            selectinload(User.company),
            selectinload(User.startup).selectinload(Startup.direct_members),
        )
        .where(User.space_id == space_id)
    )
    if search:
        stmt = stmt.where(
            or_(
                User.full_name.ilike(f"%{search}%"),
                User.email.ilike(f"%{search}%")
            )
        )
    stmt = stmt.order_by(User.full_name)
    result = await db.execute(stmt)
    return result.scalars().all()

async def get_user_by_id(db: AsyncSession, user_id: int, options: Optional[List] = None) -> Optional[User]:
    """
    Fetches a single user by their ID, with optional related data.
    """
    logger.debug(f"Fetching user by ID: {user_id} with options: {options}")
    try:
        stmt = select(User).filter(User.id == user_id)
        if options:
            stmt = stmt.options(*options)
        result = await db.execute(stmt)
        user = result.scalars().first()
        if not user:
            logger.warning(f"User with ID {user_id} not found.")
        return user
    except SQLAlchemyError as e:
        logger.error(f"Database error fetching user by ID {user_id}: {e}", exc_info=True)
        return None

async def get_users_by_company_and_role(
    db: AsyncSession, *, company_id: int, role: UserRole, search: Optional[str] = None
) -> List[User]:
    """
    Retrieves all users for a given company and role.
    """
    stmt = (
        select(User)
        .options(
            selectinload(User.profile),
            selectinload(User.assignments).selectinload(models.WorkstationAssignment.workstation),
            selectinload(User.company),
            selectinload(User.startup).selectinload(Startup.direct_members),
        )
        .where(User.company_id == company_id, User.role == role)
    )
    if search:
        stmt = stmt.where(
            or_(
                User.full_name.ilike(f"%{search}%"),
                User.email.ilike(f"%{search}%")
            )
        )
    stmt = stmt.order_by(User.full_name)
    result = await db.execute(stmt)
    return result.scalars().all()

async def bulk_update_user_status_and_space(
    db: AsyncSession, *, user_ids: List[int], status: UserStatus, space_id: Optional[int]
):
    """
    Bulk updates the status and space_id for a list of users.
    """
    if not user_ids:
        return
    stmt = (
        update(User)
        .where(User.id.in_(user_ids))
        .values(status=status, space_id=space_id)
        .execution_options(synchronize_session=False)
    )
    await db.execute(stmt)

async def disassociate_all_employees_from_company(db: AsyncSession, *, company_id: int):
    """
    Disassociates all employees from a company by setting their company_id to None.
    This is used when a company is being deleted.
    """
    stmt = (
        update(User)
        .where(User.company_id == company_id)
        .values(company_id=None)
        .execution_options(synchronize_session=False)
    )
    await db.execute(stmt)

# Wrapper class to mimic the old CRUD object structure for compatibility
class CrudUserWrapper:
    def __init__(self):
        # This adapter method handles the parameter name mismatch (id vs user_id)
        async def get_adapter(db: AsyncSession, *, id: int, options: Optional[List] = None) -> Optional[User]:
            return await get_user_by_id(db, user_id=id, options=options)

        self.get = get_adapter
        self.get_user_by_id = get_user_by_id
        self.get_user_by_email = get_user_by_email
        self.create_user = create_user
        self.update_user_internal = update_user_internal
        self.update_user_password = update_user_password
        self.get_users_by_status = get_users_by_status
        self.get_users_by_role_and_startup = get_users_by_role_and_startup
        self.get_users_by_role_and_space_id = get_users_by_role_and_space_id
        self.get_user_by_email_and_startup = get_user_by_email_and_startup
        self.activate_corporate_user = activate_corporate_user
        self.assign_user_to_space = assign_user_to_space
        self.activate_user_for_startup_invitation = activate_user_for_startup_invitation
        self.get_user_details_for_profile = get_user_details_for_profile
        self.get_users_by_startup_and_space = get_users_by_startup_and_space
        self.update_user_password_by_email = update_user_password_by_email
        self.get_users = get_users
        self.get_total_users_count = get_total_users_count
        self.get_active_assignment_for_user = get_active_assignment_for_user
        self.remove_user_from_space_and_deactivate = remove_user_from_space_and_deactivate
        self.get_admin_for_company = get_admin_for_company
        self.get_admin_for_startup = get_admin_for_startup
        self.get_users_by_space_id = get_users_by_space_id
        self.get_users_by_company_and_role = get_users_by_company_and_role
        self.bulk_update_user_status_and_space = bulk_update_user_status_and_space
        self.disassociate_all_employees_from_company = disassociate_all_employees_from_company
        self.add_user_to_space = add_user_to_space
        self.get_waitlisted_freelancers = get_waitlisted_freelancers

crud_user = CrudUserWrapper()