import pytest
from pydantic import ValidationError
from app.schemas.auth import AuditorRegister, ActivationRequest
from app.schemas.users import UserCreate, UserChangePasswordRequest

def test_auditor_register_weak_password():
    with pytest.raises(ValidationError):
        AuditorRegister(email="test@test.com", password="weak", name="Test")

def test_activation_request_weak_password():
    with pytest.raises(ValidationError):
        ActivationRequest(email="test@test.com", activation_key="key", password="weak", full_name="Test")

def test_user_create_weak_password():
    with pytest.raises(ValidationError):
        UserCreate(email="test@test.com", password="weak", full_name="Test", role="user")

def test_user_change_password_weak():
    with pytest.raises(ValidationError):
        UserChangePasswordRequest(old_password="old", new_password="weak", confirm_password="weak")
