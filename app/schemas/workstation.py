from pydantic import BaseModel

class WorkstationAssignmentRequest(BaseModel):
    user_id: int 