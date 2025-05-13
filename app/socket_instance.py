import socketio

# Configure allowed origins for Socket.IO (match FastAPI CORS or be more specific)
# For production, use a specific list, not "*"
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*') # TODO: Restrict origins for production 