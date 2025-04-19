from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

import app.crud.crud_user as crud_user
import app.schemas.user as user_schemas
from app.db.session import get_db

router = APIRouter()

@router.post("/register", response_model=user_schemas.User, status_code=status.HTTP_201_CREATED)
async def register_user(
    user_in: user_schemas.UserCreate,
    db: AsyncSession = Depends(get_db)
):
    """Register a new user."""
    existing_user = await crud_user.get_user_by_email(db, email=user_in.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Attempt to create the user
    try:
        db_user = await crud_user.create_user(db=db, obj_in=user_in)
        return db_user
    except Exception as e:
        # Catch potential errors from CRUD operation (e.g., database errors)
        # Log the detailed error internally
        print(f"Error during user registration: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during registration."
        )

# Add other auth routes here later (login, verify-email, etc.) 