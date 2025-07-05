from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime

from app.models.enums import WorkstationStatus
from .common import UserSimple

class WorkstationBase(BaseModel):
    name: str
    status: WorkstationStatus = WorkstationStatus.AVAILABLE

class WorkstationCreate(WorkstationBase):
    pass

class WorkstationUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[WorkstationStatus] = None

class Workstation(WorkstationBase):
    id: int
    space_id: int
    
    model_config = ConfigDict(
        from_attributes=True,
    )

class WorkstationAssignment(BaseModel):
    id: int
    user_id: int
    workstation_id: int
    start_date: datetime

    model_config = ConfigDict(
        from_attributes=True,
    )

class SpaceWorkstationDetail(Workstation):
    """Extends Workstation with details of the assigned user."""
    occupant: Optional[UserSimple] = None

class SpaceWorkstationListResponse(BaseModel):
    workstations: List[SpaceWorkstationDetail]

class WorkstationAssignmentRequest(BaseModel):
    user_id: int 