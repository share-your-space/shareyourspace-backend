import asyncio
import sys
import os
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import text, delete, or_, update
from sqlalchemy.orm import selectinload
import logging

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Adjust path for script execution
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import AsyncSessionLocal
from app.models.user import User, UserRole
from app.models.profile import UserProfile
from app.models.notification import Notification
from app.models.verification_token import VerificationToken
from app.models.space import SpaceNode, Workstation, WorkstationAssignment
from app.models.interest import Interest
from app.models.connection import Connection
from app.models.chat import ChatMessage, ConversationParticipant, MessageReaction
from app.models.organization import Company, Startup
from app.models.invitation import Invitation

async def delete_user_and_associated_data(db: AsyncSession, user_email: str):
    logger.info(f"Attempting to delete user: {user_email} and associated data.")
    try:
        user_stmt = select(User).options(selectinload(User.startup).selectinload(Startup.direct_members)).where(User.email == user_email)
        user_result = await db.execute(user_stmt)
        user = user_result.scalar_one_or_none()

        if not user:
            logger.info(f"User with email {user_email} not found.")
            return

        user_id = user.id
        logger.info(f"Found user ID: {user_id} for email: {user_email}, Role: {user.role}")

        startup_id_to_delete = None
        if user.role == UserRole.STARTUP_ADMIN and user.startup:
            logger.info(f"User is a STARTUP_ADMIN for startup '{user.startup.name}' (ID: {user.startup.id}). Queueing startup for deletion after all members are removed.")
            member_emails_to_delete = [member.email for member in user.startup.direct_members if member.id != user_id]
            
            startup_id_to_delete = user.startup.id

            for member_email in member_emails_to_delete:
                logger.info(f"Calling deletion for startup member: {member_email}")
                await delete_user_and_associated_data(db, member_email)

        logger.info(f"Deleting Invitations for user_id: {user_id} or email: {user_email}...")
        await db.execute(delete(Invitation).where(
            or_(
                Invitation.accepted_by_user_id == user_id,
                Invitation.invited_by_user_id == user_id,
                Invitation.revoked_by_admin_id == user_id,
                Invitation.approved_by_admin_id == user_id,
                Invitation.email == user_email
            )
        ))
        
        logger.info(f"Finding conversations for user_id: {user_id} to delete messages and reactions...")
        participant_entries = await db.execute(select(ConversationParticipant).where(ConversationParticipant.user_id == user_id))
        conversation_ids = [p.conversation_id for p in participant_entries.scalars().all()]

        if conversation_ids:
            logger.info(f"Deleting MessageReactions from conversations user {user_id} was part of...")
            await db.execute(delete(MessageReaction).where(MessageReaction.conversation_id.in_(conversation_ids)))

            logger.info(f"Deleting ChatMessages from conversations user {user_id} was part of...")
            await db.execute(delete(ChatMessage).where(ChatMessage.conversation_id.in_(conversation_ids)))
        
        logger.info(f"Deleting MessageReactions made by user_id: {user_id}...")
        await db.execute(delete(MessageReaction).where(MessageReaction.user_id == user_id))

        logger.info(f"Deleting ConversationParticipants for user_id: {user_id}...")
        await db.execute(delete(ConversationParticipant).where(ConversationParticipant.user_id == user_id))
        
        logger.info(f"Deleting Interests for user_id: {user_id}...")
        await db.execute(delete(Interest).where(Interest.user_id == user_id))

        logger.info(f"Deleting Connections for user_id: {user_id}...")
        await db.execute(delete(Connection).where(or_(Connection.requester_id == user_id, Connection.recipient_id == user_id)))
        
        logger.info(f"Deleting WorkstationAssignments for user_id: {user_id}...")
        await db.execute(delete(WorkstationAssignment).where(WorkstationAssignment.user_id == user_id))

        logger.info(f"Deleting notifications for user_id: {user_id}...")
        await db.execute(delete(Notification).where(
            or_(
                Notification.user_id == user_id, 
                Notification.related_entity_id == user_id,
                Notification.sender_id == user_id
            )
        ))

        logger.info(f"Deleting VerificationToken for user_id: {user_id}...")
        await db.execute(delete(VerificationToken).where(VerificationToken.user_id == user_id))

        logger.info(f"Deleting UserProfile for user_id: {user_id}...")
        await db.execute(delete(UserProfile).where(UserProfile.user_id == user_id))
        
        logger.info(f"Deleting user record for user_id: {user_id} (email: {user_email})...")
        await db.execute(delete(User).where(User.id == user_id))

        if startup_id_to_delete:
            logger.info(f"Deleting startup record ID: {startup_id_to_delete}")
            await db.execute(delete(Startup).where(Startup.id == startup_id_to_delete))
            logger.info(f"Startup {startup_id_to_delete} deleted.")

        await db.commit()
        logger.info(f"Successfully committed deletions for user {user_email}.")

    except Exception as e:
        logger.error(f"Error during deletion process for {user_email}: {e}", exc_info=True)
        await db.rollback()
        logger.info("Database transaction rolled back due to error.")
    finally:
        logger.info(f"Deletion process for {user_email} finished.")

async def main():
    if len(sys.argv) < 2:
        logger.error("Usage: python scripts/delete_user_by_email.py <user_email>")
        return

    user_email_to_delete = sys.argv[1]

    async with AsyncSessionLocal() as db_session:
        try:
            await delete_user_and_associated_data(db_session, user_email_to_delete)
        except Exception as e:
            logger.critical(f"Critical error in main execution for {user_email_to_delete}: {e}", exc_info=True)
        finally:
            pass

if __name__ == "__main__":
    asyncio.run(main())