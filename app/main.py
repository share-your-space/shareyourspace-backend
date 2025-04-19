from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware # Import CORS Middleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text # Import text for raw SQL

from app.db.session import get_db # Assuming get_db dependency is here
from app.routers import auth # Import the new auth router

# Define allowed origins (adjust for production later)
origins = [
    "http://localhost:3000", # Frontend dev server
    # Add your deployed frontend URL here for production
]

def create_app() -> FastAPI:
    app = FastAPI(title="ShareYourSpace Backend")

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True, # Allows cookies/auth headers
        allow_methods=["*"],    # Allow all standard methods (GET, POST, etc.)
        allow_headers=["*"],    # Allow all headers
    )

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

    # Include routers
    app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
    # Add other routers here (e.g., users) when created
    # from .routers import users 
    # app.include_router(users.router, prefix="/api/users", tags=["users"])

    return app

app = create_app() 