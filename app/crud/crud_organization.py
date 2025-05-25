from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.organization import Company, Startup
from app.schemas.organization import CompanyCreate, CompanyUpdate, StartupCreate, StartupUpdate

# CRUD operations for Company
async def get_company(db: AsyncSession, company_id: int) -> Company | None:
    result = await db.execute(select(Company).filter(Company.id == company_id))
    return result.scalars().first()

# Add create_company, update_company later if needed
# async def create_company(db: AsyncSession, *, obj_in: CompanyCreate) -> Company:
#     db_obj = Company(**obj_in.dict())
#     db.add(db_obj)
#     await db.commit()
#     await db.refresh(db_obj)
#     return db_obj

# CRUD operations for Startup
async def get_startup(db: AsyncSession, startup_id: int) -> Startup | None:
    result = await db.execute(select(Startup).filter(Startup.id == startup_id))
    return result.scalars().first()

async def get_startups_by_space_id(db: AsyncSession, space_id: int) -> list[Startup]:
    """Fetches all startups associated with a given space_id."""
    result = await db.execute(
        select(Startup)
        .filter(Startup.space_id == space_id)
        .order_by(Startup.name) # Optional: order by name
    )
    return result.scalars().all()

# Add create_startup, update_startup later if needed

# Potentially add get_company_by_admin_user, get_startup_by_admin_user later 