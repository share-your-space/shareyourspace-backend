import socketio
from app.core.config import settings

# Configure allowed origins for Socket.IO to match FastAPI CORS settings
# This ensures that only trusted frontends can connect.
sio = socketio.AsyncServer(
    async_mode='asgi', 
    cors_allowed_origins=settings.ALLOWED_ORIGINS
)