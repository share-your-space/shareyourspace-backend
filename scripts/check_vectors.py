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
from app.models.profile import UserProfile

async def check_user_vectors():
    emails_to_check = [
        "corp.admin@syscorp.com",   # User ID 7
        "admin@futuretech.ai",      # User ID 11
        "member.active@futuretech.ai", # User ID 12
        "freelancer.active@example.com" # User ID 15
    ]
    print("\nChecking profile vectors for specific users:")
    async with AsyncSessionLocal() as db:
        for email_str in emails_to_check:
            user_result = await db.execute(
                select(User)
                .options(selectinload(User.profile))
                .filter(User.email == email_str)
            )
            user = user_result.scalars().first()
            if user:
                if user.profile:
                    vector_status = "Exists" if user.profile.profile_vector is not None else "NULL"
                    print(f"- User: {user.email} (ID: {user.id}), Profile ID: {user.profile.id}, Vector: {vector_status}")
                    if vector_status == "Exists":
                        print(f"  Vector snippet: {user.profile.profile_vector[:5]}...") # Print first 5 elements
                else:
                    print(f"- User: {user.email} (ID: {user.id}), Profile: Does not exist")
            else:
                print(f"- User: {email_str}, Not found in DB")

async def main():
    await check_user_vectors()

if __name__ == "__main__":
    asyncio.run(main()) 