import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, EmailStr, HttpUrl


class Settings(BaseSettings):
    DATABASE_URL: str = Field(..., validation_alias='DATABASE_URL')
    SECRET_KEY: str = Field(..., validation_alias='SECRET_KEY')
    ALGORITHM: str = Field(..., validation_alias='ALGORITHM')
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(30, validation_alias='ACCESS_TOKEN_EXPIRE_MINUTES') # Default 30 minutes

    # Add other secrets/config variables here later as needed
    RESEND_API_KEY: str | None = Field(None, validation_alias='RESEND_API_KEY')
    STRIPE_SECRET_KEY: str | None = Field(None, validation_alias='STRIPE_SECRET_KEY')
    STRIPE_PUBLISHABLE_KEY: str | None = Field(None, validation_alias='STRIPE_PUBLISHABLE_KEY')
    STRIPE_WEBHOOK_SECRET: str | None = Field(None, validation_alias='STRIPE_WEBHOOK_SECRET')
    GOOGLE_CLIENT_ID: str | None = Field(None, validation_alias='GOOGLE_CLIENT_ID')
    GOOGLE_CLIENT_SECRET: str | None = Field(None, validation_alias='GOOGLE_CLIENT_SECRET')
    LINKEDIN_CLIENT_ID: str | None = Field(None, validation_alias='LINKEDIN_CLIENT_ID')
    LINKEDIN_CLIENT_SECRET: str | None = Field(None, validation_alias='LINKEDIN_CLIENT_SECRET')
    APPLE_CLIENT_ID: str | None = Field(None, validation_alias='APPLE_CLIENT_ID')
    APPLE_TEAM_ID: str | None = Field(None, validation_alias='APPLE_TEAM_ID')
    APPLE_KEY_ID: str | None = Field(None, validation_alias='APPLE_KEY_ID')
    APPLE_PRIVATE_KEY: str | None = Field(None, validation_alias='APPLE_PRIVATE_KEY')
    GOOGLE_AI_API_KEY: str | None = Field(None, validation_alias='GOOGLE_AI_API_KEY')
    FRONTEND_URL: str = Field("http://localhost:3000", validation_alias='FRONTEND_URL') # Default for local dev
    GCS_BUCKET_NAME: str
    TARGET_SERVICE_ACCOUNT_EMAIL: str | None = Field(None, validation_alias='TARGET_SERVICE_ACCOUNT_EMAIL')

    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

settings = Settings() 