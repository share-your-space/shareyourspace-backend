from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app import crud, models, schemas
from app.socket_instance import sio

async def get_user_conversations(db: AsyncSession, *, user_id: int) -> List[schemas.chat.ConversationForList]:
    return await crud.crud_chat.get_user_conversations_with_details(db=db, user_id=user_id)

async def get_conversation(
    db: AsyncSession, *, conversation_id: int, user_id: int
) -> models.Conversation:
    conversation = await crud.crud_chat.get_conversation_by_id(
        db=db, conversation_id=conversation_id, user_id=user_id
    )
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found or user not a participant.")
    return conversation

async def get_or_create_conversation(
    db: AsyncSession, *, user1_id: int, user2_id: int, is_external: bool = False
) -> models.Conversation:
    other_user = await crud.crud_user.get_user_by_id(db, user_id=user2_id)
    if not other_user:
        raise HTTPException(status_code=404, detail="Other user not found")

    conversation = await crud.crud_chat.get_or_create_conversation(
        db=db, user1_id=user1_id, user2_id=user2_id, is_external=is_external
    )
    if not conversation:
        raise HTTPException(status_code=500, detail="Could not get or create conversation.")
    
    return conversation

async def get_messages(
    db: AsyncSession, *, conversation_id: int, skip: int, limit: int
) -> List[models.ChatMessage]:
    return await crud.crud_chat.get_messages_for_conversation(
        db=db, conversation_id=conversation_id, skip=skip, limit=limit
    )

async def mark_conversation_as_read(db: AsyncSession, *, conversation_id: int, user_id: int) -> None:
    updated = await crud.crud_chat.mark_conversation_as_read(
        db=db, conversation_id=conversation_id, user_id=user_id
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Conversation not found or user is not a participant.")
    
    notification_ref = f"conversation:{conversation_id}"
    await crud.crud_notification.mark_notifications_as_read_by_ref(
        db=db, user_id=user_id, reference=notification_ref
    )

async def edit_message(
    db: AsyncSession, *, message_id: int, current_user_id: int, new_content: str
) -> models.ChatMessage:
    updated_message = await crud.crud_chat.update_message(
        db, message_id=message_id, current_user_id=current_user_id, new_content=new_content
    )
    if not updated_message:
        raise HTTPException(status_code=403, detail="Message cannot be edited.")
    
    # Emit event
    if updated_message.conversation:
        updated_message_data = schemas.chat.ChatMessageSchema.model_validate(updated_message).model_dump(mode='json')
        for participant in updated_message.conversation.participants:
            await sio.emit("message_updated", data=updated_message_data, room=str(participant.id))
            
    return updated_message

async def delete_message(db: AsyncSession, *, message_id: int, current_user_id: int) -> models.ChatMessage:
    deleted_message = await crud.crud_chat.delete_message(
        db, message_id=message_id, current_user_id=current_user_id
    )
    if not deleted_message:
        raise HTTPException(status_code=403, detail="Message cannot be deleted.")

    # Emit event
    if deleted_message.conversation:
        deleted_message_data = schemas.chat.ChatMessageSchema.model_validate(deleted_message).model_dump(mode='json')
        for participant in deleted_message.conversation.participants:
            await sio.emit("message_deleted", data=deleted_message_data, room=str(participant.id))
            
    return deleted_message

async def add_or_toggle_reaction(
    db: AsyncSession, *, message_id: int, user_id: int, emoji: str
) -> models.MessageReaction:
    reaction = await crud.crud_chat.add_or_toggle_reaction(
        db, message_id=message_id, user_id=user_id, emoji=emoji
    )
    
    chat_message = await crud.crud_chat.get_chat_message_by_id(db, message_id=message_id)
    if chat_message and chat_message.conversation:
        action = "added" if reaction else "removed"
        reaction_payload = schemas.chat.MessageReactionResponse.model_validate(reaction).model_dump(mode='json') if reaction else None

        for participant in chat_message.conversation.participants:
            await sio.emit(
                "reaction_updated",
                data={
                    "message_id": message_id,
                    "conversation_id": chat_message.conversation.id,
                    "reaction": reaction_payload,
                    "user_id_who_reacted": user_id,
                    "emoji": emoji,
                    "action": action,
                },
                room=str(participant.id),
            )
            
    return reaction

async def remove_reaction(db: AsyncSession, *, message_id: int, user_id: int, emoji: str) -> None:
    success = await crud.crud_chat.remove_reaction(
        db, message_id=message_id, user_id=user_id, emoji=emoji
    )
    if not success:
        raise HTTPException(status_code=404, detail="Reaction not found or already removed")

    chat_message = await crud.crud_chat.get_chat_message_by_id(db, message_id=message_id)
    if chat_message and chat_message.conversation:
        for participant in chat_message.conversation.participants:
            await sio.emit(
                "reaction_updated",
                data={
                    "message_id": message_id,
                    "conversation_id": chat_message.conversation.id,
                    "reaction": None,
                    "user_id_who_reacted": user_id,
                    "emoji": emoji,
                    "action": "removed",
                },
                room=str(participant.id),
            )

async def get_reactions(db: AsyncSession, *, message_id: int) -> List[models.MessageReaction]:
    return await crud.crud_chat.get_reactions_for_message(db, message_id=message_id) 