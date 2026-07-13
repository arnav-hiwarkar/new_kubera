import os
import httpx
import time

BASE_URL = "http://localhost:8000"
INTERNAL_KEY = "change-me-internal-key"

def main():
    print("Running Live E2E tests for Notifications and Activity Log module...")
    
    with httpx.Client() as client:
        # 1. Create a company
        email = f"e2e_{int(time.time())}@example.com"
        print(f"Creating company with email: {email}")
        res = client.post(f"{BASE_URL}/api/v1/auth/companies", 
            headers={"X-Internal-Api-Key": INTERNAL_KEY},
            json={"name": "E2E Corp", "admin": {"email": email, "password": "password123"}}
        )
        res.raise_for_status()
        
        # 2. Login
        res = client.post(f"{BASE_URL}/api/v1/auth/company/login",
            json={"email": email, "password": "password123"}
        )
        res.raise_for_status()
        token = res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # 3. Fetch activity log
        print("Fetching activity log...")
        res = client.get(f"{BASE_URL}/api/v1/activity-log", headers=headers)
        res.raise_for_status()
        logs = res.json()
        print(f"Got {len(logs)} activity logs. (Expected some from user creation/login depending on backend hooks)")
        
        # 4. Fetch notifications
        print("Fetching notifications...")
        res = client.get(f"{BASE_URL}/api/v1/notifications", headers=headers)
        res.raise_for_status()
        notifs = res.json()
        print(f"Got {len(notifs)} notifications.")
        
        if len(notifs) > 0:
            print("Marking notification as read...")
            notif_id = notifs[0]["id"]
            res = client.patch(f"{BASE_URL}/api/v1/notifications/{notif_id}/read", headers=headers)
            res.raise_for_status()
            read_notif = res.json()
            assert read_notif["read_at"] is not None
            print("Successfully marked notification as read.")
        
        print("E2E Tests Passed successfully!")

if __name__ == "__main__":
    main()
