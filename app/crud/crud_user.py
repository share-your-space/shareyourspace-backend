from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import Select # Import Select for type hint
from sqlalchemy.orm import Load, selectinload # Import Load, selectinload for type hint
import logging # Add logging import

from app.models.user import User
from app.models.space import WorkstationAssignment # Ensure WorkstationAssignment is imported
from app.schemas.user import UserCreate, UserUpdateInternal
from app.utils.security_utils import get_password_hash, verify_password
from typing import List, Optional, Sequence # Import Sequence

logger = logging.getLogger(__name__) # Add logger instance

async def get_user_by_id(
    db: AsyncSession, 
    *, 
    user_id: int, 
    options: Optional[Sequence[Load]] = None # Add options parameter
) -> User | None:
    """Fetch a single user by ID, optionally applying loading options."""
    try:
        stmt = select(User).filter(User.id == user_id)
        if options:
            stmt = stmt.options(*options) # Apply options if provided
            
        result = await db.execute(stmt)
        return result.scalars().first()
    except SQLAlchemyError as e:
        print(f"Database error fetching user by ID {user_id}: {e}")
        return None

async def get_user_by_email(db: AsyncSession, *, email: str) -> User | None:
    """Fetch a single user by email."""
    try:
        result = await db.execute(select(User).filter(User.email == email))
        return result.scalars().first()
    except SQLAlchemyError as e:
        # Handle potential database errors (log them, etc.)
        print(f"Database error fetching user by email: {e}")
        return None

async def create_user(db: AsyncSession, *, obj_in: UserCreate) -> User:
    """Create a new user."""
    hashed_password = get_password_hash(obj_in.password)
    
    # Determine initial status based on role
    initial_status = 'PENDING_VERIFICATION' # Default
    if obj_in.role == 'FREELANCER':
        initial_status = 'WAITLISTED' # As per ON-05 flow
    elif obj_in.role == 'STARTUP_ADMIN':
        initial_status = 'WAITLISTED' # As per ON-05 flow
    elif obj_in.role == 'CORP_ADMIN': # Should be CORP_REPRESENTATIVE during signup
        initial_status = 'PENDING_ONBOARDING' # As per ON-06 flow

    # Create the User model instance
    db_user = User(
        email=obj_in.email,
        full_name=obj_in.full_name,
        hashed_password=hashed_password,
        role=obj_in.role,
        status=initial_status, # Use determined status
        is_active=False # Usually set to True after verification/activation
    )
    
    try:
        db.add(db_user)
        await db.commit()
        await db.refresh(db_user)
        return db_user
    except SQLAlchemyError as e:
        await db.rollback() 
        # Handle potential database errors (log them, raise specific exceptions, etc.)
        print(f"Database error creating user: {e}")
        raise # Re-raise the exception for the router to handle 

async def update_user_internal(db: AsyncSession, *, db_obj: User, obj_in: UserUpdateInternal) -> User:
    """Update user fields internally (e.g., status)."""
    update_data = obj_in.model_dump(exclude_unset=True)
    logger.info(f"Updating user {db_obj.id}. Current state: status={db_obj.status}, is_active={db_obj.is_active}. Update data: {update_data}")
    for field, value in update_data.items():
        setattr(db_obj, field, value)
    logger.info(f"User {db_obj.id} state after setattr: status={db_obj.status}, is_active={db_obj.is_active}") # Log after setattr
    db.add(db_obj)
    try:
        await db.commit()
        logger.info(f"User {db_obj.id} update commit successful.")
        await db.refresh(db_obj)
        logger.info(f"User {db_obj.id} state after refresh: status={db_obj.status}, is_active={db_obj.is_active}")
        return db_obj
    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(f"Database error during internal update for user {db_obj.id}: {e}", exc_info=True) # Log exception info
        raise 

async def update_user_password(db: AsyncSession, *, user: User, new_password: str) -> User:
    """Update a user's password."""
    hashed_password = get_password_hash(new_password)
    user.hashed_password = hashed_password
    db.add(user)
    try:
        await db.commit()
        await db.refresh(user)
        return user
    except SQLAlchemyError as e:
        await db.rollback()
        print(f"Database error updating user password: {e}")
        raise 

async def get_users_by_status(db: AsyncSession, status: str) -> List[User]:
    """Get a list of users filtered by their status."""
    result = await db.execute(select(User).filter(User.status == status))
    return result.scalars().all()

async def get_users_by_role_and_startup(db: AsyncSession, *, role: str, startup_id: int) -> List[User]:
    """Get a list of users filtered by their role and startup ID."""
    stmt = select(User).where(User.role == role, User.startup_id == startup_id)
    result = await db.execute(stmt)
    return result.scalars().all()

async def get_users_by_role_and_space_id(db: AsyncSession, *, role: str, space_id: int) -> List[User]:
    """Get a list of users filtered by their role and space ID."""
    stmt = select(User).where(User.role == role, User.space_id == space_id)
    result = await db.execute(stmt)
    return result.scalars().all()

async def get_user_by_email_and_startup(db: AsyncSession, *, email: str, startup_id: int) -> Optional[User]:
    """Fetch a single user by email if they belong to a specific startup."""
    try:
        stmt = select(User).where(User.email == email, User.startup_id == startup_id)
        result = await db.execute(stmt)
        return result.scalars().first()
    except SQLAlchemyError as e:
        logger.error(f"Database error fetching user by email {email} for startup {startup_id}: {e}")
        return None

async def activate_corporate_user(db: AsyncSession, *, user_id: int, space_id: Optional[int] = None) -> Optional[User]:
    """Activates a user with PENDING_ONBOARDING status to CORP_ADMIN and ACTIVE."""
    user = await get_user_by_id(db, user_id=user_id)
    if not user or user.status != 'PENDING_ONBOARDING':
        return None # Or raise an exception

    update_data = {
        "status": "ACTIVE",
        "role": "CORP_ADMIN",
        "is_active": True,
        "space_id": space_id # Assign space if provided
    }
    return await update_user_internal(db, db_obj=user, obj_in=UserUpdateInternal(**update_data))

async def assign_user_to_space(db: AsyncSession, *, user_id: int, space_id: Optional[int]) -> Optional[User]:
    """Assigns or unassigns a user to a specific space."""
    user = await get_user_by_id(db, user_id=user_id)
    if not user:
        return None # Or raise error
    
    # Check if space exists if assigning (space_id is not None)
    if space_id is not None:
        from .crud_space import get_space # Local import to avoid circular dependency issues
        space = await get_space(db, space_id=space_id)
        if not space:
            # Raise a specific error or return None/False to indicate space not found
            raise ValueError(f"Space with ID {space_id} not found.") 

    user.space_id = space_id
    db.add(user)
    try:
        await db.commit()
        await db.refresh(user)
        return user
    except SQLAlchemyError as e:
        await db.rollback()
        print(f"Database error assigning user to space: {e}")
        raise

async def activate_user_for_startup_invitation(db: AsyncSession, *, user_to_activate: User) -> Optional[User]:
    """Activates a user created via startup invitation and sets their status."""
    if user_to_activate:
        user_to_activate.is_active = True
        user_to_activate.status = "ACTIVE" # Or UserStatus.ACTIVE if using enum
        db.add(user_to_activate)
        await db.commit()
        await db.refresh(user_to_activate)
        logger.info(f"User {user_to_activate.id} activated via startup invitation. Status: {user_to_activate.status}")
        return user_to_activate
    return None

async def get_user_details_for_profile(db: AsyncSession, user_id: int) -> Optional[User]:
    """
    Fetches a user by ID with related details for their profile page.
    Eager loads profile, company, startup, space (they belong to), 
    managed_space (if Corp Admin), and active workstation assignment.
    """
    stmt = (
        select(User)
        .where(User.id == user_id)
        .options(
            selectinload(User.profile),
            selectinload(User.company),
            selectinload(User.startup),
            selectinload(User.space), # Space the user belongs to
            selectinload(User.managed_space), # Space the user manages (if Corp Admin)
            selectinload(User.assignments).options( # Load assignments
                selectinload(WorkstationAssignment.workstation) # And the related workstation for each assignment
            )
        )
    )
    result = await db.execute(stmt)
    user = result.scalars().first()
    return user

# Note: Consider consolidating activation logic if rules become complex.
# For example, a generic activate_user(user, new_status) might be useful.

# user = CRUDUser(User) # This line seems to be for a CRUDBase pattern not fully used here yet