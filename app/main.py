from fastapi import FastAPI, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text # Import text for raw SQL

from app.db.session import get_db # Assuming get_db dependency is here

def create_app() -> FastAPI:
    app = FastAPI(title="ShareYourSpace Backend")

    @app.get("/")
    async def root():
        return {"message": "Welcome to ShareYourSpace API"}

    @app.get("/health/db")
    async def health_check_db(db: AsyncSession = Depends(get_db)):
        try:
            # Try to run a simple query
            await db.execute(text("SELECT 1"))
            return {"status": "OK", "message": "Database connection successful"}
        except Exception as e:
            # If query fails, return error status
            # In production, you might want to log the error `e`
            return {"status": "error", "message": f"Database connection failed: {str(e)}"}

    # Include routers here later
    # from .routers import auth, users, etc.
    # app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
    # app.include_router(users.router, prefix="/api/users", tags=["users"])

    return app

app = create_app() 