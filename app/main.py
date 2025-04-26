from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware # Import CORS middleware
# Remove unused imports if AsyncSession/text/get_db are no longer needed directly here
# from sqlalchemy.ext.asyncio import AsyncSession
# from sqlalchemy import text
# from app.db.session import get_db

from app.routers import auth, users, organizations # Import the routers

# Define allowed origins (adjust for production later)
# For development, allow the frontend origin
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
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

# Simple health check endpoint
@app.get("/health")
def read_root():
    return {"status": "ok"}

# The create_app function is no longer needed for this structure
# def create_app() -> FastAPI:
#     ...
#     return app

# Uvicorn will run this 'app' instance based on Dockerfile CMD likely being 'uvicorn app.main:app ...'