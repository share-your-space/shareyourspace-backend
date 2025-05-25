from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List

from app.db.session import get_db
from app import crud, schemas, models
from app.security import get_current_active_user, get_current_user_with_roles
from app.schemas.user import User as UserSchema

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

@router.get(
    "/startups/me/members",
    response_model=List[UserSchema],
    dependencies=[Depends(get_current_user_with_roles(required_roles=["STARTUP_ADMIN"]))],
)
async def read_my_startup_members(
    current_user: models.User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve members of the current Startup Admin's team.
    Requires the user to be a STARTUP_ADMIN.
    Members are users with the same startup_id and space_id.
    """
    if not current_user.startup_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current user is not associated with a startup.",
        )
    if not current_user.space_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current user is not associated with a space. Startup members must be in the same space.",
        )

    stmt = (
        select(models.User)
        .where(
            models.User.startup_id == current_user.startup_id,
            models.User.space_id == current_user.space_id,
            models.User.id != current_user.id
        )
    )
    result = await db.execute(stmt)
    team_members = result.scalars().all()

    return team_members

@router.post(
    "/startups/me/request-member",
    response_model=schemas.organization.MemberRequestResponse, # Use the new response schema
    dependencies=[Depends(get_current_user_with_roles(required_roles=["STARTUP_ADMIN"]))],
    status_code=status.HTTP_201_CREATED,
)
async def request_add_startup_member(
    request_data: schemas.organization.MemberRequestCreate, # Use the new request schema
    current_user: models.User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Allows a Startup Admin to request adding a new member to their startup.
    This will send a notification to the Corporate Admin of the startup's space.
    """
    if not current_user.startup_id or not current_user.startup:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current user is not associated with a startup.",
        )
    if not current_user.space_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current user is not associated with a space.",
        )

    # Get the SpaceNode to find the Corporate Admin
    space_node = await db.get(models.SpaceNode, current_user.space_id)
    if not space_node or not space_node.corporate_admin_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, # Or 500 if this state is unexpected
            detail="Cannot process request: Space admin not found for your startup's space.",
        )

    corporate_admin_id = space_node.corporate_admin_id

    # Create notification for the Corporate Admin
    try:
        startup_name = current_user.startup.name if current_user.startup else f"Startup ID {current_user.startup_id}"
        await crud.crud_notification.create_notification(
            db=db,
            user_id=corporate_admin_id,
            type="member_request",
            message=f"Startup '{startup_name}' (ID: {current_user.startup_id}) requests to add a new member: {request_data.email}.",
            reference=f"startup_id:{current_user.startup_id};requested_email:{request_data.email}",
            # link=f"/admin/member-requests?startup_id={current_user.startup_id}" # Optional: Link to a future admin UI
        )
    except Exception as e:
        # Log the error, but maybe don't fail the whole request if notification is secondary
        # For now, let's make it critical
        # logger.error(f"Failed to create notification for member request: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create notification for corporate admin: {str(e)}",
        )

    return schemas.organization.MemberRequestResponse(
        message="Member addition request sent to Corporate Admin for approval.",
        notification_sent_to_admin_id=corporate_admin_id,
        requested_email=request_data.email,
    )

# Add more endpoints later for listing, creating, updating if needed.
# Consider adding more granular authorization based on user roles/relationships. 