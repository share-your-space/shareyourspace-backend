import asyncio
from datetime import timedelta

# Adjust import path if necessary when running inside the container
# Assuming the script is run from /app/scripts and security.py is in /app/app/security.py
# For direct execution in container with PYTHONPATH set up by poetry, this might work:
from app.security import get_password_hash, verify_password, create_access_token
from app.core.config import settings # Required for create_access_token

async def main():
    print("--- Testing Security Functions ---")

    # Test password hashing and verification
    test_password = "mysecretpassword123"
    hashed_password = get_password_hash(test_password)
    print(f"Original password: {test_password}")
    print(f"Hashed password: {hashed_password}")

    is_verified_correct = verify_password(test_password, hashed_password)
    print(f"Verification with correct password: {is_verified_correct}")

    is_verified_incorrect = verify_password("wrongpassword", hashed_password)
    print(f"Verification with incorrect password: {is_verified_incorrect}")

    if is_verified_correct and not is_verified_incorrect:
        print("✅ Password hashing and verification: PASSED")
    else:
        print("❌ Password hashing and verification: FAILED")

    # Test JWT creation
    # Ensure settings are loaded for SECRET_KEY and ALGORITHM
    print(f"Using SECRET_KEY: {'*' * len(settings.SECRET_KEY.get_secret_value()) if settings.SECRET_KEY else 'Not Set'}")
    print(f"Using ALGORITHM: {settings.ALGORITHM}")
    
    user_data = {"sub": "testuser@example.com", "user_id": 1}
    try:
        access_token = create_access_token(data=user_data)
        print(f"Generated JWT: {access_token[:30]}...{access_token[-30:]}") # Print snippet
        
        # Basic check if token is a non-empty string
        if access_token and isinstance(access_token, str):
             print("✅ JWT creation (basic check): PASSED")
        else:
            print("❌ JWT creation (basic check): FAILED - Token is empty or not a string")

    except Exception as e:
        print(f"❌ JWT creation: FAILED with error: {e}")
        # Attempt to load .env if running locally and config is not found
        from dotenv import load_dotenv
        load_dotenv()
        settings.reload() # Reload settings after loading .env
        print("Attempted to load .env and reload settings. Please check if .env is correctly configured and accessible.")
        print(f"After attempting .env load, SECRET_KEY: {'*' * len(settings.SECRET_KEY.get_secret_value()) if settings.SECRET_KEY and settings.SECRET_KEY.get_secret_value() else 'Not Set'}")


    print("--- Security Function Testing Complete ---")

if __name__ == "__main__":
    # Pytest-asyncio runs async tests directly, but for plain script execution:
    asyncio.run(main()) 