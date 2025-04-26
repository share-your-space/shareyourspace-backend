from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app import crud, schemas, models
from app.security import get_current_active_user

router = APIRouter()

@router.get(
    "/companies/{company_id}",
    response_model=schemas.organization.Company,
    dependencies=[Depends(get_current_active_user)] # Ensure user is authenticated
)
async def read_company(
    company_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Retrieve company details by ID."""
    db_company = await crud.crud_organization.get_company(db, company_id=company_id)
    if db_company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return db_company

@router.get(
    "/startups/{startup_id}",
    response_model=schemas.organization.Startup,
    dependencies=[Depends(get_current_active_user)] # Ensure user is authenticated
)
async def read_startup(
    startup_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Retrieve startup details by ID."""
    db_startup = await crud.crud_organization.get_startup(db, startup_id=startup_id)
    if db_startup is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Startup not found")
    return db_startup

# Add more endpoints later for listing, creating, updating if needed.
# Consider adding more granular authorization based on user roles/relationships. 