import requests
import os
import json # For printing JSON nicely

BASE_URL = "http://localhost:8000/api/v1"
LOGIN_URL = f"{BASE_URL}/auth/login"
PROFILE_URL = f"{BASE_URL}/users/me/profile"

# Target User for this specific test run
TARGET_USERNAME = "corporate_pending@example.com"
TARGET_PASSWORD = "password123"

PROFILE_PAYLOAD = {
    "title": "Corporate Innovation Lead", 
    "bio": "Driving innovation within large organizations by connecting with startups and freelancers. Keen on AI applications.", 
    "skills_expertise": ["Project Management", "AI Strategy", "Corporate Innovation", "Networking"], 
    "industry_focus": ["Technology", "Enterprise Solutions"], 
    "project_interests_goals": "Finding agile talent for new tech initiatives.", 
    "collaboration_preferences": ["Brainstorming sessions", "Pilot projects"], 
    "tools_technologies": ["Jira", "Confluence", "Microsoft Suite"]
}

def run_profile_update():
    access_token = None
    print(f"--- 1. Attempting to log in as {TARGET_USERNAME} ---")
    login_payload = {
        'username': TARGET_USERNAME,
        'password': TARGET_PASSWORD
    }
    try:
        response = requests.post(LOGIN_URL, data=login_payload)
        response.raise_for_status()
        token_data = response.json()
        access_token = token_data.get('access_token')
        if not access_token:
            print("Login failed or access_token not found.")
            print(f"Response: {response.status_code} {response.text}")
            return
        print(f"Login successful. Token: {access_token}")

    except requests.exceptions.RequestException as e:
        print(f"Login request error: {e}")
        return
    except Exception as e:
        print(f"Login unexpected error: {e}")
        return

    if not access_token:
        print("Cannot proceed without access token.")
        return

    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }

    print(f"\n--- 2. Attempting to update profile for {TARGET_USERNAME} ---")
    try:
        response = requests.put(PROFILE_URL, headers=headers, json=PROFILE_PAYLOAD)
        print(f"PUT {PROFILE_URL} Status: {response.status_code}")
        try:
            print(f"Response JSON: {json.dumps(response.json(), indent=2)}")
            if response.status_code == 200:
                print("SUCCESS: Profile updated successfully.")
            else:
                print("FAILURE: Failed to update profile.")
        except json.JSONDecodeError:
            print(f"Response Text: {response.text}")
            print("FAILURE: Failed to update profile (non-JSON response).")
            
    except requests.exceptions.RequestException as e:
        print(f"PUT {PROFILE_URL} request error: {e}")
    except Exception as e:
        print(f"PUT {PROFILE_URL} unexpected error: {e}")

if __name__ == "__main__":
    # This script is now focused on updating a specific user's profile
    # Comment out or remove other test calls if not needed for this run
    run_profile_update() 