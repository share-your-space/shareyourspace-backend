from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app import crud, models, schemas
from app.models.enums import UserStatus, NotificationType, UserRole

async def express_interest(db: AsyncSession, *, space_id: int, current_user: models.User) -> models.Interest:
    """
    Allows a user to express interest in a space, creating an Interest object
    and notifying the space admin. If interest already exists, it returns the existing one.
    """
    # Merge the incoming user object into the current session to avoid
    # sqlalchemy.exc.InvalidRequestError: Object is already attached to session
    current_user = await db.merge(current_user)
    
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
    new_interest = models.Interest(
        space_id=space_id,
        user_id=current_user.id,
        status=models.enums.InterestStatus.PENDING
    )
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