# Leave this file empty 

# Import the Base class to make it accessible for models
from app.db.base_class import Base
from .user import User  # Import the User model

# You can also import all your models here later so Alembic can find them
# e.g., from .item import Item 