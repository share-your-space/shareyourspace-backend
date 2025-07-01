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

from app.core.config import settings

# Configure logging
logger = logging.getLogger(__name__)

storage_client: storage.Client | None = None
GCS_BUCKET: storage.bucket.Bucket | None = None

try:
    source_credentials, project_id = google.auth.default()
    effective_project_id = project_id or settings.GOOGLE_CLOUD_PROJECT # Use GOOGLE_CLOUD_PROJECT from settings if ADC doesn't provide it

    if settings.TARGET_SERVICE_ACCOUNT_EMAIL:
        logger.info(f"Attempting to impersonate Service Account: {settings.TARGET_SERVICE_ACCOUNT_EMAIL}")
        scoped_credentials = impersonated_credentials.Credentials(
            source_credentials=source_credentials,
            target_principal=settings.TARGET_SERVICE_ACCOUNT_EMAIL,
            target_scopes=['https://www.googleapis.com/auth/devstorage.read_write'], # More specific scope
            lifetime=3600, # 1 hour
        )
        storage_client = storage.Client(credentials=scoped_credentials, project=effective_project_id)
        logger.info(f"GCS Client initialized with IMPERSONATED credentials for project {effective_project_id}.")
    elif source_credentials:
        logger.info(f"Using default Application Default Credentials for project {effective_project_id}.")
        storage_client = storage.Client(credentials=source_credentials, project=effective_project_id)
    else:
        logger.warning("Could not obtain Google Cloud credentials. GCS client not initialized.")

    if storage_client and settings.GCS_BUCKET_NAME:
        GCS_BUCKET = storage_client.bucket(settings.GCS_BUCKET_NAME)
        logger.info(f"GCS Bucket {settings.GCS_BUCKET_NAME} obtained.")
    elif not storage_client:
        logger.error("Storage client not initialized. Cannot obtain bucket.")

except Exception as e:
    logger.error(f"Failed to initialize Google Cloud Storage client or bucket: {e}", exc_info=True)
    # storage_client and GCS_BUCKET remain None

def upload_file_to_gcs(
    file: UploadFile,
    destination_blob_name: str
) -> str | None:
    """Uploads a file to GCS and returns the blob name if successful."""
    if not GCS_BUCKET or not storage_client:
        logger.error("GCS bucket or client not initialized. Cannot upload file.")
        return None

    blob = GCS_BUCKET.blob(destination_blob_name)

    try:
        file.file.seek(0)
        blob.upload_from_file(file.file, content_type=file.content_type)
        logger.info(f"File {file.filename} uploaded to GCS: {settings.GCS_BUCKET_NAME}/{destination_blob_name}")
        return destination_blob_name # Return the blob name
    except GoogleAPICallError as e:
        logger.error(f"GCS API error during upload to {destination_blob_name}: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Unexpected error during upload to {destination_blob_name}: {e}", exc_info=True)
        return None

def generate_gcs_signed_url(blob_name: str, expiration_minutes: int = 60) -> str | None:
    """Generates a signed URL for a GCS blob."""
    if not GCS_BUCKET or not storage_client:
        logger.error("GCS bucket or client not initialized. Cannot generate signed URL.")
        return None
    if not blob_name:
        logger.warning("generate_gcs_signed_url called with empty blob_name.")
        return None

    blob = GCS_BUCKET.blob(blob_name)
    try:
        # Ensure the service account used (either default or impersonated)
        # has permissions to generate signed URLs (roles/iam.serviceAccountTokenCreator on the SA itself)
        # and read access to the blob.
        signed_url = blob.generate_signed_url(version="v4", expiration=timedelta(minutes=expiration_minutes), method="GET")
        logger.info(f"Generated v4 signed URL for blob {blob_name} expiring in {expiration_minutes} minutes.")
        return signed_url
    except GoogleAPICallError as e:
        logger.error(f"GCS API error generating signed URL for {blob_name}: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Unexpected error generating signed URL for {blob_name}: {e}", exc_info=True)
        return None

# Optional: Function to delete a blob if needed for cleanup
def delete_gcs_blob(blob_name: str) -> bool:
    if not GCS_BUCKET or not storage_client:
        logger.error("GCS bucket or client not initialized. Cannot delete blob.")
        return False
    if not blob_name:
        logger.warning("delete_gcs_blob called with empty blob_name.")
        return False
    
    blob = GCS_BUCKET.blob(blob_name)
    try:
        if blob.exists():
            blob.delete()
            logger.info(f"Blob {blob_name} deleted successfully from GCS bucket {settings.GCS_BUCKET_NAME}.")
            return True
        else:
            logger.warning(f"Attempted to delete non-existent blob: {blob_name}")
            return False
    except GoogleAPICallError as e:
        logger.error(f"GCS API error deleting blob {blob_name}: {e}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"Unexpected error deleting blob {blob_name}: {e}", exc_info=True)
        return False

def download_blob(blob_name: str) -> Blob | None:
    """Downloads a blob object from GCS. Returns the Blob object itself."""
    if not GCS_BUCKET or not storage_client:
        logger.error("GCS bucket or client not initialized. Cannot download blob.")
        return None
    if not blob_name:
        return None
    try:
        blob = GCS_BUCKET.blob(blob_name)
        # Check if blob exists before trying to download (optional but good practice)
        if not blob.exists():
             logger.warning(f"Attempted to download non-existent blob: {blob_name}")
             return None
        return blob
    except GoogleAPICallError as e:
        logger.error(f"GCS API error downloading blob {blob_name}: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Unexpected error downloading blob {blob_name}: {e}", exc_info=True)
        return None 