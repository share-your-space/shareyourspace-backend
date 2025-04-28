import asyncio
# import logging # Removed logging import

from faker import Faker
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

# Make sure paths are correct for script execution
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import AsyncSessionLocal, engine # Assuming engine might be needed for direct ops
from app.models.user import User
from app.models.organization import Company, Startup # Import Company and Startup
from app.utils.security_utils import get_password_hash

# logging.basicConfig(level=logging.INFO) # Removed logging config
# logger = logging.getLogger(__name__) # Removed logger instance

faker = Faker()

# --- Configuration --- (Keep config vars if needed elsewhere, or remove)
# SYS_ADMIN_EMAIL = "admin@shareyourspace.com"
# SYS_ADMIN_PASSWORD = "changeme"
# NUM_FAKE_USERS_PER_TYPE = 3
# DEFAULT_FAKE_USER_PASSWORD = "password123"

async def seed_data():
    async with AsyncSessionLocal() as db:
        print("Seeding initial data...")

        # --- Seed SYS Admin ---
        sys_admin_email = "admin@shareyourspace.com"
        existing_sys_admin = (await db.execute(select(User).filter(User.email == sys_admin_email))).scalars().first()
        if not existing_sys_admin:
            sys_admin = User(
                email=sys_admin_email,
                hashed_password=get_password_hash("adminpassword"), # Use a secure default password
                full_name="SYS Admin",
                role="SYS_ADMIN",
                status="ACTIVE",
                is_active=True
            )
            db.add(sys_admin)
            print(f"Created SYS Admin: {sys_admin_email}")
        else:
            print(f"SYS Admin {sys_admin_email} already exists.")

        # --- Seed Company ---
        company_name = "Pixida Group"
        existing_company = (await db.execute(select(Company).filter(Company.name == company_name))).scalars().first()
        company = None
        if not existing_company:
            company = Company(
                name=company_name,
                industry_focus="Automotive & Technology Consulting",
                description="Driving digital transformation.",
                website="https://www.pixida.com/"
            )
            db.add(company)
            print(f"Created Company: {company_name}")
            await db.flush() # Flush to get company ID
        else:
            company = existing_company
            print(f"Company {company_name} already exists.")

        # --- Seed Startups ---
        startup1_name = "AI Innovations GmbH"
        existing_startup1 = (await db.execute(select(Startup).filter(Startup.name == startup1_name))).scalars().first()
        startup1 = None
        if not existing_startup1:
            startup1 = Startup(
                name=startup1_name,
                industry_focus="Artificial Intelligence",
                description="Developing cutting-edge AI solutions.",
                mission="To democratize AI access.",
                website="https://fake-ai-innovations.com"
            )
            db.add(startup1)
            print(f"Created Startup: {startup1_name}")
            await db.flush() # Flush to get startup ID
        else:
            startup1 = existing_startup1
            print(f"Startup {startup1_name} already exists.")

        startup2_name = "GreenTech Solutions"
        existing_startup2 = (await db.execute(select(Startup).filter(Startup.name == startup2_name))).scalars().first()
        if not existing_startup2:
            startup2 = Startup(
                name=startup2_name,
                industry_focus="Sustainability Tech",
                description="Building a greener future with technology.",
                website="https://fake-greentech.com"
            )
            db.add(startup2)
            print(f"Created Startup: {startup2_name}")
        else:
            print(f"Startup {startup2_name} already exists.")

        # --- Seed Sample Users (Modify to assign company/startup IDs) ---
        user_data = [
            {"role": "CORP_ADMIN", "status": "PENDING_ONBOARDING", "company_id": company.id if company else None, "startup_id": None},
            {"role": "CORP_EMPLOYEE", "status": "PENDING_ONBOARDING", "company_id": company.id if company else None, "startup_id": None},
            {"role": "STARTUP_ADMIN", "status": "WAITLISTED", "company_id": None, "startup_id": startup1.id if startup1 else None},
            {"role": "STARTUP_MEMBER", "status": "WAITLISTED", "company_id": None, "startup_id": startup1.id if startup1 else None},
            {"role": "FREELANCER", "status": "WAITLISTED", "company_id": None, "startup_id": None},
        ]

        for data in user_data:
            email = faker.unique.email()
            existing_user = (await db.execute(select(User).filter(User.email == email))).scalars().first()
            if not existing_user:
                user = User(
                    email=email,
                    hashed_password=get_password_hash(faker.password()), # Use faker.password() directly
                    full_name=faker.name(),
                    role=data["role"],
                    status=data["status"],
                    is_active=False, # Start inactive until verified/onboarded
                    company_id=data["company_id"],
                    startup_id=data["startup_id"]
                )
                db.add(user)
                print(f"Created {data['role']}: {email}")
            else:
                # Optionally update existing test users if needed
                pass

        try:
            await db.commit()
            print("Seeding complete.")
        except Exception as e:
            await db.rollback()
            print(f"Error during seeding commit: {e}")

async def main():
    # logger.info("Initializing DB session for seeding.") # Removed logger call
    print("Initializing DB session for seeding.")
    db: AsyncSession = AsyncSessionLocal()
    try:
        await seed_data()
    finally:
        await db.close()
        if engine:
            await engine.dispose()
        # logger.info("DB session closed.") # Removed logger call
        print("DB session closed.")

if __name__ == "__main__":
    # Apply migrations first (optional, but good practice before seeding)
    # print("Running DB migrations before seeding...")
    # os.system("poetry run alembic upgrade head")
    # print("Migrations complete.")

    asyncio.run(main()) 