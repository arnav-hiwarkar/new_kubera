import pytest
from app.models.docvault import Document, DocumentStatus

def test_document_model_has_approval_fields():
    assert hasattr(Document, "approver_id")
    assert hasattr(Document, "approval_requested_at")
    assert hasattr(Document, "approved_at")
    assert hasattr(Document, "approval_notes")
