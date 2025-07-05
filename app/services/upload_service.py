import uuid
from fastapi import UploadFile, HTTPException, status
from fastapi.concurrency import run_in_threadpool

from app.utils import storage
from app.schemas.uploads import ChatAttachmentResponse

async def upload_chat_attachment(file: UploadFile, current_user_id: int) -> ChatAttachmentResponse:
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No filename provided.")

    file_extension = file.filename.split('.')[-1] if '.' in file.filename else ''
    unique_filename = f"{uuid.uuid4()}.{file_extension}"
    destination_blob_name = f"chat_attachments/{current_user_id}/{unique_filename}"

    try:
        blob_name = await run_in_threadpool(
            storage.upload_file_to_gcs, file=file, destination_blob_name=destination_blob_name
        )
        if not blob_name:
            raise HTTPException(status_code=500, detail="File upload failed.")

        signed_url = await run_in_threadpool(storage.generate_gcs_signed_url, blob_name=blob_name)
        if not signed_url:
            raise HTTPException(status_code=500, detail="Could not generate access URL.")

        return ChatAttachmentResponse(
            attachment_url=signed_url,
            original_filename=file.filename,
            content_type=file.content_type or "application/octet-stream",
            new_filename=unique_filename
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not upload file: {e}") 