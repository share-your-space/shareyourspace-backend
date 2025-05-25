import logging
import sys
import socketio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Corrected and simplified router imports
from app.routers import (
    auth,
    users,
    organizations,
    spaces,
    connections,
    notifications,
    chat,
    admin,
    matching,
    agent,
    uploads,
    member_requests,
    invitations,
    startup_actions
)
# Any other routers you have should also be in this tuple, e.g., 'profiles' if it's ready.
# Make sure 'utils' is NOT here unless it's a valid, initialized router.

from app.core.config import settings
from app.socket_handlers import register_socketio_handlers
from app.socket_instance import sio
# from app.db.session import engine # Only if used for create_all
from app.db import base_class

# --- Basic Logging Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

origins = [
    "http://localhost:3000",
]

def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        openapi_url=f"{settings.API_V1_STR}/openapi.json",
        description="API for ShareYourSpace platform.",
        version="0.1.0"
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers using the names from the import tuple
    app.include_router(auth.router, prefix=settings.API_V1_STR + "/auth", tags=["auth"])
    app.include_router(users.router, prefix=settings.API_V1_STR + "/users", tags=["users"])
    app.include_router(organizations.router, prefix=settings.API_V1_STR + "/organizations", tags=["organizations"])
    app.include_router(admin.router, prefix=settings.API_V1_STR + "/admin", tags=["admin"])
    app.include_router(matching.router, prefix=settings.API_V1_STR + "/matching", tags=["matching"])
    app.include_router(connections.router, prefix=settings.API_V1_STR + "/connections", tags=["connections"])
    app.include_router(notifications.router, prefix=settings.API_V1_STR + "/notifications", tags=["notifications"])
    app.include_router(chat.router, prefix=settings.API_V1_STR + "/chat", tags=["chat"])
    app.include_router(agent.router, prefix=settings.API_V1_STR + "/agent", tags=["agent"])
    app.include_router(uploads.router, prefix=settings.API_V1_STR + "/uploads", tags=["uploads"])
    app.include_router(spaces.router, prefix=settings.API_V1_STR + "/spaces", tags=["spaces"])
    # If you have a profiles router ready and it's in app.routers.__init__.py and the import tuple above:
    # app.include_router(profiles.router, prefix=settings.API_V1_STR + "/profiles", tags=["profiles"])
    app.include_router(member_requests.router, prefix=settings.API_V1_STR + "/member-requests", tags=["member-requests"])
    app.include_router(invitations.router, prefix=settings.API_V1_STR + "/invitations", tags=["invitations"])
    app.include_router(startup_actions.router, prefix=settings.API_V1_STR + "/startup-actions", tags=["startup-actions"])

    @app.get("/health", tags=["health"])
    async def health_check():
        return {"status": "ok"}

    @app.get("/", tags=["root"])
    async def root():
        return {"message": f"Welcome to {settings.PROJECT_NAME}! Navigate to /docs for API documentation."}

    return app

fastapi_app = create_app()

register_socketio_handlers(sio)
app = socketio.ASGIApp(sio, other_asgi_app=fastapi_app)

# base_class.Base.metadata.create_all(bind=engine) # Usually for dev, ensure Alembic handles prod