from fastapi import APIRouter, Depends, UploadFile, File
from app import models, services
from app.dependencies import get_current_active_user
from app.schemas.uploads import ChatAttachmentResponse

router = APIRouter()

@router.post("/chat-attachment", response_model=ChatAttachmentResponse)
async def upload_chat_attachment(
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Upload a file attachment for use in chat.
    Generates a unique filename and returns a signed URL for private access.
    """
    return await services.upload_service.upload_chat_attachment(
        file=file, current_user_id=current_user.id
    ) 