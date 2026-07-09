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
