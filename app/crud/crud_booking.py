from sqlalchemy.orm import joinedload
from sqlalchemy.future import select
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.space import WorkstationAssignment, SpaceNode
from app.models.user import User
from app.models.organization import Company

class CRUDBooking:
    async def get_bookings_by_company_id(self, db: AsyncSession, *, company_id: int) -> List[WorkstationAssignment]:
        stmt = (
            select(WorkstationAssignment)
            .join(SpaceNode, WorkstationAssignment.space_id == SpaceNode.id)
            .where(SpaceNode.company_id == company_id)
            .options(
                joinedload(WorkstationAssignment.user).joinedload(User.profile),
                joinedload(WorkstationAssignment.workstation)
            )
            .order_by(WorkstationAssignment.start_date.desc())
        )
        result = await db.execute(stmt)
        return result.scalars().all()

crud_booking = CRUDBooking()
