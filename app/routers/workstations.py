from fastapi import APIRouter, Depends, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.db.session import get_db
from app import models, schemas, services, crud
from app.dependencies import get_current_active_user, get_current_user_with_roles

router = APIRouter()

@router.post(
    "/spaces/{space_id}/workstations/assign",
    response_model=schemas.space.WorkstationAssignmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def assign_workstation_to_user(
    space_id: int,
    assignment_data: schemas.space.WorkstationAssignmentRequest,
    request: Request, 
    current_user: models.User = Depends(get_current_user_with_roles(["CORP_ADMIN"])),
    db: AsyncSession = Depends(get_db),
):
    """Assign a user to a workstation within a managed space."""
    return await services.workstation_service.assign_workstation(
        db=db, request=request, space_id=space_id, assignment_data=assignment_data, current_user=current_user
    )

@router.post(
    "/spaces/{space_id}/workstations/unassign",
    response_model=schemas.Message,
)
async def unassign_user_from_workstation(
    space_id: int,
    unassign_data: schemas.space.WorkstationUnassignRequest,
    request: Request,
    current_user: models.User = Depends(get_current_user_with_roles(["CORP_ADMIN"])),
    db: AsyncSession = Depends(get_db),
):
    """Unassign a user from a workstation within a managed space."""
    return await services.workstation_service.unassign_workstation(
        db=db, request=request, space_id=space_id, unassign_data=unassign_data, current_user=current_user
    )

@router.get(
    "/spaces/{space_id}/workstations",
    response_model=schemas.space.SpaceWorkstationListResponse,
)
async def list_space_workstations(
    space_id: int,
    current_user: models.User = Depends(get_current_user_with_roles(["CORP_ADMIN"])),
    db: AsyncSession = Depends(get_db),
):
    """List all workstations within a managed space, including status and occupant."""
    await services.corp_admin_service.check_admin_space_permission(db, current_user=current_user, space_id=space_id)
    
    workstations_orm = await crud.crud_space.get_workstations_in_space(db, space_id=space_id)
    
    workstation_details_list: List[schemas.space.WorkstationDetail] = []
    for ws_orm in workstations_orm:
        occupant_info = None
        status = ws_orm.status
        
        if ws_orm.active_assignment and ws_orm.active_assignment.user:
            status = schemas.space.WorkstationStatus.OCCUPIED
            occupant_info = schemas.space.WorkstationTenantInfo.from_orm(ws_orm.active_assignment.user)

        workstation_details_list.append(
            schemas.space.WorkstationDetail(
                id=ws_orm.id,
                name=ws_orm.name,
                status=status,
                space_id=ws_orm.space_id,
                occupant=occupant_info,
            )
        )
    return schemas.space.SpaceWorkstationListResponse(workstations=workstation_details_list)

@router.put(
    "/spaces/{space_id}/workstations/{workstation_id}/status",
    response_model=schemas.space.WorkstationDetail,
)
async def update_workstation_status(
    space_id: int,
    workstation_id: int,
    status_update: schemas.space.WorkstationStatusUpdateRequest,
    current_user: models.User = Depends(get_current_user_with_roles(["CORP_ADMIN"])),
    db: AsyncSession = Depends(get_db),
):
    """Update the status of a specific workstation within a managed space."""
    await services.corp_admin_service.check_admin_space_permission(db, current_user=current_user, space_id=space_id)
    
    updated_workstation = await crud.crud_space.update_workstation_status(
        db, space_id=space_id, workstation_id=workstation_id, new_status=status_update.status
    )
    return updated_workstation 