from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud, models, schemas, security
from app.core.config import settings
from app.schemas.admin import UserStatusUpdate, SpaceUpdate
from app.schemas.user import UserUpdateInternal

async def get_all_users_paginated(
    db: AsyncSession, *, skip: int, limit: int, user_type: models.enums.UserRole,
    status: models.enums.UserStatus, space_id: int, search_term: str
):
    users = await crud.crud_user.get_users(
        db, skip=skip, limit=limit, user_type=user_type, status=status,
        space_id=space_id, search_term=search_term
    )
    total_users = await crud.crud_user.get_total_users_count(
        db, user_type=user_type, status=status, space_id=space_id, search_term=search_term
    )
    return users, total_users

async def impersonate_user(db: AsyncSession, *, user_id: int) -> str:
    user = await crud.crud_user.get_user_by_id(db, user_id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    token = security.create_access_token(
        data={"sub": user.email, "user_id": user.id, "role": user.role.value, "impersonated": True},
        expires_delta=settings.ACCESS_TOKEN_EXPIRE_MINUTES_IMPERSONATE
    )
    return token

async def update_user_status(db: AsyncSession, *, user_id: int, status_update: UserStatusUpdate) -> models.User:
    user = await crud.crud_user.get_user_by_id(db, user_id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    update_data = UserUpdateInternal(**status_update.model_dump(exclude_unset=True))
    updated_user = await crud.crud_user.update_user_internal(db=db, db_obj=user, obj_in=update_data)
    return updated_user

async def update_space_details(db: AsyncSession, *, space_id: int, space_update: SpaceUpdate) -> models.SpaceNode:
    space = await crud.crud_space.get_space_by_id(db, space_id=space_id)
    if not space:
        raise HTTPException(status_code=404, detail="Space not found")
    
    updated_space = await crud.crud_space.update_space(db=db, db_obj=space, obj_in=space_update)
    return updated_space

async def get_platform_stats(db: AsyncSession) -> schemas.admin.PlatformStats:
    # This is a placeholder. A real implementation would query the database.
    return schemas.admin.PlatformStats(
        total_users=0, active_users=0, total_spaces=0, total_connections_made=0,
        users_pending_verification=0, users_waitlisted=0, users_pending_onboarding=0,
        users_suspended=0, users_banned=0
    )

async def delete_company_and_all_resources(db: AsyncSession, *, company_id: int):
    """
    Deletes a company and all of its associated resources, including spaces,
    employees, and invitations.
    """
    company = await crud.crud_organization.get_company(db, company_id=company_id)
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found.")

    # 1. Get all spaces associated with the company
    spaces_to_delete = await crud.crud_space.get_by_company_id(db, company_id=company.id)
    space_ids_to_delete = [space.id for space in spaces_to_delete]

    # 2. Delete all workstations in those spaces
    if space_ids_to_delete:
        await crud.crud_space.terminate_all_workstation_assignments_in_space(db, space_id__in=space_ids_to_delete)

    # 3. Delete the spaces themselves
    for space_id in space_ids_to_delete:
        await crud.crud_space.space.remove(db=db, id=space_id)

    # 4. Handle employees of the company (e.g., re-assign or delete)
    # This is a placeholder for more complex logic. For now, we'll just disassociate them.
    await crud.crud_user.disassociate_all_employees_from_company(db, company_id=company.id)

    # 5. Delete pending invitations for the company
    await crud.crud_invitation.delete_invitations_for_company(db, company_id=company.id)

    # 6. Delete the company itself
    await crud.crud_organization.company.remove(db=db, id=company.id)

    return {"message": f"Company '{company.name}' and all associated resources have been deleted."} 