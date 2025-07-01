import asyncio
import sys
import os
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import text, delete, or_, update
import logging

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Adjust path for script execution
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import AsyncSessionLocal
from app.models.user import User
from app.models.profile import UserProfile
from app.models.set_password_token import SetPasswordToken
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
        # 1. Get the user by email to find their ID
        user_stmt = select(User).where(User.email == user_email)
        user_result = await db.execute(user_stmt)
        user = user_result.scalar_one_or_none()

        if not user:
            logger.info(f"User with email {user_email} not found.")
            return

        user_id = user.id
        logger.info(f"Found user ID: {user_id} for email: {user_email}")

        # If user is a CORP_ADMIN, handle the company and its employees
        if user.role == "CORP_ADMIN" and user.company_id:
            company_id_to_delete = user.company_id
            logger.info(f"User is a CORP_ADMIN for company {company_id_to_delete}. Unlinking employees...")
            
            # Unlink all users from this company before deleting it
            await db.execute(
                update(User)
                .where(User.company_id == company_id_to_delete)
                .values(company_id=None)
            )
            logger.info(f"Finished unlinking employees from company {company_id_to_delete}.")

            # Find and delete spaces (SpaceNodes) associated with this company
            spaces_to_delete_stmt = select(SpaceNode).where(SpaceNode.company_id == company_id_to_delete)
            spaces_result = await db.execute(spaces_to_delete_stmt)
            spaces_to_delete = spaces_result.scalars().all()
            
            if spaces_to_delete:
                space_ids_to_delete = [s.id for s in spaces_to_delete]
                logger.info(f"Found spaces {space_ids_to_delete} linked to company {company_id_to_delete}. Deleting dependencies...")

                # Unlink all users from these spaces
                await db.execute(
                    update(User).where(User.space_id.in_(space_ids_to_delete)).values(space_id=None)
                )
                # Delete all interests associated with these spaces
                await db.execute(delete(Interest).where(Interest.space_id.in_(space_ids_to_delete)))
                # Delete all workstation assignments within these spaces
                await db.execute(delete(WorkstationAssignment).where(WorkstationAssignment.space_id.in_(space_ids_to_delete)))
                # Delete all workstations within these spaces
                await db.execute(delete(Workstation).where(Workstation.space_id.in_(space_ids_to_delete)))

                # Now delete the SpaceNodes
                await db.execute(delete(SpaceNode).where(SpaceNode.id.in_(space_ids_to_delete)))
                logger.info(f"Finished deleting spaces {space_ids_to_delete} and their dependencies.")

            logger.info(f"Deleting company {company_id_to_delete}...")
            await db.execute(delete(Company).where(Company.id == company_id_to_delete))
            logger.info("Company deletion executed.")

        # If user is a STARTUP_ADMIN, handle the startup and its members
        if user.role == "STARTUP_ADMIN" and user.startup_id:
            startup_id_to_delete = user.startup_id
            logger.info(f"User is a STARTUP_ADMIN for startup {startup_id_to_delete}. Unlinking members...")

            # Set startup_id to NULL for all members of this startup
            await db.execute(
                update(User)
                .where(User.startup_id == startup_id_to_delete)
                .values(startup_id=None)
            )
            logger.info(f"Finished unlinking members from startup {startup_id_to_delete}.")

            logger.info(f"Deleting startup {startup_id_to_delete}...")
            await db.execute(delete(Startup).where(Startup.id == startup_id_to_delete))
            logger.info("Startup deletion executed.")

        # 2. Delete associated data (order might matter based on FK constraints)
        
        logger.info(f"Deleting Invitations for user_id: {user_id}...")
        await db.execute(delete(Invitation).where(
            or_(
                Invitation.accepted_by_user_id == user_id,
                Invitation.invited_by_user_id == user_id,
                Invitation.revoked_by_admin_id == user_id,
                Invitation.approved_by_admin_id == user_id,
                Invitation.email == user_email
            )
        ))
        logger.info("Invitation deletion executed.")
        
        logger.info(f"Deleting Interests for user_id: {user_id}...")
        await db.execute(delete(Interest).where(Interest.user_id == user_id))
        logger.info("Interest deletion executed.")

        logger.info(f"Deleting Connections for user_id: {user_id}...")
        await db.execute(delete(Connection).where(or_(Connection.requester_id == user_id, Connection.recipient_id == user_id)))
        logger.info("Connection deletion executed.")

        logger.info(f"Finding ChatMessages sent by user_id: {user_id} to delete their reactions first...")
        messages_sent_by_user = await db.execute(select(ChatMessage.id).where(ChatMessage.sender_id == user_id))
        message_ids = messages_sent_by_user.scalars().all()

        if message_ids:
            logger.info(f"Deleting MessageReactions for messages sent by user {user_id}...")
            await db.execute(delete(MessageReaction).where(MessageReaction.message_id.in_(message_ids)))
            logger.info("MessageReaction deletion for user's messages executed.")

        logger.info(f"Deleting MessageReactions made by user_id: {user_id}...")
        await db.execute(delete(MessageReaction).where(MessageReaction.user_id == user_id))
        logger.info("MessageReaction deletion executed.")
        
        logger.info(f"Deleting ConversationParticipants for user_id: {user_id}...")
        await db.execute(delete(ConversationParticipant).where(ConversationParticipant.user_id == user_id))
        logger.info("ConversationParticipant deletion executed.")
        
        logger.info(f"Deleting ChatMessages for user_id: {user_id}...")
        await db.execute(delete(ChatMessage).where(ChatMessage.sender_id == user_id))
        logger.info("ChatMessage deletion executed.")

        logger.info(f"Deleting WorkstationAssignments for user_id: {user_id}...")
        await db.execute(delete(WorkstationAssignment).where(WorkstationAssignment.user_id == user_id))
        logger.info("WorkstationAssignment deletion executed.")

        logger.info(f"Deleting notifications for user_id: {user_id}...")
        delete_notif_stmt = Notification.__table__.delete().where(
            or_(
                Notification.user_id == user_id, 
                Notification.related_entity_id == user_id,
                Notification.sender_id == user_id
            )
        )
        await db.execute(delete_notif_stmt)
        logger.info("Notification deletion executed.")

        logger.info(f"Deleting VerificationToken for user_id: {user_id}...")
        delete_vt_stmt = VerificationToken.__table__.delete().where(VerificationToken.user_id == user_id)
        await db.execute(delete_vt_stmt)
        logger.info("VerificationToken deletion executed.")

        logger.info(f"Deleting SetPasswordToken for user_id: {user_id}...")
        delete_spt_stmt = SetPasswordToken.__table__.delete().where(SetPasswordToken.user_id == user_id)
        await db.execute(delete_spt_stmt)
        logger.info("SetPasswordToken deletion executed.")

        logger.info(f"Deleting UserProfile for user_id: {user_id}...")
        delete_profile_stmt = UserProfile.__table__.delete().where(UserProfile.user_id == user_id)
        await db.execute(delete_profile_stmt)
        logger.info("UserProfile deletion executed.")
        
        # 3. Finally, delete the user
        logger.info(f"Deleting user record for user_id: {user_id} (email: {user_email})...")
        delete_user_stmt = User.__table__.delete().where(User.id == user_id)
        await db.execute(delete_user_stmt)
        logger.info("User record deletion executed.")

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