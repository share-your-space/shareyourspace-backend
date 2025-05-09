import logging # Add logging
import sys # Add sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware # Import CORS Middleware
# Remove unused imports if AsyncSession/text/get_db are no longer needed directly here
# from sqlalchemy.ext.asyncio import AsyncSession
# from sqlalchemy import text
# from app.db.session import get_db

from app.routers import auth, users, organizations, admin, matching, connections, notifications # Import connections router
from app.core.config import settings

# --- Basic Logging Configuration ---
logging.basicConfig(
    level=logging.INFO, # Set the root logger level
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout) # Log to stdout
    ]
)
# Set specific log levels for libraries if needed (optional)
# logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING) 
# logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
# --- End Logging Configuration ---


# Define allowed origins (adjust for production later)
# For development, allow your frontend origin
# This list will be used inside create_app
origins = [
    "http://localhost:3000", # Your frontend dev server
    # Add your production frontend URL here later
    # e.g., "https://your-frontend-domain.com"
]

# Remove initial app creation and configuration
# app = FastAPI(...)
# app.add_middleware(...)
# app.include_router(...)

def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        openapi_url=f"{settings.API_V1_STR}/openapi.json",
        description="API for ShareYourSpace platform.",
        version="0.1.0"
    )

    # Add CORS middleware using the defined origins list
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins, # Use the list defined above
        allow_credentials=True,
        allow_methods=["*"], # Allows all methods (GET, POST, PUT, etc.)
        allow_headers=["*"], # Allows all headers
    )

    # Include routers
    app.include_router(auth.router, prefix=settings.API_V1_STR + "/auth", tags=["auth"])
    app.include_router(users.router, prefix=settings.API_V1_STR + "/users", tags=["users"])
    app.include_router(organizations.router, prefix=settings.API_V1_STR + "/organizations", tags=["organizations"])
    app.include_router(admin.router, prefix=settings.API_V1_STR + "/admin", tags=["admin"])
    app.include_router(matching.router, prefix=settings.API_V1_STR + "/matching", tags=["matching"])
    app.include_router(connections.router, prefix=settings.API_V1_STR + "/connections", tags=["connections"]) # Add connections router
    app.include_router(notifications.router, prefix=settings.API_V1_STR + "/notifications", tags=["notifications"]) # Add notifications router

    # Simple health check endpoint
    @app.get("/health", tags=["health"])
    async def health_check():
        return {"status": "ok"}

    return app

# Create the app instance using the factory function
app = create_app()

# Uvicorn will run this 'app' instance