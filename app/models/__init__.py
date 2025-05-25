# Import the Base class to make it accessible for models
# and for Alembic discovery via Base.metadata
from app.db.base_class import Base  # noqa: F401

# Models will be discovered by Alembic via Base.metadata
# and should be imported explicitly where needed in the application code,
# not necessarily via this __init__.py.

# However, sometimes explicit imports here ARE needed for relationship setup
# across files before the full app loads. Let's restore necessary ones carefully.

from .user import User # Needed by other models/routers
from .organization import Company, Startup # Needed by User
from .space import SpaceNode, Workstation, WorkstationAssignment # Needed by User?
from .profile import UserProfile # Import the CORRECT profile model
from .connection import Connection # Needed by User
from .notification import Notification # Needed by routers?
from .password_reset_token import PasswordResetToken # Needed by auth?
from .verification_token import VerificationToken # Needed by auth?
from .enums import ContactVisibility # Needed by profile model/schema
from .chat import ChatMessage # Add ChatMessage model import
from .invitation import Invitation, InvitationStatus # Add this line

# You can also import all your models here later so Alembic can find them
# e.g., from .item import Item 

# Optional: if you want to define a __all__ for explicit exports
__all__ = [
    "User",
    "Role",
    "UserRoleLink", 
    "Organization", 
    "OrganizationMember",
    "Startup",
    "Company",
    "Space",
    "Workstation",
    "WorkstationAssignment",
    "Notification",
    "Profile",
    "UserInterest",
    "Skill",
    "UserProfileSkillLink",
    "PasswordResetToken",
    "VerificationToken",
    "Message",
    "MessageReaction",
    "ChatRoom",
    "ChatRoomMember",
    "Connection",
    "ConnectionRequest",
    "Invitation", # Add this line
    "InvitationStatus", # Add this line
    # Enums if they are defined in separate files and imported here, or directly if here.
    "OrganizationRole",
    "UserStatus",
    "SpaceStatus",
    "WorkstationStatus",
    "NotificationType", 
    "NotificationStatus",
    "UserChatRoomRole"
] 