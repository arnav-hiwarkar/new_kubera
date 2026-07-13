import pytest
from httpx import AsyncClient

from tests.conftest import create_test_company, get_company_token
from app.models.compliance import ComplianceDomain

@pytest.mark.asyncio
async def test_secretarial_flow(client: AsyncClient):
    await create_test_company(client, email="sec@a.com", password="pass")
    token = await get_company_token(client, email="sec@a.com", password="pass")
    headers = {"Authorization": f"Bearer {token}"}

    # Create document type
    dt_data = {
        "name": "Minutes of Meeting",
        "metadata_schema": {"type": "object", "properties": {"date": {"type": "string"}}}
    }
    resp = await client.post("/api/v1/secretarial/document-types", json=dt_data, headers=headers)
    assert resp.status_code == 201
    dt_id = resp.json()["id"]
    
    # List document types
    resp = await client.get("/api/v1/secretarial/document-types", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) >= 1
    
    # Create meeting record
    mr_data = {
        "doc_type_id": dt_id,
        "structured_metadata": {"date": "2023-10-01"}
    }
    resp = await client.post("/api/v1/secretarial/meeting-records", json=mr_data, headers=headers)
    assert resp.status_code == 201
    mr_id = resp.json()["id"]
    
    # List meeting records
    resp = await client.get("/api/v1/secretarial/meeting-records", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_roc_flow(client: AsyncClient):
    await create_test_company(client, email="roc@a.com", password="pass")
    token = await get_company_token(client, email="roc@a.com", password="pass")
    headers = {"Authorization": f"Bearer {token}"}

    # Create document type
    dt_data = {
        "name": "AOC-4",
        "due_date_rule": "30 days from AGM"
    }
    resp = await client.post("/api/v1/roc/document-types", json=dt_data, headers=headers)
    assert resp.status_code == 201
    dt_id = resp.json()["id"]
    
    # Create meeting record (roc filing)
    mr_data = {
        "doc_type_id": dt_id
    }
    resp = await client.post("/api/v1/roc/meeting-records", json=mr_data, headers=headers)
    assert resp.status_code == 201
    
    # List
    resp = await client.get("/api/v1/roc/meeting-records", headers=headers)
    assert len(resp.json()) == 1
    
    # Secretarial should not see ROC records
    resp = await client.get("/api/v1/secretarial/meeting-records", headers=headers)
    assert len(resp.json()) == 0


@pytest.mark.asyncio
async def test_cross_tenant_compliance(client: AsyncClient):
    await create_test_company(client, email="c1@a.com", password="pass")
    token1 = await get_company_token(client, email="c1@a.com", password="pass")
    h1 = {"Authorization": f"Bearer {token1}"}
    
    await create_test_company(client, email="c2@a.com", password="pass")
    token2 = await get_company_token(client, email="c2@a.com", password="pass")
    h2 = {"Authorization": f"Bearer {token2}"}

    # C1 creates dt
    resp = await client.post("/api/v1/secretarial/document-types", json={"name": "C1 Doc"}, headers=h1)
    dt_id = resp.json()["id"]
    
    # C2 cannot see C1 dt
    resp = await client.get("/api/v1/secretarial/document-types", headers=h2)
    assert not any(d["name"] == "C1 Doc" for d in resp.json())
    
    # C2 cannot update C1 dt
    resp = await client.put(f"/api/v1/secretarial/document-types/{dt_id}", json={"name": "Hacked"}, headers=h2)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_record_date_roundtrip(client: AsyncClient):
    await create_test_company(client, email="rd@a.com", password="pass")
    headers = {"Authorization": f"Bearer {await get_company_token(client, email='rd@a.com', password='pass')}"}

    dt_id = (await client.post("/api/v1/roc/document-types", json={"name": "Monthly Return"}, headers=headers)).json()["id"]
    resp = await client.post(
        "/api/v1/roc/meeting-records",
        json={"doc_type_id": dt_id, "record_date": "2026-07-05", "structured_metadata": {"ref": "R-1"}},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["record_date"] == "2026-07-05"

    rows = (await client.get("/api/v1/roc/meeting-records", headers=headers)).json()
    assert rows[0]["record_date"] == "2026-07-05"


@pytest.mark.asyncio
async def test_delete_type_guarded_by_records(client: AsyncClient):
    await create_test_company(client, email="del@a.com", password="pass")
    headers = {"Authorization": f"Bearer {await get_company_token(client, email='del@a.com', password='pass')}"}

    # Type with a record cannot be deleted
    used = (await client.post("/api/v1/secretarial/document-types", json={"name": "Used"}, headers=headers)).json()["id"]
    await client.post("/api/v1/secretarial/meeting-records", json={"doc_type_id": used}, headers=headers)
    resp = await client.delete(f"/api/v1/secretarial/document-types/{used}", headers=headers)
    assert resp.status_code == 409

    # An empty type deletes fine
    empty = (await client.post("/api/v1/secretarial/document-types", json={"name": "Empty"}, headers=headers)).json()["id"]
    resp = await client.delete(f"/api/v1/secretarial/document-types/{empty}", headers=headers)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_record_rejects_wrong_domain_type(client: AsyncClient):
    await create_test_company(client, email="dom@a.com", password="pass")
    headers = {"Authorization": f"Bearer {await get_company_token(client, email='dom@a.com', password='pass')}"}
    roc_dt = (await client.post("/api/v1/roc/document-types", json={"name": "ROC only"}, headers=headers)).json()["id"]
    # Using a ROC type under the secretarial domain must be rejected.
    resp = await client.post("/api/v1/secretarial/meeting-records", json={"doc_type_id": roc_dt}, headers=headers)
    assert resp.status_code == 400
