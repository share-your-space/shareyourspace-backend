from pydantic import BaseModel

class ChatAttachmentResponse(BaseModel):
    attachment_url: str
    original_filename: str
    content_type: str
    new_filename: str 