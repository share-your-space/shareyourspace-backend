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
