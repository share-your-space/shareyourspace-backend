import uvicorn
from dotenv import load_dotenv

# Load environment variables from .env file before importing the app
load_dotenv()

# Now it's safe to import the app and settings
from app.main import app

if __name__ == "__main__":
    # When running directly, use uvicorn to serve the app
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True) 