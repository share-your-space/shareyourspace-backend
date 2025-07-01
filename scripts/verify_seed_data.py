import asyncio
import sys
import os

# Ensure the app directory is in the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.db.session import AsyncSessionLocal
from app.models.user import User
from app.models.organization import Company, Startup
from app.models.space import SpaceNode
from app.models.profile import UserProfile

# Emails from test_credentials.txt
seeded_emails = [
    "sys.admin@shareyourspace.com",
    "corp.admin@syscorp.com",
    "pending.admin@innovate.com",
    "employee.active@syscorp.com",
    "employee.pending@syscorp.com",
    "admin@futuretech.ai",
    "member.active@futuretech.ai",
    "member.waitlisted@futuretech.ai",
    "admin@greengrow.com",
    "freelancer.active@example.com",
    "freelancer.waitlisted@example.com",
    "freelancer.pending@example.com",
]

async def verify_data(db: AsyncSession):
    print("--- Verifying Seeded User Data ---")
    for email in seeded_emails:
        print(f"\n--- Verifying User: {email} ---")
        user = await db.scalar(
            select(User)
            .options(
                selectinload(User.profile),
                selectinload(User.company),
                selectinload(User.startup),
                selectinload(User.space).selectinload(SpaceNode.admin) # Eager load space admin
            )
            .filter(User.email == email)
        )

        if not user:
            print(f"ERROR: User with email {email} NOT FOUND.")
            continue

        print(f"  User ID: {user.id}")
        print(f"  Full Name: {user.full_name}")
        print(f"  Role: {user.role}")
        print(f"  Status: {user.status}")
        print(f"  Is Active: {user.is_active}")
        print(f"  Created At: {user.created_at}")
        print(f"  Updated At: {user.updated_at}")

        if user.company:
            print(f"  Company: {user.company.name} (ID: {user.company_id})")
        elif user.company_id:
            print(f"  Company ID: {user.company_id} (Company details not loaded/found)")
        else:
            print("  Company: None")

        if user.startup:
            print(f"  Startup: {user.startup.name} (ID: {user.startup_id})")
        elif user.startup_id:
            print(f"  Startup ID: {user.startup_id} (Startup details not loaded/found)")
        else:
            print("  Startup: None")

        if user.space:
            print(f"  Space: {user.space.name} (ID: {user.space_id})")
            if user.space.admin:
                print(f"    Space Corporate Admin: {user.space.admin.full_name} (ID: {user.space.corporate_admin_id})")
            elif user.space.corporate_admin_id:
                 print(f"    Space Corporate Admin ID: {user.space.corporate_admin_id} (Admin details not loaded/found)")
            else:
                print("    Space Corporate Admin: None assigned")
        elif user.space_id:
            print(f"  Space ID: {user.space_id} (Space details not loaded/found)")
        else:
            print("  Space: None")
            
        if hasattr(user, 'managed_space_through_fk_association') and user.managed_space_through_fk_association:
            # This assumes you have a relationship set up like 'managed_space_through_fk_association'
            # on the User model that links to SpaceNode where User.id == SpaceNode.corporate_admin_id
            # Example: managed_space = relationship("SpaceNode", foreign_keys="[SpaceNode.corporate_admin_id]", back_populates="admin_user", uselist=False)
            # The seed script sets user.space_id for corp admin, and implies managed space.
            # Let's check if a SpaceNode lists THIS user as its corporate_admin_id.
            managed_space_node = await db.scalar(
                select(SpaceNode).filter(SpaceNode.corporate_admin_id == user.id)
            )
            if managed_space_node:
                 print(f"  Manages Space: {managed_space_node.name} (ID: {managed_space_node.id})")
            else:
                pass # Not explicitly managing a space directly as corporate_admin_id

        if user.profile:
            print("  Profile:")
            print(f"    Title: {user.profile.title}")
            print(f"    Bio (snippet): {user.profile.bio[:50]}..." if user.profile.bio else "N/A")
            print(f"    Contact Info Visibility: {user.profile.contact_info_visibility}")
            print(f"    Skills: {user.profile.skills_expertise}")
            print(f"    Profile Picture URL: {user.profile.profile_picture_url if user.profile.profile_picture_url else 'Not set'}")
            if hasattr(user.profile, 'profile_vector') and user.profile.profile_vector is not None:
                print(f"    Profile Vector: Exists (Length: {len(user.profile.profile_vector)})")
            else:
                print("    Profile Vector: Not found or None")
        else:
            print("  Profile: Not found for this user.")
        
        # Check if this user is a corporate_admin_id for any space (alternative check for managed space)
        if user.role == "CORP_ADMIN":
            directly_managed_spaces = await db.execute(
                select(SpaceNode.name, SpaceNode.id).filter(SpaceNode.corporate_admin_id == user.id)
            )
            managed_spaces_info = directly_managed_spaces.fetchall()
            if managed_spaces_info:
                for space_name, space_id_val in managed_spaces_info:
                    print(f"  Directly Manages Space (as corporate_admin_id): {space_name} (ID: {space_id_val})")


    print("\n--- Verification Complete ---")

async def main():
    print("Starting database verification script...")
    async with AsyncSessionLocal() as db:
        await verify_data(db)
    print("Database verification script finished.")

if __name__ == "__main__":
    asyncio.run(main()) 