import logging
from fastapi import HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud, models, schemas
from app.services.corp_admin_service import check_admin_space_permission

logger = logging.getLogger(__name__)

async def create_workstation(
    db: AsyncSession, *, space_id: int, workstation_in: schemas.WorkstationCreate, current_user: models.User
) -> models.Workstation:
    """
    Creates a new workstation in a space, validating admin permissions.
    """
    await check_admin_space_permission(db, current_user=current_user, space_id=space_id)

    new_workstation = await crud.crud_space.create_workstation(db, workstation_in=workstation_in, space_id=space_id)
    if not new_workstation:
        # This case might be redundant if create_workstation always raises or returns, but good practice.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not create workstation.")
        
    return new_workstation

async def update_workstation_details(
    db: AsyncSession, *, space_id: int, workstation_id: int, workstation_in: schemas.WorkstationUpdate, current_user: models.User
) -> models.Workstation:
    """
    Updates a workstation's details, validating admin permissions.
    """
    await check_admin_space_permission(db, current_user=current_user, space_id=space_id)

    workstation_obj = await crud.crud_space.get_workstation_by_id_and_space_id(
        db, workstation_id=workstation_id, space_id=space_id
    )
    if not workstation_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workstation not found in this space.")

    return await crud.crud_space.update_workstation(
        db, workstation_obj=workstation_obj, workstation_in=workstation_in
    )

async def delete_workstation_by_id(db: AsyncSession, *, space_id: int, workstation_id: int, current_user: models.User) -> None:
    """
    Deletes a workstation, handling unassignment and notifications.
    """
    await check_admin_space_permission(db, current_user=current_user, space_id=space_id)

    workstation_to_delete = await crud.crud_space.get_workstation_by_id_and_space_id(
        db, workstation_id=workstation_id, space_id=space_id
    )
    if not workstation_to_delete:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workstation not found in this space.")

    unassigned_user_id = None
    if workstation_to_delete.active_assignment:
        unassigned_user_id = workstation_to_delete.active_assignment.user_id

    await crud.crud_space.delete_workstation(db=db, workstation_id=workstation_id, space_id=space_id)

    if unassigned_user_id:
        await crud.crud_notification.create_notification(
            db=db,
            user_id=unassigned_user_id,
            type=models.NotificationType.WORKSTATION_UNASSIGNED,
            message=f"Your workstation '{workstation_to_delete.name}' was removed by an admin.",
            link="/dashboard"
        )
        await db.commit()
    return

async def assign_workstation(
    db: AsyncSession, *, request: Request, space_id: int, assignment_data: schemas.space.WorkstationAssignmentRequest, current_user: models.User
) -> schemas.space.WorkstationAssignmentResponse:
    await check_admin_space_permission(db, current_user=current_user, space_id=space_id)

    try:
        assignment_result = await crud.crud_space.assign_user_to_workstation(
            db=db,
            user_id=assignment_data.user_id,
            workstation_id=assignment_data.workstation_id,
            space_id=space_id,
            assigning_admin_id=current_user.id
        )
        new_assignment, workstation_name = assignment_result

        # Emit Socket.IO event
        try:
            sio_server = request.app.state.sio
            await sio_server.emit('workstation_changed', data={"status": "assigned", "workstation_name": workstation_name}, room=str(assignment_data.user_id))
        except Exception as e:
            logger.error(f"Failed to emit Socket.IO event for workstation assignment: {e}", exc_info=True)

        return schemas.space.WorkstationAssignmentResponse.model_validate(new_assignment)

    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))


async def unassign_workstation(
    db: AsyncSession, *, request: Request, space_id: int, workstation_id: int, current_user: models.User
) -> schemas.Message:
    await check_admin_space_permission(db, current_user=current_user, space_id=space_id)

    try:
        unassign_result = await crud.crud_space.unassign_user_from_workstation(
            db=db,
            workstation_id=workstation_id,
            space_id=space_id,
            unassigning_admin_id=current_user.id
        )
        if not unassign_result:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workstation is not occupied or not found.")

        workstation, assigned_user_id = unassign_result
        
        # Emit Socket.IO event
        try:
            sio_server = request.app.state.sio
            await sio_server.emit('workstation_changed', data={"status": "unassigned", "workstation_name": workstation.name}, room=str(assigned_user_id))
        except Exception as e:
            logger.error(f"Failed to emit Socket.IO event for unassignment: {e}", exc_info=True)

        # Create notification for the unassigned user
        await crud.crud_notification.create_notification(
            db=db,
            user_id=assigned_user_id,
            type=models.NotificationType.WORKSTATION_UNASSIGNED,
            message=f"You have been unassigned from workstation '{workstation.name}' by an admin.",
            link="/dashboard"
        )
        await db.commit()

        return schemas.Message(message=f"User successfully unassigned from workstation '{workstation.name}'.")

    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))

async def update_workstation_status(
    db: AsyncSession, *, space_id: int, workstation_id: int, status_update: schemas.WorkstationStatusUpdateRequest, current_user: models.User
) -> models.Workstation:
    """
    Updates the status of a specific workstation, validating admin permissions.
    """
    await check_admin_space_permission(db, current_user=current_user, space_id=space_id)

    workstation = await crud.crud_space.get_workstation_by_id_and_space_id(
        db, workstation_id=workstation_id, space_id=space_id
    )
    if not workstation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workstation not found in this space.")

    # If changing status to AVAILABLE, ensure no user is assigned.
    if status_update.status == schemas.WorkstationStatus.AVAILABLE and workstation.active_assignment:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot set status to AVAILABLE. Workstation is currently occupied. Please unassign the user first."
        )

    updated_workstation = await crud.crud_space.update_workstation_status(
        db, workstation_obj=workstation, new_status=status_update.status
    )
    return updated_workstation 