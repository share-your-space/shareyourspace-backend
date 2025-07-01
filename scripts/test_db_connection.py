import asyncio
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from app.core.config import settings # To get DATABASE_URL

async def check_db_connection_and_list_tables():
    db_url = str(settings.DATABASE_URL)
    print(f"Attempting to connect to database: {db_url}")
    
    engine = create_async_engine(db_url, echo=False)
    
    try:
        async with engine.connect() as connection:
            print("Successfully connected to the database.")
            
            # List tables (specific to PostgreSQL)
            result = await connection.execute(
                text("SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname != 'pg_catalog' AND schemaname != 'information_schema';")
            )
            tables = result.scalars().all()
            if tables:
                print("Tables found in the database:")
                for table in tables:
                    print(f"- {table}")
            else:
                print("No user tables found in the database.")
            
    except Exception as e:
        print(f"Error connecting to the database or listing tables: {e}")
    finally:
        await engine.dispose()

async def main():
    await check_db_connection_and_list_tables()

if __name__ == "__main__":
    asyncio.run(main()) 