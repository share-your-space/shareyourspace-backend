from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas, models, crud
from app.db.session import get_db
from app.security import get_current_user_with_roles
from app.models.enums import UserRole, NotificationType

router = APIRouter(
    tags=["Workstations"],
    dependencies=[Depends(get_current_user_with_roles([UserRole.STARTUP_ADMIN]))]
)

@router.post("/request-assignment", status_code=status.HTTP_202_ACCEPTED)
async def request_workstation_assignment(
    payload: schemas.workstation.WorkstationAssignmentRequest,
    db: AsyncSession = Depends(get_db),
    current_admin: models.User = Depends(get_current_user_with_roles([UserRole.STARTUP_ADMIN])),
):
    """
    Allows a Startup Admin to request a workstation for one of their members.
    This creates a notification for the Corporate Admin of the space.
    """
    if not current_admin.space_id:
        raise HTTPException(status_code=400, detail="You are not associated with a space.")

    member = await crud.crud_user.get_user_by_id(db, user_id=payload.user_id)
    if not member or member.startup_id != current_admin.startup_id:
        raise HTTPException(status_code=404, detail="Member not found in your startup.")

    space = await crud.crud_space.get_space_by_id(db, space_id=current_admin.space_id)
    if not space or not space.corporate_admin_id:
        raise HTTPException(status_code=404, detail="Corporate admin for your space not found.")

    await crud.crud_notification.create_notification(
        db=db,
        user_id=space.corporate_admin_id,
        type=NotificationType.WORKSTATION_ASSIGNED, # A more specific type could be created
        message=f"Startup '{current_admin.startup.name}' requests a workstation for their member: {member.full_name or member.email}.",
        related_entity_id=member.id
    )
    
    await db.commit()
    
    return {"message": "Workstation assignment request sent to the Corporate Admin."} 