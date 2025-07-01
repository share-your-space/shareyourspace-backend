from fastapi import APIRouter

from . import auth
from . import users
from . import organizations
from . import admin
from . import matching
from . import connections
from . import notifications
from . import chat
from . import agent
from . import uploads
from . import spaces
from . import invitations
from . import workstations

api_router = APIRouter()

# Include routers with their prefixes
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(organizations.router, prefix="/organizations", tags=["organizations"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(matching.router, prefix="/matching", tags=["matching"])
api_router.include_router(connections.router, prefix="/connections", tags=["connections"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["notifications"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(agent.router, prefix="/agent", tags=["agent"])
api_router.include_router(uploads.router, prefix="/uploads", tags=["uploads"])
api_router.include_router(spaces.router, prefix="/spaces", tags=["spaces"])
api_router.include_router(invitations.router, prefix="/invitations", tags=["invitations"])
api_router.include_router(workstations.router, prefix="/workstations", tags=["workstations"])

# You can optionally define __all__ if you want to control `from app.routers import *` behavior
# __all__ = ["api_router"]

# Leave this file empty 