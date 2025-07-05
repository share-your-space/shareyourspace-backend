from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from typing import List, Optional

from app.crud.base import CRUDBase
from app.models.interest import Interest, InterestStatus
from app.models.space import SpaceNode
from app.models.user import User
from app.models.organization import Startup
from app.schemas.interest import InterestCreate, InterestUpdate

class CRUDInterest(CRUDBase[Interest, InterestCreate, InterestUpdate]):
    async def get_by_user_and_space(
        self, db: AsyncSession, *, user_id: int, space_id: int
    ) -> Optional[Interest]:
        """
        Get an interest by user and space ID.
        """
        statement = select(self.model).where(
            self.model.user_id == user_id, self.model.space_id == space_id
        )
        result = await db.execute(statement)
        return result.scalar_one_or_none()

    async def create_with_user_and_space(
        self, db: AsyncSession, *, obj_in: InterestCreate, user_id: int
    ) -> Interest:
        """
        Create an interest, linking it to the user and space.
        """
        db_obj = self.model(**obj_in.model_dump(), user_id=user_id, status=InterestStatus.PENDING)
        db.add(db_obj)
        await db.commit()
        
        # Re-fetch the object with all necessary relationships eager-loaded to prevent lazy loading errors.
        result = await db.execute(
            select(self.model)
            .where(self.model.id == db_obj.id)
            .options(
                selectinload(self.model.user),
                selectinload(self.model.space).selectinload(SpaceNode.company)
            )
        )
        return result.scalar_one()

    async def get_interests_for_space(
        self, db: AsyncSession, *, space_id: int
    ) -> List[Interest]:
        """
        Get all interests (pending, accepted, etc.) for a specific space.
        """
        statement = (
            select(self.model)
            .where(self.model.space_id == space_id)
            .options(
                selectinload(self.model.user).selectinload(User.profile),
            )
            .order_by(self.model.created_at.desc())
        )
        result = await db.execute(statement)
        return result.scalars().all()

    async def get_interests_for_spaces(
        self, db: AsyncSession, *, space_ids: List[int]
    ) -> List[Interest]:
        if not space_ids:
            return []
        result = await db.execute(
            select(self.model).where(self.model.space_id.in_(space_ids))
        )
        return result.scalars().all()

    async def get_interests_by_user(
        self, db: AsyncSession, *, user_id: int
    ) -> List[Interest]:
        """
        Get all interests for a specific user.
        """
        statement = select(self.model).where(self.model.user_id == user_id)
        result = await db.execute(statement)
        return result.scalars().all()

    async def get_by_id_with_user(self, db: AsyncSession, *, id: int) -> Optional[Interest]:
        result = await db.execute(
            select(self.model).options(selectinload(self.model.user)).filter(self.model.id == id)
        )
        return result.scalars().first()

    async def get_with_full_details(self, db: AsyncSession, *, id: int) -> Optional[Interest]:
        """
        Get an interest by ID, with the user and their full startup details (including members) loaded.
        This is to prevent lazy-loading errors during response serialization.
        """
        result = await db.execute(
            select(self.model)
            .options(
                selectinload(self.model.user)
                .selectinload(User.startup)
                .selectinload(Startup.direct_members)
            )
            .filter(self.model.id == id)
        )
        return result.scalars().first()


interest = CRUDInterest(Interest) 