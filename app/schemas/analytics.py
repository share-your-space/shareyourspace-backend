from pydantic import BaseModel
from typing import List, Dict
from datetime import date

class TimeSeriesData(BaseModel):
    date: date
    count: int

class AnalyticsData(BaseModel):
    bookings_over_time: List[TimeSeriesData]
    tenant_growth: List[TimeSeriesData]
    workstation_utilization: float # A percentage
    tenant_distribution: Dict[str, int]

class MonthlyBooking(BaseModel):
    month: str
    count: int

class WorkstationUtilization(BaseModel):
    occupied: int
    available: int

class AnalyticsOverview(BaseModel):
    total_bookings: int
    monthly_bookings: List[MonthlyBooking]
    workstation_utilization: WorkstationUtilization
    top_users: List[Dict[str, int]]
