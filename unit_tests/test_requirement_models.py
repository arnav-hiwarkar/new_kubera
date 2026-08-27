import uuid
from app.models.auditease import (
    RequirementRequest,
    RequirementResponse,
    RequirementResponseDocument,
    RequestStatus,
)


def test_requirement_request_columns_and_defaults():
    req = RequirementRequest(
        engagement_id=uuid.uuid4(),
        raised_by=uuid.uuid4(),
        description="Provide FY24 statements",
    )
    assert req.status == RequestStatus.open
    assert req.priority == 1
    assert req.due_date is None
    assert req.closed_by is None
    assert req.closed_at is None
    req.seq_number = 7
    assert req.requirement_id == "REQ-007"


def test_requirement_response_model():
    req_id = uuid.uuid4()
    resp = RequirementResponse(
        requirement_id=req_id,
        round_number=1,
        text_answer="Here is the explanation",
    )
    assert resp.requirement_id == req_id
    assert resp.round_number == 1
    assert resp.text_answer == "Here is the explanation"
    assert resp.responded_by is None


def test_requirement_response_document_model():
    resp_id = uuid.uuid4()
    doc = RequirementResponseDocument(
        response_id=resp_id,
        document_id=None,
        filename="bank_statement.pdf",
    )
    assert doc.response_id == resp_id
    assert doc.document_id is None
    assert doc.filename == "bank_statement.pdf"

