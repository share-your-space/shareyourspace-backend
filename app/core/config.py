import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, EmailStr, HttpUrl, PostgresDsn, SecretStr
from typing import List, Optional


class Settings(BaseSettings):
    PROJECT_NAME: str = "ShareYourSpace 2.0" # Added default project name
    DATABASE_URL: PostgresDsn
    SECRET_KEY: SecretStr
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7 # 1 week
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
    GCS_BUCKET_NAME: str
    TARGET_SERVICE_ACCOUNT_EMAIL: str | None = Field(None, validation_alias='TARGET_SERVICE_ACCOUNT_EMAIL')
    GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = None # Path to service account key file (if not using ADC/impersonation)
    MESSAGE_EDIT_DELETE_WINDOW_SECONDS: int = 300 # Default 5 minutes, time in seconds

    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

settings = Settings() 