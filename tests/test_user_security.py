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

    # Exactly 72 characters and 72 bytes
    pwd_72 = "A" * 69 + "1!a"
    assert len(pwd_72) == 72
    assert len(pwd_72.encode("utf-8")) == 72
    validate_password_complexity(pwd_72)

    # Multi-byte UTF-8 that exceeds 72 bytes even though under 72 chars
    pwd_multibyte = "Valid1!Pass" + "🚀" * 16  # 27 chars, 75 bytes
    assert len(pwd_multibyte) == 27
    assert len(pwd_multibyte.encode("utf-8")) == 75
    with pytest.raises(ValueError, match="no more than 72 characters"):
        validate_password_complexity(pwd_multibyte)

    # Null byte injection
    with pytest.raises(ValueError, match="cannot contain null bytes"):
        validate_password_complexity("Valid1!Pass\x00extra")

    # Non-ASCII characters
    with pytest.raises(ValueError, match="only printable ASCII"):
        validate_password_complexity("Pässwörd1!")
    
    with pytest.raises(ValueError, match="only printable ASCII"):
        validate_password_complexity("ПарольA1!b")

    # Non-printable characters (like tabs and newlines)
    with pytest.raises(ValueError, match="only printable ASCII"):
        validate_password_complexity("Valid1!Pass\n")
        
    with pytest.raises(ValueError, match="only printable ASCII"):
        validate_password_complexity("Valid1!Pass\t")

def test_password_pydantic_type():
    with pytest.raises(ValidationError):
        DummyModel(pwd="Short1!")

    with pytest.raises(ValidationError):
        DummyModel(pwd="Valid1!Pass" + "🚀" * 16)

    model = DummyModel(pwd="Valid1!Pass")
    assert model.pwd == "Valid1!Pass"

