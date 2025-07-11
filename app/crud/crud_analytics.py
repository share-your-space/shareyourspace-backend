from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, cast, Date
from typing import List, Dict
from datetime import date, timedelta

from app.models import WorkstationAssignment, User, organization, SpaceNode, Workstation
from app.models.enums import UserRole

class CRUDAnalytics:
    async def get_bookings_over_time(self, db: AsyncSession, *, company_id: int, start_date: date, end_date: date) -> List[Dict]:
        space_ids_query = select(SpaceNode.id).where(SpaceNode.company_id == company_id)
        
        stmt = (
            select(
                cast(WorkstationAssignment.start_date, Date).label("date"),
                func.count(WorkstationAssignment.id).label("count")
            )
            .join(SpaceNode, WorkstationAssignment.space_id == SpaceNode.id)
            .where(
                SpaceNode.company_id == company_id,
                cast(WorkstationAssignment.start_date, Date).between(start_date, end_date)
            )
            .group_by(cast(WorkstationAssignment.start_date, Date))
            .order_by(cast(WorkstationAssignment.start_date, Date))
        )
        result = await db.execute(stmt)
        return result.mappings().all()

    async def get_tenant_growth(self, db: AsyncSession, *, company_id: int, start_date: date, end_date: date) -> List[Dict]:
        space_ids_query = select(SpaceNode.id).where(SpaceNode.company_id == company_id)
        
        # Freelancers
        freelancer_stmt = (
            select(
                cast(User.created_at, Date).label("date"),
                func.count(User.id).label("count")
            )
            .where(
                User.space_id.in_(space_ids_query),
                User.role == UserRole.FREELANCER,
                cast(User.created_at, Date).between(start_date, end_date)
            )
            .group_by(cast(User.created_at, Date))
        )
        
        # Startups
        startup_stmt = (
            select(
                cast(organization.Startup.created_at, Date).label("date"),
                func.count(organization.Startup.id).label("count")
            )
            .where(
                organization.Startup.space_id.in_(space_ids_query),
                cast(organization.Startup.created_at, Date).between(start_date, end_date)
            )
            .group_by(cast(organization.Startup.created_at, Date))
        )

        freelancer_result = await db.execute(freelancer_stmt)
        startup_result = await db.execute(startup_stmt)

        # Combine results
        growth_data = {}
        for row in freelancer_result.mappings().all():
            growth_data[row.date] = growth_data.get(row.date, 0) + row.count
        for row in startup_result.mappings().all():
            growth_data[row.date] = growth_data.get(row.date, 0) + row.count
            
        return [{"date": d, "count": c} for d, c in sorted(growth_data.items())]

    async def get_workstation_utilization(self, db: AsyncSession, *, company_id: int) -> float:
        space_ids_query = select(SpaceNode.id).where(SpaceNode.company_id == company_id)
        
        total_workstations_stmt = select(func.count()).select_from(select(Workstation).where(Workstation.space_id.in_(space_ids_query)).subquery())
        occupied_workstations_stmt = select(func.count()).select_from(select(Workstation).where(Workstation.space_id.in_(space_ids_query), Workstation.status == 'OCCUPIED').subquery())

        total_workstations = await db.scalar(total_workstations_stmt)
        occupied_workstations = await db.scalar(occupied_workstations_stmt)

        if total_workstations == 0:
            return 0.0
        
        return (occupied_workstations / total_workstations) * 100

    async def get_tenant_distribution(self, db: AsyncSession, *, company_id: int) -> Dict[str, int]:
        space_ids_query = select(SpaceNode.id).where(SpaceNode.company_id == company_id)

        freelancers_count_stmt = select(func.count()).select_from(select(User).where(User.space_id.in_(space_ids_query), User.role == UserRole.FREELANCER).subquery())
        startups_count_stmt = select(func.count()).select_from(select(organization.Startup).where(organization.Startup.space_id.in_(space_ids_query)).subquery())

        freelancers_count = await db.scalar(freelancers_count_stmt)
        startups_count = await db.scalar(startups_count_stmt)

        return {"freelancers": freelancers_count, "startups": startups_count}


crud_analytics = CRUDAnalytics()
