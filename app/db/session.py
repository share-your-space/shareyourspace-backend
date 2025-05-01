from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# Convert Pydantic DSN object to string for SQLAlchemy engine
engine = create_async_engine(str(settings.DATABASE_URL), pool_pre_ping=True)

# Create a session factory bound to the engine
AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Dependency function for FastAPI to get a DB session
async def get_db() -> AsyncSession:
    """Dependency function to get DB session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close() 