import os
import httpx
import time

BASE_URL = "http://localhost:8000"
INTERNAL_KEY = "change-me-internal-key"

def main():
    print("Running Live E2E tests for Compliance module...")
    
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
        
        # 3. Create a ROC Document Type
        print("Creating ROC document type...")
        res = client.post(f"{BASE_URL}/api/v1/roc/document-types", headers=headers, json={
            "name": "Annual Filing",
            "due_date_rule": "Within 30 days of AGM",
            "metadata_schema": {"fields": [{"key": "financial_year", "label": "Financial Year", "type": "text", "required": True}]}
        })
        res.raise_for_status()
        doc_type = res.json()
        doc_type_id = doc_type["id"]
        print(f"Created doc type: {doc_type_id}")
        
        # 4. Upload a template (mock file upload to vault)
        print("Finding or creating ROC bucket...")
        buckets = client.get(f"{BASE_URL}/api/v1/docvault/buckets", headers=headers).json()
        roc_bucket = next((b for b in buckets if b["name"] == "ROC Compliance"), None)
        if not roc_bucket:
            roc_bucket = client.post(f"{BASE_URL}/api/v1/docvault/buckets", headers=headers, json={"name": "ROC Compliance"}).json()
        bucket_id = roc_bucket["id"]
        
        print("Uploading file to docVault...")
        res = client.post(f"{BASE_URL}/api/v1/docvault/documents", headers=headers, data={"title": "test_doc.pdf", "bucket_id": bucket_id}, files={
            "file": ("test_doc.pdf", b"%PDF-1.4 mock pdf content", "application/pdf")
        })
        res.raise_for_status()
        doc_id = res.json()["id"]
        print(f"Uploaded doc: {doc_id}")
        
        # 5. Create a ROC record
        print("Creating ROC record...")
        res = client.post(f"{BASE_URL}/api/v1/roc/meeting-records", headers=headers, json={
            "doc_type_id": doc_type_id,
            "document_id": doc_id,
            "record_date": "2026-07-15",
            "structured_metadata": {"financial_year": "2026-2027"}
        })
        res.raise_for_status()
        record_id = res.json()["id"]
        print(f"Created record: {record_id}")
        
        # 6. Fetch records and verify isolation
        print("Fetching ROC records...")
        res = client.get(f"{BASE_URL}/api/v1/roc/meeting-records", headers=headers)
        records = res.json()
        assert len(records) == 1
        assert records[0]["id"] == record_id
        
        print("Fetching SecretarialEase records (should be empty)...")
        res = client.get(f"{BASE_URL}/api/v1/secretarial/meeting-records", headers=headers)
        sec_records = res.json()
        assert len(sec_records) == 0
        
        # 7. Attempt to delete the Document Type (should 409)
        print("Attempting to delete document type with active records...")
        res = client.delete(f"{BASE_URL}/api/v1/roc/document-types/{doc_type_id}", headers=headers)
        assert res.status_code == 409
        print("Delete blocked as expected (409).")
        
        print("E2E Tests Passed successfully!")

if __name__ == "__main__":
    main()
