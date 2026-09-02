# Password Complexity and Truncation Fix Design

## Overview
This design addresses KUB-004, a high-severity security issue where password complexity and length validation were not universally enforced across all password-setting entry points. It also resolves a potential issue where the application's maximum password length (128 characters) exceeded bcrypt's actual truncation limit (72 bytes).

## Architecture & Components

### 1. Backend Validation (Centralized)
- **`app/services/user_security.py`**:
  - Decrease `PASSWORD_MAX_LENGTH` from `128` to `72` to accurately reflect the bcrypt limitation without requiring complex database hashing migrations.
  - Create a new `Password` type using `typing.Annotated` and `pydantic.AfterValidator`. This type will automatically run `validate_password_complexity` on any field it is assigned to.
- **Schemas (`app/schemas/auth.py`, `app/schemas/users.py`)**:
  - Replace raw `str` definitions for passwords with the new `Password` type in:
    - `AuditorRegister`
    - `ActivationRequest`
    - `UserCreate`
    - `UserChangePasswordRequest`
- **Routers & Services**:
  - `app/routers/users.py`: Remove the redundant `try/except ValueError` in `/me/change-password` because Pydantic will now catch these and automatically return a standard `422 Unprocessable Entity`.
  - `app/services/account_admin.py`: Update `set_password` (used by the `change_password.py` operator script) to directly call `validate_password_complexity(new_password)`.

### 2. Frontend Implementation
- Create a reusable password validation utility (e.g., in `frontend/src/utils/validation.ts` or as part of existing form utilities).
- Update form definitions to use this client-side validation to provide immediate feedback:
  - `frontend/src/pages/auditor/AuditorRegister.tsx`
  - `frontend/src/pages/company/CompanyActivate.tsx`
  - `frontend/src/pages/company/users/UserModal.tsx`
  - `frontend/src/pages/company/settings/UserSettingsPage.tsx`

## Testing & Verification Plan

To ensure the system functions as intended and prevents exploitable scenarios, the following comprehensive tests will be implemented:

### 1. Unit Tests (Backend)
- **Complexity Edge Cases**: 
  - Fails if missing uppercase, lowercase, number, or special character.
  - Succeeds with minimum required characters (`Aa1!aaaa`).
- **Length Boundaries (Anti-tests)**:
  - Fails at 7 characters.
  - Succeeds at 8 characters.
  - Succeeds at 72 characters.
  - Fails at 73 characters.
- **Pydantic Model Tests**: Verify that `AuditorRegister` and `UserCreate` models raise `ValidationError` when instantiated with non-compliant passwords.

### 2. Integration / E2E Tests (Backend)
- **Auditor Registration**: Attempt to register an auditor with a 1-character password (must return `422`).
- **Admin Creates Employee**: Attempt to create an employee with a non-compliant password (must return `422`).
- **Company Activation**: Attempt to activate a company admin account with a password > 72 characters (must return `422`).
- **Operator Script**: Call `account_admin.set_password` with a non-compliant password to ensure a `ValueError` is raised, preventing direct database insertion of weak hashes.

### 3. Frontend Tests
- Ensure form submission is blocked and visual errors are shown when users type non-compliant passwords in the `AuditorRegister` and `CompanyActivate` components.

## Security Considerations
By strictly enforcing the 72-character limit, we prevent users from being misled into thinking excess characters add entropy. Centralizing the validation in a Pydantic type guarantees that any future schema additions will inherit the security constraints by default if they use the `Password` type.
