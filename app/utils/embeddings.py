import google.generativeai as genai
import logging
from typing import List

from app.core.config import settings

logger = logging.getLogger(__name__)

# Configure the client
if settings.GOOGLE_AI_API_KEY:
    genai.configure(api_key=settings.GOOGLE_AI_API_KEY)
else:
    logger.warning("GOOGLE_AI_API_KEY not found in settings. Embedding generation will fail.")

# Define the model name
EMBEDDING_MODEL = "models/text-embedding-004"

def generate_embedding(text: str) -> List[float] | None:
    """Generates an embedding for the given text using the Google AI API."""
    if not settings.GOOGLE_AI_API_KEY:
        logger.error("Cannot generate embedding: GOOGLE_AI_API_KEY is not configured.")
        return None

    try:
        # Clean the text - embedding model prefers non-empty strings
        cleaned_text = text.strip()
        if not cleaned_text:
            logger.warning("Input text for embedding is empty after stripping.")
            # Return a zero vector or None, depending on desired handling
            # Returning None might be safer to indicate failure/empty input
            return None 
            # Alternative: return [0.0] * 768 # text-embedding-004 dimension is 768

        result = genai.embed_content(
            model=EMBEDDING_MODEL,
            content=cleaned_text,
            task_type="RETRIEVAL_DOCUMENT" # Use RETRIEVAL_DOCUMENT for searchable embeddings
        )
        return result['embedding']
    except Exception as e:
        logger.error(f"Error generating embedding: {e}", exc_info=True)
        return None 