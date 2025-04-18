# test_db_connection.py
import asyncio
import os
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.sql import text
import sys

async def test_connection():
    load_dotenv()
    db_url = os.getenv("DATABASE_URL")

    if not db_url:
        print("❌ ERROR: DATABASE_URL not found in .env file.")
        sys.exit(1)

    if not db_url.startswith("postgresql+asyncpg://"):
            print("⚠️ WARNING: DATABASE_URL does not use asyncpg driver. Ensure it starts with 'postgresql+asyncpg://'")
            # Attempt connection anyway, but it might fail depending on installed drivers
            # Or exit:
            # sys.exit(1)


    print(f"Attempting to connect to: {db_url.split('@')[1]}...") # Hide credentials

    engine = None
    try:
        # Adjust pool settings for a quick test
        engine = create_async_engine(db_url, pool_size=1, max_overflow=0, pool_timeout=5)
        async with engine.connect() as connection:
            print("✅ Database connection successful!")

            # Test pgvector extension
            try:
                result = await connection.execute(text("SELECT extname FROM pg_extension WHERE extname = 'vector';"))
                vector_extension = result.scalar_one_or_none()
                if vector_extension:
                    print("✅ pgvector extension is enabled.")
                else:
                    # Attempt to enable it (might fail if flag wasn't set correctly in Cloud SQL)
                    print("🟡 pgvector extension not found, attempting to enable...")
                    await connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
                    # Re-check
                    result = await connection.execute(text("SELECT extname FROM pg_extension WHERE extname = 'vector';"))
                    if result.scalar_one_or_none():
                            print("✅ pgvector extension successfully enabled now.")
                    else:
                            print("❌ ERROR: Failed to find or enable pgvector extension. Check Cloud SQL flags and permissions.")

            except Exception as e:
                print(f"❌ ERROR checking/enabling pgvector extension: {e}")

    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        print("   Check:")
        print("   - DATABASE_URL in your .env file is correct (including password, host, port 5432, db name 'postgres').")
        print("   - Your current IP address is added to the 'Authorized networks' in Cloud SQL.")
        print("   - The Cloud SQL instance is running.")
    finally:
        if engine:
            await engine.dispose() # Cleanly close the connection pool

if __name__ == "__main__":
    asyncio.run(test_connection())