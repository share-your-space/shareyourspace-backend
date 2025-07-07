import asyncio
import sys
import os
import logging

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db.session import AsyncSessionLocal
from app.models.user import User, UserRole
# Import the function from the other script
from scripts.delete_user_by_email import delete_user_and_associated_data

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def delete_all_startups(db: AsyncSession):
    """
    Deletes all startups by finding all STARTUP_ADMINs and deleting them,
    which triggers the deletion of the startup and its members.
    """
    logger.info("Starting deletion of all startups and their members...")

    # We fetch one admin at a time and delete them. The delete_user_and_associated_data
    # function is recursive and will handle the entire startup's deletion.
    # Looping like this prevents issues with modifying the list we are iterating over.
    while True:
        stmt = select(User).where(User.role == UserRole.STARTUP_ADMIN).limit(1)
        result = await db.execute(stmt)
        admin = result.scalars().first()

        if not admin:
            logger.info("No more startup admins found. All startups should be deleted.")
            break

        logger.info(f"--- Deleting startup admin: {admin.email} (User ID: {admin.id}) ---")
        # This function will handle deleting the user, which in turn will delete the startup and its members
        await delete_user_and_associated_data(db, admin.email)
        logger.info(f"--- Finished deletion process for startup admin: {admin.email} ---")
    
    logger.info("All startups and associated members have been processed.")

    logger.info("Now deleting all waitlisted freelancers...")
    while True:
        stmt = select(User).where(User.role == UserRole.FREELANCER, User.status == 'WAITLISTED').limit(1)
        result = await db.execute(stmt)
        freelancer = result.scalars().first()

        if not freelancer:
            logger.info("No more waitlisted freelancers found.")
            break

        logger.info(f"--- Deleting freelancer: {freelancer.email} (User ID: {freelancer.id}) ---")
        await delete_user_and_associated_data(db, freelancer.email)
        logger.info(f"--- Finished deletion process for freelancer: {freelancer.email} ---")

    logger.info("All waitlisted freelancers have been processed.")


async def main():
    logger.info("Connecting to the database to delete all startups.")
    async with AsyncSessionLocal() as db_session:
        await delete_all_startups(db_session)

if __name__ == "__main__":
    logger.info("Running script to delete all startups.")
    asyncio.run(main()) 