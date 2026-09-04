import uuid
from datetime import datetime, timezone, timedelta
from app.models.auditease import PendingAuditorInvite, FULL_AREA_PERMISSIONS
from app.models.auditor import Auditor


def test_pending_auditor_invite_model_has_required_columns():
    invite = PendingAuditorInvite(
        engagement_id=uuid.uuid4(),
        email="auditor@firm.com",
        token_hash="fake_hash",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        area_permissions=dict(FULL_AREA_PERMISSIONS),
    )
    assert hasattr(invite, "token_hash")
    assert hasattr(invite, "expires_at")
    assert hasattr(invite, "area_permissions")
    assert not hasattr(invite, "token")


def test_auditor_model_has_case_insensitive_index():
    index_names = [idx.name for idx in Auditor.__table__.indexes]
    assert "uq_auditors_email_lower" in index_names
