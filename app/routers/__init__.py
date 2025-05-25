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
# from . import profiles # Temporarily removed
from . import member_requests
from . import invitations # Ensure invitations is imported
from . import startup_actions # Add the new router
# If you have other router files like invites.py, add them here as well:
# from . import invites

# You can optionally define __all__ if you want to control `from app.routers import *` behavior
# __all__ = [
# "auth", "users", "organizations", "admin", "matching", 
# "connections", "notifications", "chat", "agent", "uploads", 
# "spaces", "member_requests" # Temporarily removed profiles
# ]

# Leave this file empty 