from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
import socketio

from app.routers import (
    auth, users, sys_admin, corp_admin, spaces, organizations, invitations,
    connections, chat, notifications, matching, workstations,
    uploads, interests
)
from app.core.config import settings
from app.socket_handlers import register_socketio_handlers
from app.socket_instance import sio

# Initialize FastAPI app, but name it 'fastapi_app' to avoid conflict
fastapi_app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

fastapi_app.state.sio = sio

# Set all CORS enabled origins
if settings.ALLOWED_ORIGINS:
    fastapi_app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin).strip() for origin in settings.ALLOWED_ORIGINS],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Include all routers to the FastAPI app instance
fastapi_app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
fastapi_app.include_router(sys_admin.router, prefix="/api/v1", tags=["System Admin"])
fastapi_app.include_router(corp_admin.router, prefix="/api/v1/company", tags=["Corporate Admin"])
fastapi_app.include_router(users.router, prefix="/api/v1/users", tags=["users"])
fastapi_app.include_router(spaces.router, prefix="/api/v1/spaces", tags=["spaces"])
fastapi_app.include_router(workstations.router, prefix="/api/v1/workstations", tags=["workstations"])
fastapi_app.include_router(organizations.router, prefix="/api/v1/organizations", tags=["organizations"])
fastapi_app.include_router(invitations.router, prefix="/api/v1/invitations", tags=["invitations"])
fastapi_app.include_router(connections.router, prefix="/api/v1/connections", tags=["connections"])
fastapi_app.include_router(chat.router, prefix="/api/v1/chat", tags=["chat"])
fastapi_app.include_router(notifications.router, prefix="/api/v1/notifications", tags=["notifications"])
fastapi_app.include_router(matching.router, prefix="/api/v1/matching", tags=["matching"])
fastapi_app.include_router(uploads.router, prefix="/api/v1/uploads", tags=["uploads"])
fastapi_app.include_router(interests.router, prefix="/api/v1/interests", tags=["interests"])

@fastapi_app.get("/health", tags=["health"])
def read_root():
    return {"status": "ok"}

# Create the final ASGI app that wraps FastAPI and Socket.IO. 
# This 'app' is what uvicorn will run.
app = socketio.asgi.ASGIApp(sio, other_asgi_app=fastapi_app)
register_socketio_handlers(sio)
