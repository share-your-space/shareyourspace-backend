# Leave this file empty 

# Import the Base class to make it accessible for models
from app.db.base_class import Base  # noqa: F401
from .user import User  # Import the User model
from .verification_token import VerificationToken # Import the VerificationToken model
from .password_reset_token import PasswordResetToken # noqa: F401
from .user_profile import UserProfile # Import the new model

# You can also import all your models here later so Alembic can find them
# e.g., from .item import Item 