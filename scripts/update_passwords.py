import asyncio
import sys
import os

# Ensure correct paths for script execution
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db.session import AsyncSessionLocal
from app.models.user import User
from app.security import get_password_hash

NEW_PASSWORD = "Password123!"

async def update_all_user_passwords():
    async with AsyncSessionLocal() as db:
        print(f"Attempting to update passwords for all users to: {NEW_PASSWORD}")

        result = await db.execute(select(User))
        users = result.scalars().all()

        if not users:
            print("No users found in the database.")
            return

        updated_count = 0
        for user in users:
            try:
                user.hashed_password = get_password_hash(NEW_PASSWORD)
                db.add(user)
                updated_count += 1
                print(f"Password updated for user: {user.email} (ID: {user.id})")
            except Exception as e:
                print(f"Error updating password for user {user.email} (ID: {user.id}): {e}")

        try:
            await db.commit()
            print(f"Successfully updated passwords for {updated_count} users.")
        except Exception as e:
            print(f"Error committing changes to the database: {e}")
            await db.rollback()
            print("Rolled back database changes due to commit error.")


async def main():
    print("Starting password update script...")
    await update_all_user_passwords()
    print("Password update script finished.")

if __name__ == "__main__":
    asyncio.run(main()) 