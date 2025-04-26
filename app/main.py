from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware # Import CORS Middleware
# Remove unused imports if AsyncSession/text/get_db are no longer needed directly here
# from sqlalchemy.ext.asyncio import AsyncSession
# from sqlalchemy import text
# from app.db.session import get_db

from app.routers import auth, users, organizations, admin # Import the routers
from app.core.config import settings

# Define allowed origins (adjust for production later)
# For development, allow your frontend origin
origins = [
    "http://localhost:3000", # Your frontend dev server
    "http://localhost:3001", # Add other potential origins if needed
    # Add your production frontend URL here later
]

# Initialize FastAPI app instance
app = FastAPI(
    title="ShareYourSpace API",
    description="API for ShareYourSpace platform.",
    version="0.1.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True, # Allow cookies
    allow_methods=["*"],    # Allow all methods (GET, POST, etc.)
    allow_headers=["*"],    # Allow all headers
)

# Include routers directly on the global app instance
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(organizations.router, prefix="/api/organizations", tags=["organizations"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])

# Simple health check endpoint
@app.get("/health")
def read_root():
    return {"status": "ok"}

def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        openapi_url=f"{settings.API_V1_STR}/openapi.json"
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"], # Allows all methods (GET, POST, PUT, etc.)
        allow_headers=["*"], # Allows all headers
    )

    # Include routers
    app.include_router(auth.router, prefix=settings.API_V1_STR + "/auth", tags=["auth"])
    app.include_router(users.router, prefix=settings.API_V1_STR + "/users", tags=["users"])
    app.include_router(organizations.router, prefix=settings.API_V1_STR + "/organizations", tags=["organizations"])
    app.include_router(admin.router, prefix=settings.API_V1_STR + "/admin", tags=["admin"])

    # Simple health check endpoint
    @app.get("/health", tags=["health"])
    async def health_check():
        return {"status": "ok"}

    return app

app = create_app()

# Uvicorn will run this 'app' instance based on Dockerfile CMD likely being 'uvicorn app.main:app ...'