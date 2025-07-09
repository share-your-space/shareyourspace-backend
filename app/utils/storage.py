import logging
import os
import datetime
from google.cloud import storage
from google.api_core.exceptions import GoogleAPICallError
from fastapi import UploadFile, Response
from google.cloud.storage.blob import Blob
import google.auth
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google.auth import impersonated_credentials
from datetime import timedelta
import asyncio


from app.core.config import settings

# Configure logging
logger = logging.getLogger(__name__)

class GcsStorage:
    def __init__(self):
        self.storage_client: storage.Client | None = None
        self.bucket: storage.bucket.Bucket | None = None
        self._initialize_client()

    def _initialize_client(self):
        try:
            # Check if running in a production-like environment (e.g., Render)
            # where a specific service account file is provided.
            if settings.GOOGLE_APPLICATION_CREDENTIALS and os.path.exists(settings.GOOGLE_APPLICATION_CREDENTIALS):
                logger.info(f"Initializing GCS client from service account file: {settings.GOOGLE_APPLICATION_CREDENTIALS}")
                self.storage_client = storage.Client.from_service_account_json(
                    settings.GOOGLE_APPLICATION_CREDENTIALS
                )
                logger.info("GCS Client initialized using service account JSON.")
            # Fallback to impersonation for local development
            elif settings.TARGET_SERVICE_ACCOUNT_EMAIL:
                logger.info("Using Application Default Credentials for impersonation.")
            source_credentials, project_id = google.auth.default()
            effective_project_id = project_id or settings.GOOGLE_CLOUD_PROJECT
                logger.info(f"Attempting to impersonate Service Account: {settings.TARGET_SERVICE_ACCOUNT_EMAIL}")
                scoped_credentials = impersonated_credentials.Credentials(
                    source_credentials=source_credentials,
                    target_principal=settings.TARGET_SERVICE_ACCOUNT_EMAIL,
                    target_scopes=['https://www.googleapis.com/auth/devstorage.read_write'],
                    lifetime=3600,
                )
                self.storage_client = storage.Client(credentials=scoped_credentials, project=effective_project_id)
                logger.info(f"GCS Client initialized with IMPERSONATED credentials for project {effective_project_id}.")
            else:
                 logger.error("No valid Google Cloud credentials configuration found. GCS client not initialized.")
                 return # Exit initialization if no credentials found

            if self.storage_client and settings.GCS_BUCKET_NAME:
                self.bucket = self.storage_client.bucket(settings.GCS_BUCKET_NAME)
                logger.info(f"GCS Bucket {settings.GCS_BUCKET_NAME} obtained.")
            elif not self.storage_client:
                logger.error("Storage client not initialized. Cannot obtain bucket.")

        except Exception as e:
            logger.error(f"Failed to initialize Google Cloud Storage client or bucket: {e}", exc_info=True)

    async def upload_file_async(self, file: UploadFile, blob_name: str, content_type: str) -> str:
        if not self.bucket or not self.storage_client:
            raise ConnectionAbortedError("GCS not initialized")

        blob = self.bucket.blob(blob_name)
        
        loop = asyncio.get_running_loop()
        file_content = await file.read()

        await loop.run_in_executor(
            None,
            lambda: blob.upload_from_string(file_content, content_type=content_type)
        )
        logger.info(f"File {file.filename} uploaded to GCS: {settings.GCS_BUCKET_NAME}/{blob_name}")
        return blob_name

    def generate_signed_url(self, blob_name: str, expiration_minutes: int = 60) -> str:
        if not self.bucket or not self.storage_client:
            raise ConnectionAbortedError("GCS not initialized")
        
        blob = self.bucket.blob(blob_name)
        return blob.generate_signed_url(version="v4", expiration=timedelta(minutes=expiration_minutes))

    def delete_blob(self, blob_name: str):
        if not self.bucket or not self.storage_client:
            raise ConnectionAbortedError("GCS not initialized")

        blob = self.bucket.blob(blob_name)
        if blob.exists():
            blob.delete()
            logger.info(f"Blob {blob_name} deleted successfully from GCS bucket {settings.GCS_BUCKET_NAME}.")

gcs_storage = GcsStorage() 