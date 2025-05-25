import resend
import logging
from app.core.config import settings
from typing import Optional # Added for Optional type hint

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def send_email(to: str, subject: str, html_content: str) -> None:
    """Sends an email using the Resend service."""
    if not settings.RESEND_API_KEY:
        logger.error("RESEND_API_KEY is not configured. Cannot send email.")
        # In a real application, you might want to raise an exception
        # or handle this more gracefully depending on requirements.
        return

    try:
        # Correctly extract the secret value from SecretStr
        resend.api_key = settings.RESEND_API_KEY.get_secret_value()
        params = {
            "from": "ShareYourSpace Onboarding <onboarding@shareyourspace.app>",
            "to": [to],
            "subject": subject,
            "html": html_content,
        }
        email = resend.Emails.send(params)
        logger.info(f"Email sent successfully to {to}. Message ID: {email['id']}")
    except Exception as e:
        logger.error(f"Failed to send email to {to}. Error: {e}")
        # Handle exceptions appropriately (e.g., retry logic, alerts)
        # For now, we just log, but the caller might need to know if it failed.
        raise # Re-raise the exception so the caller can handle it

def send_startup_invitation_email(
    to_email: str, 
    token: str, 
    startup_name: str,
    invited_by_name: str, # Name of the Corp Admin who approved
    full_name: Optional[str] = None 
) -> None:
    """Sends an invitation email to a user to join a startup."""
    invitation_url = f"{settings.FRONTEND_URL}/accept-invitation/{token}"
    
    user_greeting = f"Hi {full_name}," if full_name else "Hello,"

    subject = f"Invitation to Join {startup_name} on ShareYourSpace"
    html_content = f"""
    <p>{user_greeting}</p>
    <p>{invited_by_name} has invited you to join the startup "<strong>{startup_name}</strong>" on ShareYourSpace.</p>
    <p>ShareYourSpace is a platform for startups, freelancers, and corporate teams to connect and collaborate within shared workspaces.</p>
    <p>To accept this invitation and create your account, please click the link below:</p>
    <p><a href="{invitation_url}">{invitation_url}</a></p>
    <p>This link will expire in 7 days.</p>
    <p>If you were not expecting this invitation, please ignore this email.</p>
    <p>Welcome aboard!<br>The ShareYourSpace Team</p>
    """
    try:
        send_email(to=to_email, subject=subject, html_content=html_content)
        logger.info(f"Startup invitation email successfully sent to {to_email} for startup {startup_name}.")
    except Exception as e:
        logger.error(f"Failed to send startup invitation email to {to_email} for startup {startup_name}. Error: {e}")
        # The initial send_email function already logs and re-raises.
        # We can re-raise here as well if the caller (router) needs to act on this failure.
        raise 