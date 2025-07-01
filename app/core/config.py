import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, EmailStr, HttpUrl, PostgresDsn, SecretStr
from typing import List, Optional
# import hashlib # Removed for hashing the secret key for debug
# import logging # Removed for logging

# logger = logging.getLogger(__name__) # Removed for logging

class Settings(BaseSettings):
    PROJECT_NAME: str = "ShareYourSpace 2.0" # Added default project name
    DATABASE_URL: PostgresDsn
    SECRET_KEY: SecretStr
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8  # 8 days
    ACCESS_TOKEN_EXPIRE_MINUTES_IMPERSONATE: int = 15 # 15 minutes for impersonation tokens
    API_V1_STR: str = "/api/v1"

    # Add other secrets/config variables here later as needed
    RESEND_API_KEY: SecretStr | None = None
    STRIPE_SECRET_KEY: SecretStr | None = None
    STRIPE_PUBLISHABLE_KEY: str | None = None # No SecretStr needed
    STRIPE_WEBHOOK_SECRET: SecretStr | None = None
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: SecretStr | None = None
    LINKEDIN_CLIENT_ID: str | None = None
    LINKEDIN_CLIENT_SECRET: SecretStr | None = None
    APPLE_CLIENT_ID: str | None = None
    APPLE_TEAM_ID: str | None = None
    APPLE_KEY_ID: str | None = None
    APPLE_PRIVATE_KEY: SecretStr | None = None
    GOOGLE_AI_API_KEY: SecretStr | None = None
    FRONTEND_URL: str = Field(default="http://localhost:3000", description="Base URL for the frontend application")
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000"]
    GCS_BUCKET_NAME: str
    TARGET_SERVICE_ACCOUNT_EMAIL: str | None = Field(None, validation_alias='TARGET_SERVICE_ACCOUNT_EMAIL')
    GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = None # Path to service account key file (if not using ADC/impersonation)
    MESSAGE_EDIT_DELETE_WINDOW_SECONDS: int = 300 # Default 5 minutes, time in seconds
    INVITATION_EXPIRE_DAYS: int = 7 # Default 7 days for invitation expiry
    EMAIL_FROM_ADDRESS: str = "ShareYourSpace Onboarding <onboarding@shareyourspace.app>" # Added From Email
    # Token settings
    ONBOARDING_TOKEN_EXPIRE_MINUTES: int = 15 # 15 minutes for onboarding
    VERIFICATION_TOKEN_EXPIRE_HOURS: int = 1
    PASSWORD_RESET_TOKEN_EXPIRE_HOURS: int = 1
    SET_PASSWORD_TOKEN_EXPIRE_DAYS: int = 1

    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

settings = Settings()

# # --- TEMP DEBUG: Print hash of loaded SECRET_KEY ---
# try:
#     secret_key_value = settings.SECRET_KEY.get_secret_value()
#     hashed_secret = hashlib.sha256(secret_key_value.encode('utf-8')).hexdigest()
#     logger.warning(f"DEBUG: Loaded SECRET_KEY hash: {hashed_secret}")
# except Exception as e:
#     logger.error(f"DEBUG: Could not load/hash SECRET_KEY: {e}")
# # --- END TEMP DEBUG --- 