import asyncio
import logging

from faker import Faker
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

# Make sure paths are correct for script execution
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import AsyncSessionLocal, engine # Assuming engine might be needed for direct ops
from app.models.user import User
from app.security import get_password_hash

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

faker = Faker()

# --- Configuration ---
SYS_ADMIN_EMAIL = "admin@shareyourspace.com"
SYS_ADMIN_PASSWORD = "changeme"
NUM_FAKE_USERS_PER_TYPE = 3
DEFAULT_FAKE_USER_PASSWORD = "password123"

async def seed_data(db: AsyncSession):
    logger.info("Starting database seeding...")

    # --- Create SYS Admin ---
    try:
        hashed_admin_password = get_password_hash(SYS_ADMIN_PASSWORD)
        admin_user = User(
            email=SYS_ADMIN_EMAIL,
            hashed_password=hashed_admin_password,
            full_name="SYS Admin",
            role="SYS_ADMIN",
            status="ACTIVE",
            is_active=True
        )
        db.add(admin_user)
        await db.commit()
        logger.info(f"SYS Admin user '{SYS_ADMIN_EMAIL}' created.")
    except IntegrityError:
        await db.rollback()
        logger.warning(f"SYS Admin user '{SYS_ADMIN_EMAIL}' already exists. Skipping.")
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating SYS Admin user: {e}")

    # --- Create Sample Users ---
    logger.info("Creating sample users...")
    roles_statuses = {
        "CORP_ADMIN": "PENDING_ONBOARDING",
        "CORP_EMPLOYEE": "ACTIVE", # Assuming employees are added after corp is active
        "STARTUP_ADMIN": "WAITLISTED",
        "STARTUP_MEMBER": "WAITLISTED",
        "FREELANCER": "WAITLISTED",
    }
    hashed_default_password = get_password_hash(DEFAULT_FAKE_USER_PASSWORD)
    created_count = 0

    for role, status in roles_statuses.items():
        for i in range(NUM_FAKE_USERS_PER_TYPE):
            user_email = f"{role.lower()}_{i+1}@{faker.domain_name()}"
            try:
                user = User(
                    email=user_email,
                    hashed_password=hashed_default_password,
                    full_name=faker.name(),
                    role=role,
                    status=status,
                    is_active=(status == "ACTIVE") # Generally only active users are 'is_active'
                )
                db.add(user)
                await db.commit()
                created_count += 1
            except IntegrityError:
                await db.rollback()
                logger.warning(f"User with email '{user_email}' likely already exists. Skipping.")
            except Exception as e:
                await db.rollback()
                logger.error(f"Error creating fake user '{user_email}': {e}")

    logger.info(f"Created {created_count} sample users.")
    logger.info("Database seeding finished.")

async def main():
    logger.info("Initializing DB session for seeding.")
    db: AsyncSession = AsyncSessionLocal()
    try:
        await seed_data(db)
    finally:
        await db.close()
        # Dispose the engine if necessary for script cleanup
        if engine:
            await engine.dispose()
        logger.info("DB session closed.")

if __name__ == "__main__":
    # Apply migrations first (optional, but good practice before seeding)
    # print("Running DB migrations before seeding...")
    # os.system("poetry run alembic upgrade head")
    # print("Migrations complete.")

    asyncio.run(main()) 