from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional

from app.models.space import SpaceNode
from app.schemas.admin import SpaceCreate


async def create_space(db: AsyncSession, *, obj_in: SpaceCreate) -> SpaceNode:
    """Creates a new SpaceNode in the database."""
    db_obj = SpaceNode(
        name=obj_in.name,
        location_description=obj_in.location_description,
        corporate_admin_id=obj_in.corporate_admin_id,
        total_workstations=obj_in.total_workstations
    )
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj

async def get_space(db: AsyncSession, space_id: int) -> Optional[SpaceNode]:
    """Gets a specific SpaceNode by its ID."""
    result = await db.execute(select(SpaceNode).filter(SpaceNode.id == space_id))
    return result.scalars().first()

async def get_spaces(db: AsyncSession, skip: int = 0, limit: int = 100) -> List[SpaceNode]:
    """Gets a list of SpaceNodes."""
    result = await db.execute(select(SpaceNode).offset(skip).limit(limit))
    return result.scalars().all() 