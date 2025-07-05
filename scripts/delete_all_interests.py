import asyncio
import sys
import os
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete
import logging

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Adjust path for script execution
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import AsyncSessionLocal
from app.models.interest import Interest
from app.models.notification import Notification
from app.models.enums import NotificationType

async def delete_all_interests_and_notifications(db: AsyncSession):
    logger.info("Attempting to delete all interest requests and associated notifications...")
    try:
        # Delete notifications related to interest
        await db.execute(delete(Notification).where(
            Notification.type.in_([
                NotificationType.INTEREST_EXPRESSED,
                NotificationType.INTEREST_APPROVED
            ])
        ))
        logger.info("Successfully deleted interest-related notifications.")

        # Delete all interest records
        await db.execute(delete(Interest))
        logger.info("Successfully deleted all interest requests.")

        await db.commit()
        logger.info("Successfully committed all deletions.")
    except Exception as e:
        logger.error(f"Error during deletion process: {e}", exc_info=True)
        await db.rollback()
        logger.info("Database transaction rolled back due to error.")
    finally:
        logger.info("Deletion process finished.")

async def main():
    async with AsyncSessionLocal() as db_session:
        try:
            await delete_all_interests_and_notifications(db_session)
        except Exception as e:
            logger.critical(f"Critical error in main execution: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(main()) 