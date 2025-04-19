from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError

from app.models.user import User
from app.schemas.user import UserCreate
from app.security import get_password_hash

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
    
    # Map frontend role_type to backend User.role
    if obj_in.role_type == 'CORP_REP':
        db_role = 'CORP_ADMIN'
    elif obj_in.role_type == 'STARTUP_REP':
        db_role = 'STARTUP_ADMIN'
    else: # Default to FREELANCER
        db_role = 'FREELANCER'

    # Create the User model instance
    db_user = User(
        email=obj_in.email,
        full_name=obj_in.full_name,
        hashed_password=hashed_password,
        role=db_role,
        status='PENDING_VERIFICATION',  # Initial status
        # company_name and title are not directly on User model based on schema read
        # If they should be, update the User model
        is_active=True # Or False until verified? Decide based on flow
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