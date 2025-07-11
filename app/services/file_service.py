import uuid
from fastapi import UploadFile, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils import storage
from app import models

async def upload_file(
    db: AsyncSession,
    file: UploadFile,
    user_id: int,
    folder: str,
    allowed_content_types: list[str],
) -> str:
    """
    Uploads a file to a specified folder in GCS.
    """
    if file.content_type not in allowed_content_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type {file.content_type} not allowed.",
        )

    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No filename provided.")

    file_extension = file.filename.split('.')[-1] if '.' in file.filename else ''
    unique_filename = f"{uuid.uuid4()}.{file_extension}"
    destination_blob_name = f"{folder}/{unique_filename}"

    try:
        blob_name = await run_in_threadpool(
            storage.upload_file_to_gcs, file=file, destination_blob_name=destination_blob_name
        )
        if not blob_name:
            raise HTTPException(status_code=500, detail="File upload failed.")

        # Using public URL for simplicity as logos are public.
        # If signed URLs are needed, that logic can be used instead.
        public_url = f"https://storage.googleapis.com/{storage.bucket_name}/{blob_name}"
        return public_url
    except Exception as e:
        # Log the exception for debugging
        print(f"Error uploading file: {e}")
        raise HTTPException(status_code=500, detail=f"Could not upload file: {e}")
