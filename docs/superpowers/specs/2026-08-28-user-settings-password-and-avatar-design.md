# Design Specification: User Settings, Password Management & Profile Picture with Interactive Cropper

**Date:** 2026-08-28  
**Topic:** User Settings, Password Reset/Change & Profile Picture Management  
**Status:** Approved for Implementation  
**Scope:** Company Users (`/app/*`) & Tenant Admin User Management  

---

## 1. Executive Summary

This feature introduces a self-service **User Settings** interface for Company Users in Kubera, allowing users to:
1. **Change their password securely** with strict complexity rules, bcrypt hash verification, and a backend-enforced 30-day cooldown period.
2. **Upload and customize their profile picture** via an interactive circular cropping/zooming tool (supporting JPG, JPEG, PNG, WEBP <= 1 MB), with a backend-enforced 3-hour cooldown period, encrypted storage at rest in the tenant vault, and real-time display in the top navigation bar.
3. **Allow Tenant Admins to control password change privileges** per user via a `can_change_password` toggle (defaulting to `true`), hiding the password management UI and blocking API access if permission is revoked.

---

## 2. Data Model & Database Architecture

### 2.1 Database Schema Changes (`CompanyUser` Model)
Four new columns will be added to the `company_users` table in `app/models/company.py`:

```python
class CompanyUser(Base, TimestampMixin):
    # Existing columns ...
    
    # --- Password Privilege & Cooldown ---
    can_change_password: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, server_default="true"
    )
    password_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # --- Avatar Storage & Cooldown ---
    avatar_path: Mapped[str | None] = mapped_column(String, nullable=True)
    avatar_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
```

### 2.2 Alembic Migration
A new migration `add_user_password_controls_and_avatar` will add:
- `can_change_password`: `BOOLEAN NOT NULL DEFAULT TRUE`
- `password_changed_at`: `TIMESTAMP WITH TIME ZONE NULL`
- `avatar_path`: `VARCHAR NULL`
- `avatar_updated_at`: `TIMESTAMP WITH TIME ZONE NULL`

---

## 3. Backend Architecture & API Specifications

### 3.1 Schemas (`app/schemas/users.py` & `app/schemas/auth.py`)

```python
# Password Change Request Schema
class UserChangePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)
    confirm_password: str = Field(..., min_length=8, max_length=128)

# User Schemas updates
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    role: UserRole
    manager_id: uuid.UUID | None = None
    designation: str | None = None
    department: str | None = None
    accessible_modules: list[str] = Field(default_factory=list)
    can_change_password: bool = True

class UserUpdate(BaseModel):
    full_name: str | None = None
    role: UserRole | None = None
    manager_id: uuid.UUID | None = None
    designation: str | None = None
    department: str | None = None
    is_active: bool | None = None
    accessible_modules: list[str] | None = None
    can_change_password: bool | None = None

class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: UserRole
    manager_id: uuid.UUID | None
    designation: str | None
    department: str | None
    is_active: bool
    deleted_at: datetime | None = None
    accessible_modules: list[str]
    company_id: uuid.UUID
    can_change_password: bool
    has_avatar: bool = False
    avatar_updated_at: datetime | None = None
    password_changed_at: datetime | None = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class CompanyUserOut(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    email: str
    role: str
    manager_id: uuid.UUID | None = None
    full_name: str = "Unknown"
    designation: str | None = None
    department: str | None = None
    is_active: bool = True
    accessible_modules: list[str] = []
    can_change_password: bool = True
    has_avatar: bool = False
    avatar_updated_at: datetime | None = None
    password_changed_at: datetime | None = None
    model_config = {"from_attributes": True}
```

### 3.2 Password Change Endpoint: `POST /api/v1/users/me/change-password`
* **Route**: `/api/v1/users/me/change-password`
* **Authentication**: Strictly authenticated via `get_current_company_user`. (Zero direct user ID parameters accepted; impossible to target another user's account).
* **Execution & Verification Pipeline**:
  1. **Privilege Check**: Verify `current_user.can_change_password == True`. If false, raise `403 Forbidden` (`"You do not have permission to change your password"`).
  2. **30-Day Cooldown Check**: If `current_user.password_changed_at` is present and `(datetime.now(timezone.utc) - current_user.password_changed_at).total_seconds() < 30 * 86400`:
     - Calculate remaining days/hours.
     - Raise `429 Too Many Requests` (`"Password can only be changed once every 30 days. Next change available on {next_allowed_date}"`).
  3. **Old Password Match**: Verify `verify_password(body.old_password, current_user.hashed_password)`. If false, raise `400 Bad Request` (`"Current password is incorrect"`).
  4. **Password Equality & Difference**:
     - Check `body.new_password == body.confirm_password`. If not, raise `400 Bad Request` (`"New passwords do not match"`).
     - Check `body.old_password != body.new_password`. If same, raise `400 Bad Request` (`"New password cannot be the same as the current password"`).
  5. **Password Complexity Validation**:
     - At least 8 characters
     - At least 1 uppercase letter: `re.search(r'[A-Z]', password)`
     - At least 1 lowercase letter: `re.search(r'[a-z]', password)`
     - At least 1 digit: `re.search(r'[0-9]', password)`
     - At least 1 special character: `re.search(r'[!@#$%^&*(),.?":{}|<>\-_=+\\[\\]\\/`~]', password)`
  6. **Hash & Persist**:
     - Hash with `hash_password(body.new_password)` (bcrypt).
     - Set `current_user.hashed_password = new_hash`.
     - Set `current_user.password_changed_at = datetime.now(timezone.utc)`.
  7. **Audit Trail**:
     - Log activity in `ActivityLog(company_id=current_user.company_id, actor_id=current_user.id, action="user.password_changed", entity_type="company_user", entity_id=current_user.id)`.
  8. **Response**: Return `{"success": True, "message": "Password updated successfully"}`.

### 3.3 Profile Picture Upload Endpoint: `POST /api/v1/users/me/avatar`
* **Route**: `/api/v1/users/me/avatar`
* **Authentication**: `get_current_company_user`.
* **Accepted Formats**: `image/jpeg`, `image/png`, `image/webp` (max 1 MB / 1,048,576 bytes).
* **Execution & Verification Pipeline**:
  1. **3-Hour Cooldown Check**: If `current_user.avatar_updated_at` is present and `(datetime.now(timezone.utc) - current_user.avatar_updated_at).total_seconds() < 3 * 3600`:
     - Raise `429 Too Many Requests` (`"Profile picture can only be changed once every 3 hours. Next change available on {next_allowed_time}"`).
  2. **File Size Check**: If length > 1,048,576 bytes, raise `413 Request Entity Too Large` (`"Avatar must be 1 MB or smaller"`).
  3. **Magic Byte / Format Check**:
     - JPEG: starts with `\xff\xd8\xff`
     - PNG: starts with `\x89PNG\r\n\x1a\n`
     - WEBP: starts with `RIFF` and bytes 8..12 are `WEBP`
     - Otherwise, raise `415 Unsupported Media Type` (`"Avatar must be a valid JPG, PNG, or WEBP image"`).
  4. **Encryption at Rest**:
     - Fetch company KEK using `_company_kek(db, current_user.company_id)`.
     - Encrypt binary payload via `encrypt_file_data(data, kek)`.
     - Directory: `data/vault/users/{current_user.id}/`.
     - File path: `data/vault/users/{current_user.id}/avatar_{uuid4()}.{ext}.enc`.
     - Prepend 12-byte nonce to ciphertext.
  5. **Purge Old Avatar**: Delete previous avatar file if exists on disk.
  6. **Update Model**: Set `current_user.avatar_path = str(storage_path)` and `current_user.avatar_updated_at = datetime.now(timezone.utc)`.
  7. **Audit Trail**: Record `ActivityLog(action="user.avatar_updated")`.
  8. **Response**: Return updated `CompanyUserOut`.

### 3.4 Profile Picture Streaming Endpoint: `GET /api/v1/users/{user_id}/avatar` & `GET /api/v1/users/me/avatar`
* **Authentication**: `get_current_company_user` (verifies same company tenant).
* **Decryption & Streaming**:
  - Read ciphertext + nonce from disk.
  - Decrypt with company KEK.
  - Set security headers:
    - `Content-Type: image/jpeg` (or `png`/`webp`)
    - `Content-Security-Policy: default-src 'none'; sandbox`
    - `X-Content-Type-Options: nosniff`
    - `Cache-Control: private, max-age=3600`
  - Return raw binary `Response`.

---

## 4. Frontend Architecture & User Experience

### 4.1 TopBar Integration (`TopBar.tsx`)
- **Avatar Display**:
  - Renders user profile picture from `/api/v1/users/me/avatar` with `rounded-full object-cover shadow-sm`.
  - Seamless fallback to two-letter gradient initial badge if `has_avatar` is false or image fails to load.
- **Dropdown Menu**:
  - Insert **"User Settings"** item (with Lucide `Settings` icon) immediately above the "Log out" button.
  - Clicking "User Settings" navigates to `/app/settings/user`.

### 4.2 User Settings Page (`/app/settings/user`)
A responsive settings screen inside `CompanyShell`:
1. **User Identity & Info Card**: Displays Full Name, Email address, Assigned Role badge, Department, and Designation.
2. **Profile Picture Card**:
   - Displays circular avatar preview (large 96x96px).
   - Shows active cooldown status if within 3 hours (*"Next change available in X hours Y minutes"*).
   - "Upload New Photo" button (triggers file selector). Selecting an image opens the interactive cropper.
3. **Change Password Card**:
   - Completely hidden if `user.can_change_password` is `false`.
   - Displays 30-day cooldown banner if changed recently (*"Password was last updated on {Date}. Next update allowed on {Date}"*).
   - Form fields with toggleable eye icon for password visibility:
     - Old Password
     - New Password
     - Confirm New Password
   - **Real-Time Password Complexity Checklist**:
     - [ ] Minimum 8 characters
     - [ ] At least 1 uppercase letter (`A-Z`)
     - [ ] At least 1 lowercase letter (`a-z`)
     - [ ] At least 1 digit (`0-9`)
     - [ ] At least 1 special character (`!@#$%^&*...`)
     - [ ] New passwords match
   - "Update Password" button with asynchronous loading state and toast feedback.

### 4.3 Interactive Circular Avatar Cropper Modal (`AvatarCropperModal.tsx`)
- **Interactive Viewport**:
  - Shows uploaded image with a dimmed background overlay and a highlighted circular crop mask in the center.
  - **Pan & Move**: Full click-and-drag / touch-and-drag support so users can move any part of the photo into the circle.
  - **Zoom Controls**: Slider (1.0x to 3.0x) and `+` / `-` zoom buttons.
  - **Circular Live Preview**: Shows the exact avatar circle preview that will appear in the top bar.
- **Export & Upload**:
  - HTML5 canvas renders the selected circular region into a cropped image blob (<= 1 MB).
  - Uploads to `POST /api/v1/users/me/avatar`.
  - Refreshes auth profile cache and updates the TopBar avatar instantly.

### 4.4 Admin User Management (`UserModal.tsx` & `UsersDirectory.tsx`)
- Adds Switch component: **"Allow user to change password"** (`can_change_password`).
- Enabled by default for all new user creations.
- Editable by tenant admins when viewing or updating existing user accounts.

---

## 5. Security & Threat Model Review

| Threat / Risk | Mitigation Strategy |
|---|---|
| **IDOR / Privilege Escalation** | Endpoints use `get_current_company_user` from the validated JWT token; zero caller-controlled user IDs in password mutation endpoints. |
| **Brute Force / Password Guessing** | Old password checked via bcrypt with constant-time verification; rate-limited endpoints; audit logging on failed attempts. |
| **Bypass of Password Policy** | Identical regex constraints validated both on client-side (Zod) and backend (Pydantic & Python regex). |
| **Malicious File Upload (XSS / RCE / Polyglots)** | File size capped at 1 MB; binary magic byte inspection (rejects SVG/HTML/executables); stored encrypted under generated UUID names; served with `Content-Security-Policy: sandbox` and `X-Content-Type-Options: nosniff`. |
| **Path Traversal Attacks** | Storage paths constructed safely using server-generated UUIDs and validated system directories; no user-supplied file names on disk. |
| **SQL Injection** | Exclusively parameterized queries executed via async SQLAlchemy ORM. |
| **Unauthorized Password Modification** | Backend verifies `current_user.can_change_password` regardless of UI state. |

---

## 6. Testing Strategy

### 6.1 Backend Automated Tests (`tests/test_user_settings.py`)
1. **Password Validation Tests**:
   - Reject passwords shorter than 8 characters, missing uppercase, missing lowercase, missing numbers, or missing special characters.
   - Reject password change when `old_password` does not match.
   - Reject password change when `can_change_password` is `False` (403 Forbidden).
   - Enforce 30-day cooldown (429 Too Many Requests).
   - Successful password change updates hash and `password_changed_at`.
2. **Avatar Upload & Streaming Tests**:
   - Reject files > 1 MB (413).
   - Reject spoofed MIME types / non-image magic bytes (415).
   - Enforce 3-hour cooldown (429).
   - Verify encrypted storage on disk and decrypted streaming response.
   - Verify cross-tenant isolation (user cannot view avatar of another company's user).

### 6.2 Frontend Automated & Component Tests
1. **TopBar Tests**: Verify User Settings menu item presence and avatar image/initials fallback.
2. **UserSettingsPage Tests**: Verify hiding of Change Password card when `can_change_password` is false; verify real-time complexity check list; verify cooldown banners.
3. **AvatarCropperModal Tests**: Verify zoom, pan, and canvas blob export behavior.
4. **UserModal Tests**: Verify `can_change_password` toggle for tenant admins during user creation and update.
