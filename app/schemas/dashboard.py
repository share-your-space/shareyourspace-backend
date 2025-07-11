from pydantic import BaseModel


class DashboardStats(BaseModel):
    total_spaces: int
    total_workstations: int
    occupied_workstations: int
    available_workstations: int
    total_tenants: int
    pending_invites: int
