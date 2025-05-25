# Leave this file empty 
from .user import User, UserCreate, UserUpdateInternal # noqa
from .verification_token import VerificationToken, VerificationTokenCreate # noqa
# Import specific password reset schemas needed
from .password_reset_token import PasswordResetTokenCreate, RequestPasswordResetRequest, ResetPasswordRequest # noqa
from .token import Token, TokenPayload # noqa
from .user_profile import UserProfile, UserProfileUpdate # noqa
from . import organization # noqa: Import the organization schemas
from . import chat # noqa: Import the chat schemas 
from .message import Message # noqa 
from . import auth # noqa: Import the auth schemas

# After all schemas are imported, rebuild models with forward references
from .auth import TokenWithUser
from .user import User, UserDetail

TokenWithUser.model_rebuild()
User.model_rebuild() # Rebuild User schema as well, as it's referenced
UserDetail.model_rebuild() # And UserDetail, as it references other schemas

# Add other model_rebuild calls here if new forward refs are introduced