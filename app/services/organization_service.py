from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud, models, schemas

async def get_company_profile(db: AsyncSession, company_id: int) -> models.organization.Company:
    company = await crud.crud_organization.get_company(db, company_id=company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company

async def update_company_profile(
    db: AsyncSession, *, company_in: schemas.organization.CompanyUpdate, current_user: models.User
) -> models.organization.Company:
    if not current_user.company_id:
        raise HTTPException(status_code=404, detail="User not associated with a company")
    
    company = await get_company_profile(db, company_id=current_user.company_id)
    updated_company = await crud.crud_organization.update_company(db=db, db_obj=company, obj_in=company_in)
    return updated_company

async def get_startup_profile(
    db: AsyncSession, *, startup_id: int, current_user: models.User
) -> models.organization.Startup:
    startup = await crud.crud_organization.get_startup(db, startup_id=startup_id)
    if not startup:
        raise HTTPException(status_code=404, detail="Startup not found")

    is_own_profile = current_user.startup_id == startup_id
    is_sys_admin = current_user.role == models.enums.UserRole.SYS_ADMIN
    is_active_startup = startup.status == models.enums.UserStatus.ACTIVE
    is_corp_admin = current_user.role == models.enums.UserRole.CORP_ADMIN

    if not (is_active_startup or is_own_profile or is_sys_admin or is_corp_admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view this startup profile.")
        
    return startup

async def update_startup_profile(
    db: AsyncSession, *, startup_in: schemas.organization.StartupUpdate, current_user: models.User
) -> models.organization.Startup:
    if not current_user.startup_id:
        raise HTTPException(status_code=404, detail="User not associated with a startup")

    startup = await crud.crud_organization.get_startup(db, startup_id=current_user.startup_id)
    if not startup:
        raise HTTPException(status_code=404, detail="Startup not found")
        
    updated_startup = await crud.crud_organization.update_startup(db=db, db_obj=startup, obj_in=startup_in)
    return updated_startup 