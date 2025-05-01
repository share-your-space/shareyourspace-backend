import enum

class ContactVisibility(str, enum.Enum):
    PRIVATE = "private"
    CONNECTIONS = "connections"
    PUBLIC = "public"

# Add other enums here as needed, e.g.:
# class UserRole(str, enum.Enum):
#     ADMIN = "admin"
#     USER = "user" 