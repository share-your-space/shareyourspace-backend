from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app import crud, models, schemas
from app.models.enums import UserStatus, NotificationType, UserRole
from app.models.enums import InterestStatus

async def express_interest(db: AsyncSession, *, space_id: int, current_user: models.User) -> models.Interest:
    """
    Allows a user to express interest in a space, creating an Interest object
    and notifying the space admin. If interest already exists, it returns the existing one.
    """
    # Eager load the startup relationship for the current user
    user_stmt = select(models.User).options(selectinload(models.User.startup)).where(models.User.id == current_user.id)
    user_result = await db.execute(user_stmt)
    current_user = user_result.scalar_one_or_none()

    if not current_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    
    if current_user.role not in [UserRole.FREELANCER, UserRole.STARTUP_ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only freelancers and startup admins can express interest in a space."
        )

    space = await crud.crud_space.get_space_by_id(db, space_id=space_id)
    if not space:
        raise HTTPException(status_code=404, detail="Space not found.")

    if not space.company_id:
        raise HTTPException(status_code=400, detail="This space is not yet ready to accept expressions of interest.")
    
    company_admins = await crud.crud_user.get_users_by_company_and_role(db, company_id=space.company_id, role=UserRole.CORP_ADMIN)
    if not company_admins:
        raise HTTPException(status_code=400, detail="This space is not ready to accept expressions of interest as there is no admin to review it.")
    
    if current_user.role == UserRole.STARTUP_ADMIN and current_user.startup and current_user.startup.space_id == space_id:
         raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Your startup is already in this space."
        )
    if current_user.role == UserRole.FREELANCER and current_user.space_id == space_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You are already in this space."
        )

    existing_interest = await crud.crud_interest.interest.get_by_user_and_space(
        db, user_id=current_user.id, space_id=space_id
    )
    if existing_interest:
        loaded_interest = await crud.crud_interest.interest.get_with_full_details(db, id=existing_interest.id)
        if not loaded_interest:
             raise HTTPException(status_code=404, detail="Could not retrieve existing interest.")
        return loaded_interest

    # Create objects and add to session without committing
    new_interest_data = {
        "space_id": space_id,
        "user_id": current_user.id,
        "status": models.enums.InterestStatus.PENDING,
    }
    if current_user.role == UserRole.STARTUP_ADMIN and current_user.startup:
        new_interest_data["startup_id"] = current_user.startup.id

    new_interest = models.Interest(**new_interest_data)
    db.add(new_interest)

    for admin in company_admins:
        notification = models.Notification(
            user_id=admin.id,
            type=models.enums.NotificationType.INTEREST_EXPRESSED,
            message=f"{current_user.full_name or current_user.email} has expressed interest in your space: {space.name}.",
            related_entity_id=current_user.id
        )
        db.add(notification)
    
    # Commit all changes at once
    await db.commit()
    
    # Re-fetch the interest with the user relationship loaded to prevent lazy-loading errors
    final_interest = await crud.crud_interest.interest.get_with_full_details(db, id=new_interest.id)
    
    if not final_interest:
        raise HTTPException(status_code=500, detail="Could not retrieve interest after creation.")

    return final_interest

async def accept_invitation(
    db: AsyncSession, *, interest_id: int, current_user: models.User
) -> None:
    """
    Allows a user to accept an invitation to join a space.
    """
    interest = await crud.crud_interest.interest.get(db, id=interest_id)
    if not interest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found.")

    # Security check: ensure the current user is the one who was invited
    if interest.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to accept this invitation.")

    if interest.status != InterestStatus.INVITED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This invitation is not active or has already been actioned.")

    # Add the user or startup to the space
    if interest.startup_id:
        await crud.crud_organization.add_startup_to_space(db, startup_id=interest.startup_id, space_id=interest.space_id)
    else:
        await crud.crud_user.add_user_to_space(db, user_id=interest.user_id, space_id=interest.space_id)

    interest.status = InterestStatus.ACCEPTED
    db.add(interest)

    # Optional: Notify the corporate admin that their invitation was accepted
    space = await crud.crud_space.space.get(db, id=interest.space_id)
    if space and space.corporate_admin_id:
        await crud.crud_notification.create_notification(
            db=db,
            user_id=space.corporate_admin_id,
            type=NotificationType.INVITATION_ACCEPTED,
            message=f"{current_user.full_name} has accepted your invitation to join '{space.name}'.",
            link=f"/corp-admin/space-profile?spaceId={space.id}" # Example link
        )

    await db.commit()