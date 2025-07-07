import asyncio
import sys
import os
import logging

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete

from app.db.session import AsyncSessionLocal
from app.models.organization import Startup

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def delete_startup_by_id(db: AsyncSession, startup_id: int):
    logger.info(f"Attempting to delete startup with ID: {startup_id}")
    try:
        delete_stmt = delete(Startup).where(Startup.id == startup_id)
        result = await db.execute(delete_stmt)
        await db.commit()
        if result.rowcount > 0:
            logger.info(f"Successfully deleted startup with ID: {startup_id}")
        else:
            logger.warning(f"Startup with ID: {startup_id} not found.")
    except Exception as e:
        logger.error(f"Error deleting startup: {e}", exc_info=True)
        await db.rollback()

async def main():
    if len(sys.argv) < 2:
        logger.error("Usage: python scripts/delete_startup_by_id.py <startup_id>")
        return
        
    try:
        startup_id_to_delete = int(sys.argv[1])
    except ValueError:
        logger.error("Invalid startup_id provided. Must be an integer.")
        return

    async with AsyncSessionLocal() as db_session:
        await delete_startup_by_id(db_session, startup_id_to_delete)

if __name__ == "__main__":
    asyncio.run(main()) 