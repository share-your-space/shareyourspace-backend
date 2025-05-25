import asyncio
# import logging # Removed logging import

from faker import Faker
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload # Added for potential eager loading if needed

# Make sure paths are correct for script execution
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import AsyncSessionLocal, engine # Assuming engine might be needed for direct ops
from app.models.user import User
from app.models.organization import Company, Startup # Import Company and Startup
from app.models.space import SpaceNode, Workstation # Added SpaceNode, Workstation
from app.schemas.space import WorkstationStatus # Added WorkstationStatus for workstation creation
from app.utils.security_utils import get_password_hash
# Add imports for profile and embedding generation
from app.crud import crud_user_profile # For updating profile and generating embeddings
from app.schemas.user_profile import UserProfileUpdate # For profile update schema
from app.models.profile import UserProfile # To create UserProfile object if needed

# logging.basicConfig(level=logging.INFO) # Removed logging config
# logger = logging.getLogger(__name__) # Removed logger instance

faker = Faker()

# Store credentials for easy output
test_user_credentials = {}

async def clear_specific_data(db: AsyncSession):
    print("Clearing specific existing test data (Users, Startups, Companies, SpaceNodes, Workstations)...")
    
    # Order of deletion matters to avoid foreign key constraint errors
    # Start with models that are referenced by others, or use cascade deletes if set up

    # If WorkstationAssignment exists and references users/workstations, clear it first.
    # from app.models.space import WorkstationAssignment # Assuming this model exists
    # await db.execute(WorkstationAssignment.__table__.delete()) 

    await db.execute(Workstation.__table__.delete())
    # Users who might be corporate_admin in SpaceNode or have space_id need careful handling
    # Easiest might be to temporarily nullify FKs or delete dependent SpaceNodes first.
    
    # Nullify corporate_admin_id in SpaceNodes before deleting users to avoid FK violation
    await db.execute(SpaceNode.__table__.update().values(corporate_admin_id=None))
    await db.commit() # Commit this change first

    # Nullify space_id and company_id and startup_id in Users
    await db.execute(User.__table__.update().values(space_id=None, company_id=None, startup_id=None))
    await db.commit() # Commit this change

    await db.execute(SpaceNode.__table__.delete())
    # Delete users, ensuring SYS_ADMIN is handled (e.g., by filtering or specific logic if it should persist)
    # For a full reset, delete all users except perhaps a superuser if needed.
    # Or, for specific test users, use their emails for targeted deletion.
    # For now, deleting all users for a clean slate, assuming SYS_ADMIN will be recreated.
    await db.execute(User.__table__.delete().where(User.email != "admin@shareyourspace.com")) # Keep SYS_ADMIN for now or recreate
    await db.execute(Startup.__table__.delete())
    await db.execute(Company.__table__.delete())
    
    await db.commit()
    print("Specific data cleared.")


async def seed_data():
    async with AsyncSessionLocal() as db:
        # It's often better to run this on a completely fresh DB (docker-compose down -v)
        # But adding a clear function for more targeted resets if needed.
        # await clear_specific_data(db) # Uncomment if you want the script to clear data

        print("Seeding initial data...")
        test_user_credentials.clear() # Clear any previous credentials

        # --- Seed SYS Admin (Essential) ---
        sys_admin_email = "admin@shareyourspace.com"
        sys_admin_password = "adminpassword"
        existing_sys_admin = (await db.execute(select(User).filter(User.email == sys_admin_email))).scalars().first()
        if not existing_sys_admin:
            sys_admin = User(
                email=sys_admin_email,
                hashed_password=get_password_hash(sys_admin_password),
                full_name="SYS Admin",
                role="SYS_ADMIN",
                status="ACTIVE",
                is_active=True
            )
            db.add(sys_admin)
            print(f"Created SYS Admin: {sys_admin_email}, Password: {sys_admin_password}")
            test_user_credentials[sys_admin_email] = sys_admin_password 
        else:
            print(f"SYS Admin {sys_admin_email} already exists.")
            # Ensure password is known if admin already exists and we didn't set it here
            if sys_admin_email not in test_user_credentials:
                 test_user_credentials[sys_admin_email] = sys_admin_password # Store for output

        # --- Seed Company: Pixida Group ---
        pixida_company_name = "Pixida Group"
        company_pixida = (await db.execute(select(Company).filter(Company.name == pixida_company_name))).scalars().first()
        if not company_pixida:
            company_pixida = Company(
                name=pixida_company_name,
                industry_focus="Automotive & Technology Consulting",
                description="Driving digital transformation.",
                website="https://www.pixida.com/"
            )
            db.add(company_pixida)
            print(f"Created Company: {pixida_company_name}")
            await db.flush()
        else:
            print(f"Company {pixida_company_name} already exists.")

        # --- Seed Startup: AI Innovations GmbH ---
        ai_startup_name = "AI Innovations GmbH"
        startup_ai = (await db.execute(select(Startup).filter(Startup.name == ai_startup_name))).scalars().first()
        if not startup_ai:
            startup_ai = Startup(
                name=ai_startup_name,
                industry_focus="Artificial Intelligence",
                description="Developing cutting-edge AI solutions.",
                mission="To democratize AI access.",
                website="https://fake-ai-innovations.com"
            )
            db.add(startup_ai)
            print(f"Created Startup: {ai_startup_name}")
            await db.flush()
        else:
            print(f"Startup {ai_startup_name} already exists.")

        # --- Seed Startup: GreenTech Solutions ---
        greentech_startup_name = "GreenTech Solutions"
        startup_greentech = (await db.execute(select(Startup).filter(Startup.name == greentech_startup_name))).scalars().first()
        if not startup_greentech:
            startup_greentech = Startup(
                name=greentech_startup_name,
                industry_focus="Sustainability Tech",
                description="Building a greener future with technology.",
                website="https://fake-greentech.com"
            )
            db.add(startup_greentech)
            print(f"Created Startup: {greentech_startup_name}")
            await db.flush()
        else:
            print(f"Startup {greentech_startup_name} already exists.")


        # --- Define Test Users ---
        users_to_create = [
            {
                "email": "corp.admin@pixida.com", "password": "Password123!", "full_name": "Corporate Admin Pat",
                "role": "CORP_ADMIN", "status": "ACTIVE", "company": company_pixida, "startup": None
            },
            {
                "email": "startup.admin@aiinnovations.com", "password": "Password123!", "full_name": "Startup Admin Sam",
                "role": "STARTUP_ADMIN", "status": "ACTIVE", "company": None, "startup": startup_ai
            },
            {
                "email": "startup.member@aiinnovations.com", "password": "Password123!", "full_name": "Startup Member Max",
                "role": "STARTUP_MEMBER", "status": "ACTIVE", "company": None, "startup": startup_ai
            },
            {
                "email": "freelancer.frank@example.com", "password": "Password123!", "full_name": "Freelancer Frank",
                "role": "FREELANCER", "status": "ACTIVE", "company": None, "startup": None # Freelancers might not be tied to a startup initially
            }
        ]

        created_users = {} # To store created user objects

        for user_data in users_to_create:
            existing_user = (await db.execute(select(User).filter(User.email == user_data["email"]))).scalars().first()
            if not existing_user:
                new_user = User(
                    email=user_data["email"],
                    hashed_password=get_password_hash(user_data["password"]),
                    full_name=user_data["full_name"],
                    role=user_data["role"],
                    status=user_data["status"],
                    is_active=True,
                    company_id=user_data["company"].id if user_data["company"] else None,
                    startup_id=user_data["startup"].id if user_data["startup"] else None
                )
                db.add(new_user)
                await db.flush() # Get ID for new_user
                created_users[user_data["email"]] = new_user
                print(f"Created {user_data['role']}: {user_data['email']}, Password: {user_data['password']}")
                test_user_credentials[user_data["email"]] = user_data["password"]
            else:
                created_users[user_data["email"]] = existing_user # Use existing if found
                print(f"User {user_data['email']} already exists.")
                if user_data["email"] not in test_user_credentials: # Store password if not already stored
                    test_user_credentials[user_data["email"]] = user_data["password"]

            # --- Populate Profile and Generate Embedding ---
            user_object_for_profile = created_users.get(user_data["email"])
            if user_object_for_profile:
                profile = await crud_user_profile.get_profile_by_user_id(db, user_id=user_object_for_profile.id)
                if not profile:
                    profile = await crud_user_profile.create_profile_for_user(db, user_id=user_object_for_profile.id)
                    print(f"Created empty profile for user {user_object_for_profile.email}")

                # Define profile data - make Corp Admin and Freelancer very similar to Startup Admin for testing
                startup_admin_profile_template = {
                    "bio": "A passionate professional working with a focus on driving innovation and collaboration in cutting-edge technology sectors.",
                    "skills_expertise": ["Collaboration", "Communication", "Python", "FastAPI", "Docker", "React", "Management", "Strategy", "Operations", "AI", "Cloud Computing"],
                    "industry_focus": ["Artificial Intelligence", "Technology", "Software Development"],
                    "project_interests_goals": "Interested in projects related to AI, cloud solutions, and scalable web applications.",
                    "collaboration_preferences": ["Remote Work", "Team Projects", "Agile Development"],
                    "tools_technologies": ["Python", "FastAPI", "Docker", "React", "Kubernetes", "AWS", "GCP"]
                }

                if user_data["email"] == "corp.admin@pixida.com":
                    profile_details = startup_admin_profile_template.copy()
                    profile_details["title"] = "Corporate Admin at Pixida" # Keep title distinct
                    profile_details["skills_expertise"].append("Corporate Governance") # Add one unique skill
                    print(f"Seeding VERY SIMILAR profile for {user_data['email']}")
                elif user_data["email"] == "freelancer.frank@example.com":
                    profile_details = startup_admin_profile_template.copy()
                    profile_details["title"] = "Independent Tech Consultant & Freelancer" # Keep title distinct
                    profile_details["skills_expertise"].append("Client Management") # Add one unique skill
                    print(f"Seeding VERY SIMILAR profile for {user_data['email']}")
                elif user_data["email"] == "startup.admin@aiinnovations.com":
                    profile_details = startup_admin_profile_template.copy()
                    profile_details["title"] = "Startup Admin at AI Innovations GmbH"
                    print(f"Seeding base profile for {user_data['email']}")
                else: # For startup.member@aiinnovations.com or any others
                    profile_details = {
                        "title": f"{user_data['role'].replace('_', ' ').title()} at {user_data['startup'].name if user_data['startup'] else 'ShareYourSpace'}",
                        "bio": f"A team member at {user_data['startup'].name if user_data['startup'] else 'the company'}.",
                        "skills_expertise": ["Teamwork", "Communication", faker.job()],
                        "industry_focus": [user_data['startup'].industry_focus if user_data['startup'] else "Technology"],
                        "project_interests_goals": f"Contributing to projects at {user_data['startup'].name if user_data['startup'] else 'the company'}.",
                        "collaboration_preferences": ["Team Projects"],
                        "tools_technologies": ["Python", "React"]
                    }
                    print(f"Seeding generic member profile for {user_data['email']}")
                
                profile_update_schema = UserProfileUpdate(**profile_details)
                print(f"PROFILE_UPDATE_SCHEMA for {user_data['email']}: {profile_update_schema.model_dump_json(indent=2)}") # Print the schema
                
                try:
                    print(f"SEED.PY: ---- BEFORE CALLING update_profile for {user_object_for_profile.email} ----")
                    updated_profile = await crud_user_profile.update_profile(
                        db=db, 
                        db_obj=profile, 
                        obj_in=profile_update_schema
                    )
                    print(f"SEED.PY: ---- AFTER CALLING update_profile for {user_object_for_profile.email} ----")

                    if updated_profile.profile_vector is not None: # Check if the attribute is not None
                        print(f"Successfully generated and saved profile vector for {user_object_for_profile.email}.")
                    else:
                        print(f"Profile vector NOT generated for {user_object_for_profile.email} (check logs in crud_user_profile).\nPossible error during embedding generation or data too sparse.")
                except Exception as e:
                    print(f"Error updating profile/generating embedding for {user_object_for_profile.email}: {e}")
                    # Add more detailed error logging if needed, e.g., import traceback; traceback.print_exc()
            # --- End Profile Population ---


        # --- Seed SpaceNode: Pixida Munich Office ---
        # Ensure the corp_admin_user is available
        corp_admin_user_object = created_users.get("corp.admin@pixida.com")
        if not corp_admin_user_object:
            # This should not happen if user creation was successful
            # Fetch from DB as a fallback if it existed previously and wasn't in created_users
            corp_admin_user_object = (await db.execute(select(User).filter(User.email == "corp.admin@pixida.com"))).scalars().first()
            if not corp_admin_user_object:
                 print("Critical error: Corporate Admin user not found, cannot create SpaceNode correctly.")
                 await db.rollback()
                 return # Stop seeding

        space_name = "Pixida Munich Central"
        space_node = (await db.execute(select(SpaceNode).filter(SpaceNode.name == space_name))).scalars().first()
        if not space_node:
            space_node = SpaceNode(
                name=space_name,
                address="123 Tech Street, Munich",
                company_id=company_pixida.id if company_pixida else None,
                corporate_admin_id=corp_admin_user_object.id # Link to the Corp Admin
            )
            db.add(space_node)
            await db.flush() # Get ID for space_node
            print(f"Created SpaceNode: {space_name} managed by {corp_admin_user_object.email}")
        else:
            # If space exists, ensure its corporate_admin_id is correctly set (e.g. if script is re-run)
            if space_node.corporate_admin_id != corp_admin_user_object.id:
                space_node.corporate_admin_id = corp_admin_user_object.id
                print(f"Updated SpaceNode {space_name} to be managed by {corp_admin_user_object.email}")
            print(f"SpaceNode {space_name} already exists.")

        # --- Assign Space to Users ---
        # All defined test users (except SYS_ADMIN) will belong to this space
        user_emails_for_space = [
            "corp.admin@pixida.com", 
            "startup.admin@aiinnovations.com",
            "startup.member@aiinnovations.com",
            "freelancer.frank@example.com"
        ]
        for email in user_emails_for_space:
            user_to_update = created_users.get(email)
            if user_to_update and space_node:
                if user_to_update.space_id != space_node.id:
                    user_to_update.space_id = space_node.id
                    print(f"Assigned Space '{space_node.name}' to user {email}")
            elif not user_to_update:
                print(f"Warning: User {email} not found in created_users for space assignment.")
            elif not space_node:
                 print(f"Warning: SpaceNode not available for assigning to user {email}")


        # --- Seed Workstations for the SpaceNode ---
        if space_node:
            num_workstations = 5
            for i in range(1, num_workstations + 1):
                workstation_name = f"Workstation {i:03}"
                existing_workstation = (await db.execute(
                    select(Workstation).filter(Workstation.name == workstation_name, Workstation.space_id == space_node.id)
                )).scalars().first()
                
                if not existing_workstation:
                    workstation = Workstation(
                        name=workstation_name,
                        space_id=space_node.id,
                        status=WorkstationStatus.AVAILABLE # Default status
                    )
                    db.add(workstation)
                    print(f"Created Workstation: {workstation_name} in {space_node.name}")
                else:
                    print(f"Workstation {workstation_name} in {space_node.name} already exists.")
        else:
            print("SpaceNode not available, skipping workstation creation.")
        
        # --- Remove old generic user seeding logic ---
        # (The section with `user_data` list and faker.unique.email() has been replaced)

        try:
            await db.commit()
            print("\n--- Seeding Complete ---")
            print("Created/Ensured the following test user credentials:")
            for email, password in test_user_credentials.items():
                print(f"  Email: {email}, Password: {password}")
            print("--- Please save these credentials securely. ---")

        except IntegrityError as e: # Catch specific IntegrityError
            await db.rollback()
            print(f"Error during seeding commit (IntegrityError): {e.orig}") # .orig can give more DB-specific error info
            print("This might be due to unique constraints or foreign key issues if data wasn't cleared properly or has unexpected existing IDs.")
        except Exception as e:
            await db.rollback()
            print(f"Error during seeding commit: {e}")

async def main():
    # logger.info("Initializing DB session for seeding.") # Removed logger call
    print("Initializing DB session for seeding.")
    # db: AsyncSession = AsyncSessionLocal() # Session is managed within seed_data
    try:
        await seed_data()
    finally:
        # await db.close() # Session is managed within seed_data
        if engine: # Ensure engine is not None before disposing
            await engine.dispose()
        # logger.info("DB session closed.") # Removed logger call
        print("DB session closed and engine disposed.")

if __name__ == "__main__":
    # Important: For a truly clean seed, it's best to reset the database volume:
    # 1. docker-compose down -v  (The -v removes the volume)
    # 2. docker-compose up -d db (Restart only the DB)
    # 3. Wait for DB to be ready
    # 4. poetry run alembic upgrade head (Apply migrations to the fresh DB)
    # 5. poetry run python scripts/seed.py (Run this script)
    #
    # The `clear_specific_data` function is an alternative if you cannot do a full volume reset,
    # but it might be less reliable for complex schemas or if new relations are added without updating it.

    # print("Optional: Running DB migrations before seeding if you haven't done so...")
    # os.system("poetry run alembic upgrade head") # Best to do this manually after db reset
    # print("Migrations complete (if run).")

    asyncio.run(main()) 