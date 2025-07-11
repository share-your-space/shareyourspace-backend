from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status, UploadFile
from typing import Optional

from app import crud, models, schemas
from app.services import file_service

async def get_company_details(db: AsyncSession, company_id: int) -> models.Company:
    """
    Retrieves company details.
    """
    company = await crud.crud_company.get(db, id=company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company

async def update_company_details(
    db: AsyncSession,
    company_id: int,
    company_update: schemas.CompanyUpdate,
    current_user: models.User,
) -> models.Company:
    """
    Updates company details. Only a corp admin of that company can update it.
    """
    company = await get_company_details(db, company_id)
    if company.id != current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this company",
        )

    return await crud.crud_company.update(db, db_obj=company, obj_in=company_update)

async def upload_company_logo(
    db: AsyncSession,
    company_id: int,
    logo_file: UploadFile,
    current_user: models.User,
) -> models.Company:
    """
    Uploads a logo for the company.
    """
    company = await get_company_details(db, company_id)
    if company.id != current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to upload a logo for this company",
        )

    # Use a generic folder for company assets or a specific one
    folder = f"company_logos/{company_id}"
    
    # Upload the file
    file_url = await file_service.upload_file(
        db=db,
        file=logo_file,
        user_id=current_user.id,
        folder=folder,
        allowed_content_types=["image/jpeg", "image/png", "image/gif"],
    )

    # Update the company's logo_url
    company.logo_url = file_url
    await db.commit()
    await db.refresh(company)

    return company
