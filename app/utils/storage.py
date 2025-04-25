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

from app.core.config import settings

# Configure logging
logger = logging.getLogger(__name__)

# Initialize GCS client
# If GOOGLE_APPLICATION_CREDENTIALS is set in the environment or config,
# the client will use that keyfile. Otherwise, it attempts to use ADC.
try:
    # Get default credentials (expected to be user ADC via mounted file)
    source_credentials, project_id = google.auth.default()

    if settings.TARGET_SERVICE_ACCOUNT_EMAIL:
        print(f"Attempting to impersonate Service Account: {settings.TARGET_SERVICE_ACCOUNT_EMAIL}") # Temporary print
        # Create impersonated credentials
        scoped_credentials = impersonated_credentials.Credentials(
            source_credentials=source_credentials,
            target_principal=settings.TARGET_SERVICE_ACCOUNT_EMAIL,
            target_scopes=['https://www.googleapis.com/auth/devstorage.full_control'], # Scope needed for GCS
            # lifetime=3600, # Optional: default is 1 hour
        )
        # Initialize client with impersonated credentials
        storage_client = storage.Client(credentials=scoped_credentials, project=project_id)
        print("GCS Client initialized with IMPERSONATED credentials.") # Temporary print
    else:
        # Fallback to using default (user) credentials directly if no impersonation target
        # Note: This won't be able to sign URLs
        print("Impersonation target email not set. Using default credentials directly.") # Temporary print
        storage_client = storage.Client(credentials=source_credentials, project=project_id)

    GCS_BUCKET = storage_client.bucket(settings.GCS_BUCKET_NAME)
except Exception as e:
    logger.error(f"Failed to initialize Google Cloud Storage client: {e}", exc_info=True)
    storage_client = None
    GCS_BUCKET = None

def upload_file(
    file: UploadFile,
    destination_blob_name: str
) -> str | None:
    """Uploads a file to the GCS bucket.

    Args:
        file: The FastAPI UploadFile object.
        destination_blob_name: The desired name for the blob in GCS.

    Returns:
        The destination_blob_name if upload was successful, otherwise None.
    """
    if not GCS_BUCKET or not storage_client:
        logger.error("GCS bucket or client not initialized. Cannot upload file.")
        return None

    blob = GCS_BUCKET.blob(destination_blob_name)

    try:
        # Upload the file content directly from the UploadFile object
        # Ensure the file pointer is at the beginning
        file.file.seek(0)
        blob.upload_from_file(file.file, content_type=file.content_type)

        logger.info(f"File {file.filename} uploaded to {destination_blob_name}.")
        # Return the blob name, not the public URL
        return destination_blob_name

    except GoogleAPICallError as e:
        logger.error(f"GCS API error during upload to {destination_blob_name}: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Unexpected error during upload to {destination_blob_name}: {e}", exc_info=True)
        return None

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