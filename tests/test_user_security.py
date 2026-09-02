import pytest
from pydantic import BaseModel, ValidationError
from app.services.user_security import validate_password_complexity, Password, PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH

class DummyModel(BaseModel):
    pwd: Password

def test_validate_password_complexity():
    # Length boundaries
    with pytest.raises(ValueError, match="at least 8 characters"):
        validate_password_complexity("Short1!")
    
    with pytest.raises(ValueError, match="no more than 72 characters"):
        validate_password_complexity("A" * 73 + "a1!")
    
    # Complexity
    with pytest.raises(ValueError, match="uppercase"):
        validate_password_complexity("noupper1!")
    with pytest.raises(ValueError, match="lowercase"):
        validate_password_complexity("NOLOWER1!")
    with pytest.raises(ValueError, match="number"):
        validate_password_complexity("NoNumber!!")
    with pytest.raises(ValueError, match="special character"):
        validate_password_complexity("NoSpecial123")
    
    # Valid
    validate_password_complexity("Valid1!Pass")

def test_password_pydantic_type():
    with pytest.raises(ValidationError):
        DummyModel(pwd="Short1!")
    
    model = DummyModel(pwd="Valid1!Pass")
    assert model.pwd == "Valid1!Pass"
