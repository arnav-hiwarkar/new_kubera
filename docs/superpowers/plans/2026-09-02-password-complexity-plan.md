# Password Complexity Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Centralize and strictly enforce password complexity and a 72-character maximum length across all backend endpoints and provide real-time frontend validation.

**Architecture:** We will implement a custom Pydantic `Password` type using `AfterValidator` in `user_security.py` that enforces the complexity and length rules. All auth-related schemas will use this type. The frontend will implement equivalent Yup/react-hook-form validation rules to provide real-time feedback.

**Tech Stack:** FastAPI, Pydantic, React, react-hook-form.

## Global Constraints
- `PASSWORD_MAX_LENGTH` must be strictly 72.
- `PASSWORD_MIN_LENGTH` must be strictly 8.
- The complexity rules require at least one uppercase letter, one lowercase letter, one number, and one special character.
- Existing tests must not break; if they use weak passwords, they must be updated to use valid passwords (e.g., `Valid1!Pass`).
- Do NOT run the full test suite. Run only specific tests for the modified modules.

---

### Task 1: Update `validate_password_complexity` and create `Password` Type

**Files:**
- Modify: `app/services/user_security.py`
- Create/Modify: `tests/unit/test_user_security.py` (or existing test file)

**Interfaces:**
- Produces: `Password` (Pydantic `Annotated` type).

- [ ] **Step 1: Write the failing tests for backend validation**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_user_security.py -v`
Expected: FAIL (because max length is 128 and Password type doesn't exist yet)

- [ ] **Step 3: Write minimal implementation**

Modify `app/services/user_security.py`:
```python
from typing import Annotated
from pydantic import Field, AfterValidator
import re
from typing import Literal

PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 72 # Updated from 128

# Special character set allowed and checked
SPECIAL_CHARS_RE = re.compile(r'[-!@#$%^&*(),.?":{}|<>_=+`~/\\\[\];]')

def validate_password_complexity(password: str) -> None:
    if not password or len(password) < PASSWORD_MIN_LENGTH:
        raise ValueError(f"Password must be at least {PASSWORD_MIN_LENGTH} characters long.")
    if len(password) > PASSWORD_MAX_LENGTH:
        raise ValueError(f"Password must be no more than {PASSWORD_MAX_LENGTH} characters long.")
    if not re.search(r"[A-Z]", password):
        raise ValueError("Password must contain at least one uppercase letter (A-Z).")
    if not re.search(r"[a-z]", password):
        raise ValueError("Password must contain at least one lowercase letter (a-z).")
    if not re.search(r"[0-9]", password):
        raise ValueError("Password must contain at least one number (0-9).")
    if not SPECIAL_CHARS_RE.search(password):
        raise ValueError("Password must contain at least one special character.")

def _check_password(password: str) -> str:
    validate_password_complexity(password)
    return password

Password = Annotated[
    str,
    Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH),
    AfterValidator(_check_password),
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_user_security.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/user_security.py tests/unit/test_user_security.py
git commit -m "feat(security): update max password length to 72 and add Password Pydantic type"
```

### Task 2: Apply `Password` Type to Schemas and Endpoints

**Files:**
- Modify: `app/schemas/auth.py`
- Modify: `app/schemas/users.py`
- Modify: `app/routers/users.py`
- Modify: `app/services/account_admin.py`

**Interfaces:**
- Consumes: `Password` from `app.services.user_security`

- [ ] **Step 1: Write failing tests for schemas (anti-tests)**

Create/Modify: `tests/unit/test_auth_schemas.py`
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_auth_schemas.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

In `app/schemas/auth.py`:
```python
from app.services.user_security import Password

class ActivationRequest(BaseModel):
    email: EmailStr
    activation_key: str
    password: Password
    full_name: str = Field(min_length=1, max_length=255)

class AuditorRegister(BaseModel):
    email: EmailStr
    password: Password
    name: str = Field(min_length=1, max_length=255)
```

In `app/schemas/users.py`:
```python
from app.services.user_security import Password

class UserChangePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=1)
    new_password: Password
    confirm_password: Password

class UserCreate(BaseModel):
    email: EmailStr
    password: Password
    full_name: str
    ... # rest of fields remain unchanged
```

In `app/routers/users.py`, lines 202-208, remove:
```python
    try:
        validate_password_complexity(body.new_password)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        )
```

In `app/services/account_admin.py`, replace:
```python
    if not new_password:
        raise ValueError("password cannot be empty")
```
With:
```python
    from app.services.user_security import validate_password_complexity
    validate_password_complexity(new_password)
```

- [ ] **Step 4: Fix any broken existing tests**

Run `pytest unit_tests/ -v` and `pytest tests/ -v`.
If any existing tests in `unit_tests/` or `tests/` fail because they use weak passwords (e.g., `password123`), update those specific tests to use `Valid1!Pass` instead. Do not run the full e2e suite if it takes too long, just the unit tests.

- [ ] **Step 5: Run schema tests to verify they pass**

Run: `pytest tests/unit/test_auth_schemas.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/schemas/auth.py app/schemas/users.py app/routers/users.py app/services/account_admin.py tests/
git commit -m "feat(security): enforce Password complexity across all auth schemas and endpoints"
```

### Task 3: Frontend Validation Utility

**Files:**
- Create: `frontend/src/utils/passwordValidation.ts`

**Interfaces:**
- Produces: `passwordRules` object or Yup chain for use in forms.

- [ ] **Step 1: Write implementation**

Create `frontend/src/utils/passwordValidation.ts`:
```typescript
export const passwordRules = {
  required: 'Password is required',
  minLength: { value: 8, message: 'Min 8 characters' },
  maxLength: { value: 72, message: 'Max 72 characters' },
  pattern: {
    value: /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[-!@#$%^&*(),.?":{}|<>_=+`~/\\\[\];]).+$/,
    message: 'Must contain uppercase, lowercase, number, and special character'
  }
}

export const confirmPasswordRules = (watchPassword: string) => ({
  required: 'Confirm password is required',
  validate: (val: string) => {
    if (watchPassword && val !== watchPassword) {
      return 'Passwords do not match';
    }
    return true;
  }
})
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/utils/passwordValidation.ts
git commit -m "feat(frontend): add shared password validation rules"
```

### Task 4: Apply Frontend Validation to Forms

**Files:**
- Modify: `frontend/src/pages/auditor/AuditorRegister.tsx`
- Modify: `frontend/src/pages/company/CompanyActivate.tsx`
- Modify: `frontend/src/pages/company/users/UserModal.tsx`
- Modify: `frontend/src/pages/company/settings/UserSettingsPage.tsx`

**Interfaces:**
- Consumes: `passwordRules` from `frontend/src/utils/passwordValidation.ts`

- [ ] **Step 1: Write implementation**

In `frontend/src/pages/auditor/AuditorRegister.tsx`:
```tsx
import { passwordRules } from '@/utils/passwordValidation'
// ...
<Input
  id="password"
  type="password"
  autoComplete="new-password"
  error={!!errors.password}
  {...register('password', passwordRules)}
/>
```

In `frontend/src/pages/company/CompanyActivate.tsx`:
```tsx
import { passwordRules } from '@/utils/passwordValidation'
// ...
<Input
  id="password"
  type="password"
  autoComplete="new-password"
  error={!!errors.password}
  {...register('password', passwordRules)}
/>
```

In `frontend/src/pages/company/users/UserModal.tsx`:
```tsx
import { passwordRules } from '@/utils/passwordValidation'
// ...
<Input
  id="password"
  type="password"
  error={!!errors.password}
  {...register('password', isEditing ? {} : passwordRules)} // Only required/validated on create unless changing
/>
```

In `frontend/src/pages/company/settings/UserSettingsPage.tsx`:
```tsx
import { passwordRules, confirmPasswordRules } from '@/utils/passwordValidation'
// ...
<Input
  id="new_password"
  type="password"
  error={!!errors.new_password}
  {...register('new_password', passwordRules)}
/>
// ...
<Input
  id="confirm_password"
  type="password"
  error={!!errors.confirm_password}
  {...register('confirm_password', confirmPasswordRules(watch('new_password')))}
/>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/auditor/AuditorRegister.tsx frontend/src/pages/company/CompanyActivate.tsx frontend/src/pages/company/users/UserModal.tsx frontend/src/pages/company/settings/UserSettingsPage.tsx
git commit -m "feat(frontend): enforce password complexity on all forms"
```
