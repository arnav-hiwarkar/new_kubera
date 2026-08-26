import uuid


def test_requirement_request_has_lifecycle_columns():
    from app.models.auditease import RequirementRequest, ExpectedFormat
    r = RequirementRequest(engagement_id=uuid.uuid4(), raised_by=uuid.uuid4(),
                           title="t", description="d")
    assert r.priority == 1
    assert r.expected_format == ExpectedFormat.any
    r.seq_number = 7
    assert r.requirement_id == "REQ-007"


def test_requirement_response_model_exists():
    from app.models.auditease import RequirementResponse
    resp = RequirementResponse(requirement_id=uuid.uuid4())
    assert resp.text_answer is None and resp.document_id is None
