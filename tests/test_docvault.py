import pytest
from httpx import AsyncClient

from tests.conftest import create_test_company, get_company_token

@pytest.mark.asyncio
async def test_bucket_crud(client: AsyncClient):
    # Setup company and get token
    await create_test_company(client, email="b1@a.com", password="pass")
    token = await get_company_token(client, email="b1@a.com", password="pass")
    headers = {"Authorization": f"Bearer {token}"}

    # Create bucket
    resp = await client.post("/api/v1/docvault/buckets", json={"name": "Financials"}, headers=headers)
    assert resp.status_code == 201
    bucket_id = resp.json()["id"]

    # List buckets
    resp = await client.get("/api/v1/docvault/buckets", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["name"] == "Financials"

    # Delete bucket
    resp = await client.delete(f"/api/v1/docvault/buckets/{bucket_id}", headers=headers)
    assert resp.status_code == 204

    # List again
    resp = await client.get("/api/v1/docvault/buckets", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 0


@pytest.mark.asyncio
async def test_document_upload_and_download(client: AsyncClient):
    await create_test_company(client, name="DocCo", email="doc@co.com", password="pass")
    token = await get_company_token(client, email="doc@co.com", password="pass")
    headers = {"Authorization": f"Bearer {token}"}

    # Upload document
    files = {'file': ('test.txt', b'hello world, this is a secret document', 'text/plain')}
    data = {'title': 'My Secret Doc', 'tags': 'secret,test'}
    
    resp = await client.post("/api/v1/docvault/documents", data=data, files=files, headers=headers)
    assert resp.status_code == 201
    doc = resp.json()
    assert doc["title"] == "My Secret Doc"
    assert "secret" in doc["tags"]
    assert doc["status"] == "uploaded"
    assert len(doc["versions"]) == 1
    
    doc_id = doc["id"]
    version_id = doc["versions"][0]["id"]
    
    # Download document
    resp = await client.get(f"/api/v1/docvault/documents/{doc_id}/download", headers=headers)
    assert resp.status_code == 200
    assert resp.content == b'hello world, this is a secret document'
    
    # Upload new version
    files2 = {'file': ('test2.txt', b'version 2 secret', 'text/plain')}
    resp = await client.post(f"/api/v1/docvault/documents/{doc_id}/versions", files=files2, headers=headers)
    assert resp.status_code == 200
    doc = resp.json()
    assert len(doc["versions"]) == 2
    
    # Download V2
    resp = await client.get(f"/api/v1/docvault/documents/{doc_id}/download", headers=headers)
    assert resp.status_code == 200
    assert resp.content == b'version 2 secret'
    
    # Download V1 explicitly
    resp = await client.get(f"/api/v1/docvault/documents/{doc_id}/download?version_id={version_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.content == b'hello world, this is a secret document'


@pytest.mark.asyncio
async def test_document_cross_tenant_leak(client: AsyncClient):
    # Company A
    await create_test_company(client, name="CompA", email="a@co.com", password="pass")
    token_a = await get_company_token(client, email="a@co.com", password="pass")
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # Company B
    await create_test_company(client, name="CompB", email="b@co.com", password="pass")
    token_b = await get_company_token(client, email="b@co.com", password="pass")
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # A creates bucket and document
    resp = await client.post("/api/v1/docvault/buckets", json={"name": "A-Bucket"}, headers=headers_a)
    bucket_id = resp.json()["id"]

    files = {'file': ('a.txt', b'a data', 'text/plain')}
    resp = await client.post("/api/v1/docvault/documents", data={'title': 'A-Doc', 'bucket_id': bucket_id}, files=files, headers=headers_a)
    doc_id = resp.json()["id"]

    # B lists buckets -> should not see A's
    resp = await client.get("/api/v1/docvault/buckets", headers=headers_b)
    assert len(resp.json()) == 0

    # B lists docs -> should not see A's
    resp = await client.get("/api/v1/docvault/documents", headers=headers_b)
    assert len(resp.json()) == 0

    # B gets specific doc -> 404
    resp = await client.get(f"/api/v1/docvault/documents/{doc_id}", headers=headers_b)
    assert resp.status_code == 404

    # B downloads specific doc -> 404
    resp = await client.get(f"/api/v1/docvault/documents/{doc_id}/download", headers=headers_b)
    assert resp.status_code == 404
