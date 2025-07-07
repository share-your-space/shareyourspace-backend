import asyncio
import sys
import os
import logging
import argparse

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import delete
from sqlalchemy.orm import selectinload

from app.db.session import AsyncSessionLocal
from app.models.user import User, UserRole
from app.models.organization import Startup, Company

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def delete_entity_by_email(db: AsyncSession, email: str):
    """
    Deletes a user by email. If the user is a STARTUP_ADMIN or CORP_ADMIN,
    it deletes the entire organization as well.
    """
    logger.info(f"Attempting to delete entity associated with email: {email}")

    stmt = select(User).options(
        selectinload(User.startup),
        selectinload(User.company)
    ).where(User.email == email)
    
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        logger.warning(f"No user found with email: {email}")
        return

    try:
        if user.role == UserRole.STARTUP_ADMIN and user.startup:
            startup_id = user.startup.id
            logger.info(f"User {email} is admin of startup '{user.startup.name}' (ID: {startup_id}). Deleting entire startup...")
            await db.execute(delete(Startup).where(Startup.id == startup_id))
            logger.info(f"Startup {startup_id} and all its members deleted via cascade.")
        
        elif user.role == UserRole.CORP_ADMIN and user.company:
            company_id = user.company.id
            logger.info(f"User {email} is admin of company '{user.company.name}' (ID: {company_id}). Deleting entire company...")
            await db.execute(delete(Company).where(Company.id == company_id))
            logger.info(f"Company {company_id} and all its employees/spaces deleted via cascade.")

        else:
            logger.info(f"User {email} is not an admin of an organization. Deleting user only...")
            await db.execute(delete(User).where(User.id == user.id))
            logger.info(f"User {email} deleted.")

        await db.commit()
        logger.info(f"Successfully committed deletions for email {email}.")

    except Exception as e:
        logger.error(f"An error occurred during deletion for {email}: {e}", exc_info=True)
        await db.rollback()
        logger.info("Transaction rolled back.")

async def main():
    parser = argparse.ArgumentParser(description="Delete a user and their associated organization if they are an admin.")
    parser.add_argument("--email", type=str, required=True, help="The email of the user to delete.")
    args = parser.parse_args()

    async with AsyncSessionLocal() as db_session:
        await delete_entity_by_email(db_session, args.email)

if __name__ == "__main__":
    asyncio.run(main()) 