import resend
import logging
from app.core.config import settings

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