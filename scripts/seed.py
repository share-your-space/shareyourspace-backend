import asyncio
# import logging # Removed logging import

from faker import Faker
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload # Added for potential eager loading if needed
from sqlalchemy import func, text # Added text for direct SQL execution if needed

# Make sure paths are correct for script execution
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import AsyncSessionLocal, engine # Assuming engine might be needed for direct ops
from app.models.user import User
from app.models.organization import Company, Startup # Import Company and Startup
from app.models.space import SpaceNode, Workstation # Added SpaceNode, Workstation
from app.schemas.space import WorkstationStatus # Added WorkstationStatus for workstation creation
from app.security import get_password_hash
# Add imports for profile and embedding generation
from app.crud import crud_user_profile # For updating profile and generating embeddings
from app.schemas.user_profile import UserProfileUpdate # For profile update schema
from app.models.profile import UserProfile # To create UserProfile object if needed
from app.crud.crud_user_profile import get_profile_by_user_id, create_profile_for_user, update_profile
from app.models.connection import Connection
from app.models.space import WorkstationAssignment
from app.models.notification import Notification
from app.models.chat import ChatMessage, ConversationParticipant, Conversation

# logging.basicConfig(level=logging.INFO) # Removed logging config
# logger = logging.getLogger(__name__) # Removed logger instance

faker = Faker()

# Store credentials for easy output
seeded_user_credentials = {}
DEFAULT_PASSWORD = "Password123!"

async def clear_all_data(db: AsyncSession):
    """Clears all relevant data for a fresh seed, respecting deletion order."""
    print("--- Clearing All Existing Test Data ---")

    # Order of deletion is critical to avoid foreign key constraint violations.
    # Start with tables that are "at the edge" of the dependency graph.
    print("Deleting junction/event tables...")
    # await db.execute(text("DELETE FROM message_reactions CASCADE;")) # If exists
    await db.execute(Notification.__table__.delete())
    await db.execute(Connection.__table__.delete())
    await db.execute(WorkstationAssignment.__table__.delete())
    await db.execute(ChatMessage.__table__.delete())
    await db.execute(ConversationParticipant.__table__.delete())
    await db.execute(Conversation.__table__.delete())
    await db.commit()

    # Clear UserProfile first as it has a FK to User
    print("Deleting UserProfile data...")
    await db.execute(UserProfile.__table__.delete())
    await db.commit()

    # Clear Workstations
    print("Deleting Workstation data...")
    await db.execute(Workstation.__table__.delete())
    await db.commit()
    
    # Before deleting Users, nullify FKs in SpaceNode that point to User
    print("Nullifying corporate_admin_id in SpaceNodes...")
    await db.execute(SpaceNode.__table__.update().values(corporate_admin_id=None))
    await db.commit()
    
    # Before deleting SpaceNodes, nullify space_id in Users table
    print("Nullifying space_id in Users table...")
    await db.execute(User.__table__.update().values(space_id=None))
    await db.commit()

    # Before deleting Users, nullify FKs in Startup that point to SpaceNode (if any direct, or handle via SpaceNode delete)
    # For now, assuming Startup deletion will cascade or SpaceNode deletion is handled before Startup if issues arise.
    # Similarly for Company.

    # Delete SpaceNodes
    print("Deleting SpaceNode data...")
    await db.execute(SpaceNode.__table__.delete())
    await db.commit()

    # Now, attempt to delete users. If any other tables reference User directly and
    # haven't been cleared or don't have CASCADE, this might fail.
    # The `User` model has various relationships (company, startup, space_id).
    # It's often easier to nullify these FKs on the User table before deleting the referenced entities
    # or ensure the referenced entities are deleted first if the FK is on User.

    # Let's try deleting Startups and Companies before Users who might reference them
    print("Deleting Startup data...")
    await db.execute(Startup.__table__.delete())
    await db.commit()

    print("Deleting Company data...")
    await db.execute(Company.__table__.delete())
    await db.commit()
    
    # Finally, delete Users
    print("Deleting User data...")
    await db.execute(User.__table__.delete())
    await db.commit()
    
    print("--- All specific data cleared successfully. ---")


async def create_user_with_profile(
    db: AsyncSession,
    email: str,
    full_name: str,
    role: str,
    status: str,
    is_active: bool,
    company_id: int = None,
    startup_id: int = None,
    space_id: int = None,
    profile_details: dict = None,
):
    """Creates a user, their profile, and generates embeddings."""
    user = await db.scalar(select(User).filter(User.email == email))
    if user:
        print(f"User {email} already exists. Skipping creation.")
        if email not in seeded_user_credentials:
            seeded_user_credentials[email] = DEFAULT_PASSWORD
        return user

    user = User(
        email=email,
        hashed_password=get_password_hash(DEFAULT_PASSWORD),
        full_name=full_name,
        role=role,
        status=status,
        is_active=is_active,
        company_id=company_id,
        startup_id=startup_id,
        space_id=space_id,
    )
    db.add(user)
    await db.flush()  # Get user.id

    print(f"Created User: {email} (Role: {role}, Status: {status})")
    seeded_user_credentials[email] = DEFAULT_PASSWORD

    # Create UserProfile
    default_profile_details = {
        "title": f"{role.replace('_', ' ').title()} at {faker.company() if role not in ['FREELANCER'] else 'Self-Employed'}",
        "bio": faker.paragraph(nb_sentences=3),
        "contact_info_visibility": "connections",
        "skills_expertise": [faker.job() for _ in range(faker.random_int(min=2, max=5))],
        "industry_focus": [faker.bs() for _ in range(faker.random_int(min=1, max=3))],
        "project_interests_goals": faker.sentence(nb_words=10),
        "collaboration_preferences": [faker.word() for _ in range(faker.random_int(min=1, max=3))],
        "tools_technologies": [faker.word() for _ in range(faker.random_int(min=2, max=5))],
        "linkedin_profile_url": f"https://linkedin.com/in/{email.split('@')[0]}"
    }
    if profile_details:
        default_profile_details.update(profile_details)

    profile_data = UserProfileUpdate(**default_profile_details)
    
    # This function should handle creating UserProfile if not exists and updating it, then generating embedding.
    # It needs the user object.
    try:
        print(f"Ensuring profile exists and then updating for {user.email} to generate embedding...")
        
        # 1. Get or Create Profile Object
        db_profile = await get_profile_by_user_id(db, user_id=user.id)
        if not db_profile:
            print(f"Profile not found for {user.email}, creating one.")
            # Pass the user object, not just user.id, if create_profile_for_user expects the full object
            db_profile = await create_profile_for_user(db, user=user) 
            if not db_profile:
                print(f"CRITICAL: Failed to create profile for {user.email}. Skipping embedding generation.")
                # Decide on error handling: return user or raise exception
                await db.flush() 
                return user

        # 2. Update the profile (which includes embedding generation)
        # The existing `update_profile` function in crud_user_profile.py handles embedding.
        updated_db_profile = await update_profile(db=db, db_obj=db_profile, obj_in=profile_data)
        
        if updated_db_profile and updated_db_profile.profile_vector is not None:
            print(f"Successfully updated profile and generated embedding for {user.email}")
        elif updated_db_profile:
            print(f"Profile updated for {user.email}, but embedding might be missing (check logs from crud_user_profile).")
        else:
            print(f"Profile update or embedding generation failed for {user.email} (update_profile returned None).")

    except Exception as e:
        print(f"Error during profile/embedding generation for {user.email}: {e}")
        # Decide if to rollback or continue; for seeding, we might want to continue other users.

    await db.flush() # Ensure all changes for this user are flushed before moving to next
    return user

async def seed_data():
    async with AsyncSessionLocal() as db:
        
        # Option 1: Clear all data for a completely fresh seed
        await clear_all_data(db)
        
        # Option 2: Comment out clear_all_data(db) if you want to add to existing data (less common for seeding)

        print("--- Seeding Initial Platform Data ---")
        seeded_user_credentials.clear()

        # 1. SYS Admin
        print("\n--- Creating SYS Admin ---")
        sys_admin_user = await create_user_with_profile(
            db,
            email="sys.admin@shareyourspace.com",
            full_name="Platform SYS Admin",
                role="SYS_ADMIN",
                status="ACTIVE",
            is_active=True,
            profile_details={"title": "Chief Platform Officer"}
        )

        # 2. Companies
        print("\n--- Creating Companies ---")
        company_syscorp = await db.scalar(select(Company).filter(Company.name == "SYSCorp Inc."))
        if not company_syscorp:
            company_syscorp = Company(
                name="SYSCorp Inc.",
                industry_focus="Global Technology Services",
                description="Leading the future of enterprise solutions.",
                website="https://syscorp.inc.example.com"
            )
            db.add(company_syscorp)
            await db.flush()
            print(f"Created Company: {company_syscorp.name}")
        else:
            print(f"Company {company_syscorp.name} already exists.")

        company_innovate = await db.scalar(select(Company).filter(Company.name == "Innovate Solutions Ltd."))
        if not company_innovate:
            company_innovate = Company(
                name="Innovate Solutions Ltd.",
                industry_focus="Creative Digital Agency",
                description="Crafting unique digital experiences.",
                website="https://innovate.ltd.example.com"
            )
            db.add(company_innovate)
            await db.flush()
            print(f"Created Company: {company_innovate.name}")
        else:
            print(f"Company {company_innovate.name} already exists.")

        # 3. Corporate Admins
        print("\n--- Creating Corporate Admins ---")
        corp_admin_syscorp = await create_user_with_profile(
            db,
            email="corp.admin@syscorp.com",
            full_name="Admin SYSCorp",
                role="CORP_ADMIN",
            status="ACTIVE", # This admin is active and will manage a space
                is_active=True,
            company_id=company_syscorp.id,
            profile_details={"title": "Head of Operations, SYSCorp"}
        )

        corp_admin_innovate_pending = await create_user_with_profile(
            db,
            email="pending.admin@innovate.com",
            full_name="Admin Innovate (Pending)",
            role="CORP_ADMIN",
            status="PENDING_ONBOARDING", # This admin needs SYS_ADMIN approval
            is_active=True, # PENDING_ONBOARDING users are active as per backend logic
            company_id=company_innovate.id,
            profile_details={"title": "Director of Innovation, Innovate Solutions"}
        )

        # 4. SpaceNodes & Workstations
        print("\n--- Creating SpaceNodes & Workstations ---")
        space_syscorp_alpha = None
        if corp_admin_syscorp: # Ensure the admin was created
            space_syscorp_alpha = await db.scalar(select(SpaceNode).filter(SpaceNode.name == "SYSCorp Hub Alpha"))
            if not space_syscorp_alpha:
                space_syscorp_alpha = SpaceNode(
                    name="SYSCorp Hub Alpha",
                    address=faker.address(),
                    corporate_admin_id=corp_admin_syscorp.id,
                    total_workstations=20,
                    company_id=company_syscorp.id # Link space to the company
                )
                db.add(space_syscorp_alpha)
                await db.flush()
                print(f"Created SpaceNode: {space_syscorp_alpha.name} managed by {corp_admin_syscorp.email}")

                # Update Corp Admin's space_id (current assigned space, if they work there too)
                # And their managed_space is implied by corporate_admin_id on SpaceNode
                corp_admin_syscorp.space_id = space_syscorp_alpha.id
                db.add(corp_admin_syscorp)
                await db.flush()


                for i in range(space_syscorp_alpha.total_workstations):
                    workstation = Workstation(
                        name=f"Alpha-{101+i}",
                        space_id=space_syscorp_alpha.id,
                        status=WorkstationStatus.AVAILABLE if i % 3 != 0 else WorkstationStatus.MAINTENANCE # Mix status
                    )
                    db.add(workstation)
                await db.flush()
                print(f"Added {space_syscorp_alpha.total_workstations} workstations to {space_syscorp_alpha.name}")
            else:
                print(f"SpaceNode {space_syscorp_alpha.name} already exists.")
        else:
            print("SYSCorp Admin not found, cannot create SYSCorp Hub Alpha.")
            
        # 5. Corporate Employees for SYSCorp Inc.
        print("\n--- Creating Corporate Employees (SYSCorp Inc.) ---")
        if company_syscorp and space_syscorp_alpha:
            employee_active_syscorp = await create_user_with_profile(
                db,
                email="employee.active@syscorp.com",
                full_name="Eva Employee (Active)",
                role="CORP_EMPLOYEE",
                status="ACTIVE",
                is_active=True,
                company_id=company_syscorp.id,
                space_id=space_syscorp_alpha.id, # Assigned to the hub
                profile_details={"title": "Senior Developer"}
            )
            employee_pending_syscorp = await create_user_with_profile(
                db,
                email="employee.pending@syscorp.com",
                full_name="Paul Pending (Verification)",
                role="CORP_EMPLOYEE",
                status="PENDING_VERIFICATION",
                is_active=False, # Not active until verified
                company_id=company_syscorp.id,
                # No space_id until active and assigned
                profile_details={"title": "Junior Analyst"}
            )
        else:
            print("SYSCorp company or space not available, skipping SYSCorp employee creation.")

        # 6. Startups
        print("\n--- Creating Startups ---")
        startup_futuretech = None
        if space_syscorp_alpha: # Assuming FutureTech AI is in SYSCorp Hub Alpha
            startup_futuretech = await db.scalar(select(Startup).filter(Startup.name == "FutureTech AI"))
            if not startup_futuretech:
                startup_futuretech = Startup(
                    name="FutureTech AI",
                    industry_focus="AI Solutions",
                    description="Pioneering next-gen AI applications.",
                    mission="To make AI accessible and beneficial.",
                    website="https://futuretech.ai.example.com",
                    space_id=space_syscorp_alpha.id # Part of SYSCorp Hub Alpha
                )
                db.add(startup_futuretech)
                await db.flush()
                print(f"Created Startup: {startup_futuretech.name} in space {space_syscorp_alpha.name}")
            else:
                print(f"Startup {startup_futuretech.name} already exists.")
        else:
            print("SYSCorp Hub Alpha not available, cannot create FutureTech AI startup assigned to it.")

        startup_greengrow = await db.scalar(select(Startup).filter(Startup.name == "GreenGrow Ventures"))
        if not startup_greengrow:
            startup_greengrow = Startup(
                name="GreenGrow Ventures",
                industry_focus="Sustainable Technology",
                description="Investing in a greener tomorrow.",
                mission="To foster environmental innovation.",
                website="https://greengrow.example.com"
                # No space_id initially, they are waitlisted/independent
            )
            db.add(startup_greengrow)
            await db.flush()
            print(f"Created Startup: {startup_greengrow.name} (independent/waitlisted)")
        else:
            print(f"Startup {startup_greengrow.name} already exists.")

        # 7. Startup Admins & Members
        print("\n--- Creating Startup Admins & Members ---")
        if startup_futuretech and space_syscorp_alpha:
            sa_futuretech = await create_user_with_profile(
                db,
                email="admin@futuretech.ai",
                full_name="Alex Admin (FutureTech)",
                role="STARTUP_ADMIN",
                status="ACTIVE",
                is_active=True,
                startup_id=startup_futuretech.id,
                space_id=space_syscorp_alpha.id, # Active in the hub
                profile_details={"title": "CEO, FutureTech AI"}
            )
            sm_active_futuretech = await create_user_with_profile(
                db,
                email="member.active@futuretech.ai",
                full_name="Mia Member (FutureTech Active)",
                role="STARTUP_MEMBER",
                status="ACTIVE",
                    is_active=True,
                startup_id=startup_futuretech.id,
                space_id=space_syscorp_alpha.id, # Active in the hub
                profile_details={"title": "Lead Engineer, FutureTech AI"}
            )
            sm_waitlisted_futuretech = await create_user_with_profile(
                db,
                email="member.waitlisted@futuretech.ai",
                full_name="Walter Waitlist (FutureTech)",
                role="STARTUP_MEMBER",
                status="WAITLISTED", # Needs approval for space access
                is_active=True, # Email verified, but waitlisted for space
                startup_id=startup_futuretech.id,
                # No space_id yet
                profile_details={"title": "Product Designer, FutureTech AI"}
            )
        else:
            print("FutureTech AI startup or SYSCorp Hub Alpha not available, skipping FutureTech AI user creation.")

        if startup_greengrow:
            sa_greengrow_waitlisted = await create_user_with_profile(
                db,
                email="admin@greengrow.com",
                full_name="Grace Admin (GreenGrow)",
                role="STARTUP_ADMIN",
                status="WAITLISTED", # Startup itself is waitlisted for a space
                is_active=True, # Email verified
                startup_id=startup_greengrow.id,
                # No space_id yet
                profile_details={"title": "Founder, GreenGrow Ventures"}
            )
        else:
            print("GreenGrow Ventures startup not available, skipping GreenGrow admin creation.")

        # 8. Freelancers
        print("\n--- Creating Freelancers ---")
        freelancer_active = await create_user_with_profile(
            db,
            email="freelancer.active@example.com",
            full_name="Frank Freelancer (Active)",
            role="FREELANCER",
            status="ACTIVE",
            is_active=True,
            space_id=space_syscorp_alpha.id if space_syscorp_alpha else None, # Active in the hub
            profile_details={"title": "UX Consultant", "skills_expertise": ["UX Design", "UI Prototyping", "User Research", "Figma"]}
        )
        freelancer_waitlisted = await create_user_with_profile(
            db,
            email="freelancer.waitlisted@example.com",
            full_name="Wendy Waitlist (Freelancer)",
            role="FREELANCER",
            status="WAITLISTED",
            is_active=True, # Email verified
            profile_details={"title": "Content Strategist", "skills_expertise": ["SEO Writing", "Copywriting", "Content Marketing"]}
        )
        freelancer_pending_ver = await create_user_with_profile(
            db,
            email="freelancer.pending@example.com",
            full_name="Peter Pending (Freelancer Verification)",
            role="FREELANCER",
            status="PENDING_VERIFICATION",
            is_active=False,
            profile_details={"title": "Backend Developer", "bio": "Awaiting email verification to join the platform."}
        )

        # Commit all pending changes
        await db.commit()
    print("\n--- Seeding Completed ---")

    print("\n--- Seeded User Credentials (Password for all: Password123!) ---")
    for email, password in seeded_user_credentials.items():
        print(f"Email: {email}, Password: {password}")

async def main():
    print("Starting database seed process...")
    await seed_data()
    print("Database seed process finished.")

if __name__ == "__main__":
    # Important: For a truly clean seed, it's best to reset the database volume:
    # 1. docker-compose down -v  (The -v removes the volume)
    # 2. docker-compose up -d db (Restart only the DB)
    # 3. Wait for DB to be ready
    # 4. poetry run alembic upgrade head (Apply migrations to the fresh DB)
    # 5. poetry run python scripts/seed.py (Run this script)
    #
    # The `clear_all_data` function is an alternative if you cannot do a full volume reset,
    # but it might be less reliable for complex schemas or if new relations are added without updating it.

    # print("Optional: Running DB migrations before seeding if you haven't done so...")
    # os.system("poetry run alembic upgrade head") # Best to do this manually after db reset
    # print("Migrations complete (if run).")

    asyncio.run(main()) 