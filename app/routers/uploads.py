from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.concurrency import run_in_threadpool # <-- ADDED IMPORT
from pydantic import BaseModel
import shutil # For saving file temporarily if needed, or getting filename/mimetype
import uuid # For generating unique filenames

from app.utils.storage import upload_file # Assuming this function exists and works
from app.schemas.user import User # To get current user for path generation
from app.dependencies import get_current_active_user # Assuming this dependency for auth

router = APIRouter()

class ChatAttachmentResponse(BaseModel):
    attachment_url: str
    original_filename: str
    content_type: str
    new_filename: str # The unique filename used for storage

@router.post("/chat-attachment", response_model=ChatAttachmentResponse)
async def upload_chat_attachment(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user)
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided.")

    # Generate a unique filename to prevent overwrites and ensure privacy
    file_extension = file.filename.split('.')[-1] if '.' in file.filename else ''
    unique_filename = f"{uuid.uuid4()}.{file_extension}"
    
    # Define a destination path within GCS, e.g., chat_attachments/user_id/unique_filename
    # The upload_file utility should handle the bucket name itself.
    destination_blob_name = f"chat_attachments/{current_user.id}/{unique_filename}"

    try:
        # The upload_file function is synchronous, call it in a thread pool
        attachment_url = await run_in_threadpool(
            upload_file, # The synchronous function to call
            file=file,  # Arguments for upload_file
            destination_blob_name=destination_blob_name
        )
        
        if not attachment_url:
            raise HTTPException(status_code=500, detail="File upload failed, URL not returned.")

        return ChatAttachmentResponse(
            attachment_url=attachment_url,
            original_filename=file.filename,
            content_type=file.content_type or "application/octet-stream",
            new_filename=unique_filename # Useful if client wants to store this too
        )
    except Exception as e:
        # Log the exception e
        print(f"Error during chat attachment upload: {e}") # Basic logging
        raise HTTPException(status_code=500, detail=f"Could not upload file: {e}") 