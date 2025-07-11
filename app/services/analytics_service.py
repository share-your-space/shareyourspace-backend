from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date, timedelta

from app.crud import crud_analytics
from app.schemas.analytics import AnalyticsData

class AnalyticsService:
    async def get_analytics_data(self, db: AsyncSession, *, company_id: int) -> AnalyticsData:
        end_date = date.today()
        start_date = end_date - timedelta(days=30)

        bookings_over_time = await crud_analytics.get_bookings_over_time(
            db, company_id=company_id, start_date=start_date, end_date=end_date
        )
        tenant_growth = await crud_analytics.get_tenant_growth(
            db, company_id=company_id, start_date=start_date, end_date=end_date
        )
        workstation_utilization = await crud_analytics.get_workstation_utilization(
            db, company_id=company_id
        )
        tenant_distribution = await crud_analytics.get_tenant_distribution(
            db, company_id=company_id
        )

        return AnalyticsData(
            bookings_over_time=bookings_over_time,
            tenant_growth=tenant_growth,
            workstation_utilization=workstation_utilization,
            tenant_distribution=tenant_distribution,
        )

analytics_service = AnalyticsService()
