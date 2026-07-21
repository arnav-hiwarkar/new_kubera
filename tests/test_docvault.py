import pytest
from httpx import AsyncClient

from tests.conftest import create_test_company, get_company_token


async def _create_member(
    client: AsyncClient,
    admin_headers: dict,
    email: str,
    password: str = "member1234",
    full_name: str = "Member User",
    role: str = "employee",
    modules: list[str] | None = None,
) -> str:
    """Admin creates a company user; returns the new user's id."""
    resp = await client.post(
        "/api/v1/users",
        json={
            "email": email,
            "password": password,
            "full_name": full_name,
            "role": role,
            "accessible_modules": modules if modules is not None else ["docvault"],
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]

@pytest.mark.asyncio
async def test_bucket_crud(client: AsyncClient):
    # Setup company and get token
    await create_test_company(client, email="b1@a.com", password="pass1234")
    token = await get_company_token(client, email="b1@a.com", password="pass1234")
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
    await create_test_company(client, name="DocCo", email="doc@co.com", password="pass1234")
    token = await get_company_token(client, email="doc@co.com", password="pass1234")
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
    await create_test_company(client, name="CompA", email="a@co.com", password="pass1234")
    token_a = await get_company_token(client, email="a@co.com", password="pass1234")
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # Company B
    await create_test_company(client, name="CompB", email="b@co.com", password="pass1234")
    token_b = await get_company_token(client, email="b@co.com", password="pass1234")
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


# === Per-bucket access control ===


async def _setup_company_with_members(client: AsyncClient):
    """Admin + two non-admin docvault members (user A and user B). Returns
    (admin_headers, a_headers, b_headers, a_id, b_id)."""
    await create_test_company(client, name="AccessCo", email="admin@acc.com", password="pass1234")
    admin_token = await get_company_token(client, email="admin@acc.com", password="pass1234")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    a_id = await _create_member(client, admin_headers, "usera@acc.com")
    b_id = await _create_member(client, admin_headers, "userb@acc.com")
    a_token = await get_company_token(client, email="usera@acc.com", password="member1234")
    b_token = await get_company_token(client, email="userb@acc.com", password="member1234")
    return (
        admin_headers,
        {"Authorization": f"Bearer {a_token}"},
        {"Authorization": f"Bearer {b_token}"},
        a_id,
        b_id,
    )


@pytest.mark.asyncio
async def test_restricted_bucket_hidden_from_non_granted_user(client: AsyncClient):
    admin_headers, a_headers, b_headers, a_id, b_id = await _setup_company_with_members(client)

    # Admin creates a bucket + document in it.
    resp = await client.post("/api/v1/docvault/buckets", json={"name": "Board"}, headers=admin_headers)
    bucket_id = resp.json()["id"]
    files = {"file": ("m.txt", b"board minutes", "text/plain")}
    resp = await client.post(
        "/api/v1/docvault/documents",
        data={"title": "Minutes", "bucket_id": bucket_id},
        files=files,
        headers=admin_headers,
    )
    doc_id = resp.json()["id"]

    # Both members see it while visibility is `everyone` (default).
    assert len(((await client.get("/api/v1/docvault/buckets", headers=a_headers)).json())) == 1
    assert len(((await client.get("/api/v1/docvault/buckets", headers=b_headers)).json())) == 1

    # Restrict to user A only.
    resp = await client.patch(
        f"/api/v1/docvault/buckets/{bucket_id}/access",
        json={"visibility": "restricted", "user_ids": [a_id]},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["visibility"] == "restricted"
    assert resp.json()["access_user_ids"] == [a_id]

    # User A still sees the bucket, its doc, and can download it.
    assert [b["id"] for b in (await client.get("/api/v1/docvault/buckets", headers=a_headers)).json()] == [bucket_id]
    assert len((await client.get("/api/v1/docvault/documents", headers=a_headers)).json()) == 1
    assert (await client.get(f"/api/v1/docvault/documents/{doc_id}/download", headers=a_headers)).status_code == 200

    # User B sees neither the bucket nor its document, and is 404'd on direct access.
    assert (await client.get("/api/v1/docvault/buckets", headers=b_headers)).json() == []
    assert (await client.get("/api/v1/docvault/documents", headers=b_headers)).json() == []
    assert (await client.get(f"/api/v1/docvault/documents/{doc_id}", headers=b_headers)).status_code == 404
    assert (await client.get(f"/api/v1/docvault/documents/{doc_id}/download", headers=b_headers)).status_code == 404
    # And B cannot find it via search.
    assert (await client.get("/api/v1/docvault/documents/search?q=Minutes", headers=b_headers)).json() == []
    assert len((await client.get("/api/v1/docvault/documents/search?q=Minutes", headers=a_headers)).json()) == 1

    # Admin always sees everything regardless of restriction.
    assert len((await client.get("/api/v1/docvault/buckets", headers=admin_headers)).json()) == 1
    assert len((await client.get("/api/v1/docvault/documents", headers=admin_headers)).json()) == 1


@pytest.mark.asyncio
async def test_uncategorized_docs_visible_to_all(client: AsyncClient):
    admin_headers, a_headers, b_headers, a_id, b_id = await _setup_company_with_members(client)

    # A restricted bucket + a bucketless (uncategorized) doc.
    resp = await client.post("/api/v1/docvault/buckets", json={"name": "Secret"}, headers=admin_headers)
    bucket_id = resp.json()["id"]
    await client.patch(
        f"/api/v1/docvault/buckets/{bucket_id}/access",
        json={"visibility": "restricted", "user_ids": [a_id]},
        headers=admin_headers,
    )
    files = {"file": ("free.txt", b"open doc", "text/plain")}
    await client.post("/api/v1/docvault/documents", data={"title": "Uncat"}, files=files, headers=admin_headers)

    # User B (not granted) still sees the uncategorized doc, but no restricted bucket.
    docs_b = (await client.get("/api/v1/docvault/documents", headers=b_headers)).json()
    assert [d["title"] for d in docs_b] == ["Uncat"]
    assert (await client.get("/api/v1/docvault/buckets", headers=b_headers)).json() == []


@pytest.mark.asyncio
async def test_creator_loses_access_when_restricted_away(client: AsyncClient):
    admin_headers, a_headers, b_headers, a_id, b_id = await _setup_company_with_members(client)

    # User A creates a bucket (default `everyone`) and puts a doc in it.
    resp = await client.post("/api/v1/docvault/buckets", json={"name": "A-owned"}, headers=a_headers)
    bucket_id = resp.json()["id"]
    files = {"file": ("c.txt", b"creator doc", "text/plain")}
    await client.post(
        "/api/v1/docvault/documents",
        data={"title": "CreatorDoc", "bucket_id": bucket_id},
        files=files,
        headers=a_headers,
    )

    # Admin restricts it to *only* user B, excluding the creator A.
    await client.patch(
        f"/api/v1/docvault/buckets/{bucket_id}/access",
        json={"visibility": "restricted", "user_ids": [b_id]},
        headers=admin_headers,
    )

    # Creator A no longer sees the bucket or its document — creating it grants no
    # standing access once it's restricted away from them.
    assert bucket_id not in [b["id"] for b in (await client.get("/api/v1/docvault/buckets", headers=a_headers)).json()]
    assert [d["title"] for d in (await client.get("/api/v1/docvault/documents", headers=a_headers)).json()] == []

    # User B (on the list) does see it.
    assert bucket_id in [b["id"] for b in (await client.get("/api/v1/docvault/buckets", headers=b_headers)).json()]
    assert [d["title"] for d in (await client.get("/api/v1/docvault/documents", headers=b_headers)).json()] == ["CreatorDoc"]


@pytest.mark.asyncio
async def test_upload_and_move_into_inaccessible_bucket_rejected(client: AsyncClient):
    admin_headers, a_headers, b_headers, a_id, b_id = await _setup_company_with_members(client)

    resp = await client.post("/api/v1/docvault/buckets", json={"name": "Locked"}, headers=admin_headers)
    bucket_id = resp.json()["id"]
    await client.patch(
        f"/api/v1/docvault/buckets/{bucket_id}/access",
        json={"visibility": "restricted", "user_ids": [a_id]},
        headers=admin_headers,
    )

    # User B cannot upload into a bucket they can't see.
    files = {"file": ("x.txt", b"x", "text/plain")}
    resp = await client.post(
        "/api/v1/docvault/documents",
        data={"title": "Sneaky", "bucket_id": bucket_id},
        files=files,
        headers=b_headers,
    )
    assert resp.status_code == 403

    # User B uploads an uncategorized doc, then tries to move it into the locked bucket.
    resp = await client.post("/api/v1/docvault/documents", data={"title": "Mine"}, files={"file": ("y.txt", b"y", "text/plain")}, headers=b_headers)
    doc_id = resp.json()["id"]
    resp = await client.patch(f"/api/v1/docvault/documents/{doc_id}", json={"bucket_id": bucket_id}, headers=b_headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_access_endpoint_is_admin_only(client: AsyncClient):
    admin_headers, a_headers, b_headers, a_id, b_id = await _setup_company_with_members(client)

    resp = await client.post("/api/v1/docvault/buckets", json={"name": "Board"}, headers=admin_headers)
    bucket_id = resp.json()["id"]

    # Non-admin cannot change access.
    resp = await client.patch(
        f"/api/v1/docvault/buckets/{bucket_id}/access",
        json={"visibility": "restricted", "user_ids": [a_id]},
        headers=a_headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_revert_restricted_to_everyone(client: AsyncClient):
    admin_headers, a_headers, b_headers, a_id, b_id = await _setup_company_with_members(client)

    resp = await client.post("/api/v1/docvault/buckets", json={"name": "Toggle"}, headers=admin_headers)
    bucket_id = resp.json()["id"]

    # Restrict to A, then open back to everyone -> B sees it again and grants are cleared.
    await client.patch(f"/api/v1/docvault/buckets/{bucket_id}/access", json={"visibility": "restricted", "user_ids": [a_id]}, headers=admin_headers)
    assert (await client.get("/api/v1/docvault/buckets", headers=b_headers)).json() == []

    resp = await client.patch(f"/api/v1/docvault/buckets/{bucket_id}/access", json={"visibility": "everyone", "user_ids": []}, headers=admin_headers)
    assert resp.json()["visibility"] == "everyone"
    assert resp.json()["access_user_ids"] == []
    assert bucket_id in [b["id"] for b in (await client.get("/api/v1/docvault/buckets", headers=b_headers)).json()]
