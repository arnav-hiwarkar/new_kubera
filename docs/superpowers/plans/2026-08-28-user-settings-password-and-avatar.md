# User Settings, Password Management & Profile Picture Implementation Plan

> **For:** Antigravity (Claude / Gemini)  
> **Source Spec:** [`docs/superpowers/specs/2026-08-28-user-settings-password-and-avatar-design.md`](file:///Users/ash/Projects/new_kubera/docs/superpowers/specs/2026-08-28-user-settings-password-and-avatar-design.md)  
> **Target Files:**
> - `app/models/company.py`
> - `alembic/versions/*_user_password_controls_and_avatar.py`
> - `app/schemas/users.py`
> - `app/schemas/auth.py`
> - `app/routers/users.py`
> - `app/services/user_security.py` (helpers for password complexity & magic bytes)
> - `tests/test_user_settings.py`
> - `frontend/src/api/types.ts`
> - `frontend/src/api/endpoints/users.ts`
> - `frontend/src/api/hooks/users.ts`
> - `frontend/src/components/ui/TopBar.tsx`
> - `frontend/src/components/users/AvatarCropperModal.tsx`
> - `frontend/src/pages/company/settings/UserSettingsPage.tsx`
> - `frontend/src/pages/company/users/UserModal.tsx`
> - `frontend/src/routes/company.routes.tsx`
> - `frontend/src/components/users/AvatarCropperModal.test.tsx`
> - `frontend/src/pages/company/settings/UserSettingsPage.test.tsx`

---

## Overview of Tasks

1. **Task 1: Database Model & Alembic Migration**: Add `can_change_password`, `password_changed_at`, `avatar_path`, and `avatar_updated_at` to `CompanyUser` and generate/apply the migration.
2. **Task 2: Backend Schemas & Security Validation Core**: Update Pydantic schemas in `users.py` & `auth.py`; create password complexity validation and magic-bytes validator utilities.
3. **Task 3: Backend API Endpoints**: Implement `POST /api/v1/users/me/change-password`, `POST /api/v1/users/me/avatar`, `GET /api/v1/users/me/avatar`, and `GET /api/v1/users/{user_id}/avatar` with all rate limits, cooldowns, and encryption.
4. **Task 4: Backend Integration Test Suite**: Write comprehensive tests in `tests/test_user_settings.py` covering complexity rules, hash checking, 30-day cooldown, 3-hour cooldown, magic byte validation, and privilege enforcement.
5. **Task 5: Frontend API Client & Hooks**: Add typed API endpoints and React Query hooks for password change and avatar upload/streaming.
6. **Task 6: Interactive Circular Avatar Cropper**: Build `AvatarCropperModal.tsx` with pan/drag, zoom slider, live circular preview, and canvas blob export ($\le 1\text{ MB}$).
7. **Task 7: User Settings Page & UI Integration**: Build `UserSettingsPage.tsx` with live password strength checklist and cooldown notices; update `TopBar.tsx` with avatar rendering and "User Settings" menu item; update `UserModal.tsx` with admin toggle.
8. **Task 8: Frontend Unit & Component Tests**: Write Vitest unit tests for `AvatarCropperModal.test.tsx`, `UserSettingsPage.test.tsx`, and updated `TopBar.test.tsx`.
9. **Task 9: Full Verification**: Run backend test suite, frontend vitest suite, and TypeScript build checks.

---

## Detailed Task Breakdown

### Task 1: Database Model & Alembic Migration

- [ ] **Step 1.1**: Open `app/models/company.py` and add the 4 columns to `CompanyUser`:
  ```python
  can_change_password: Mapped[bool] = mapped_column(
      Boolean, default=True, nullable=False, server_default="true"
  )
  password_changed_at: Mapped[datetime | None] = mapped_column(
      DateTime(timezone=True), nullable=True
  )
  avatar_path: Mapped[str | None] = mapped_column(String, nullable=True)
  avatar_updated_at: Mapped[datetime | None] = mapped_column(
      DateTime(timezone=True), nullable=True
  )
  ```
- [ ] **Step 1.2**: Create a new Alembic migration in `alembic/versions/` adding these 4 columns to the `company_users` table with proper upgrade and downgrade functions.
- [ ] **Step 1.3**: Run `uv run pytest tests/` to confirm model loading and schema initialization succeed.

---

### Task 2: Backend Schemas & Security Validation Core

- [ ] **Step 2.1**: Update `app/schemas/users.py`:
  - Add `UserChangePasswordRequest` with `old_password`, `new_password`, `confirm_password`.
  - Add `can_change_password: bool = True` to `UserCreate`.
  - Add `can_change_password: bool | None = None` to `UserUpdate`.
  - Add `can_change_password: bool`, `has_avatar: bool = False`, `avatar_updated_at: datetime | None = None`, `password_changed_at: datetime | None = None` to `UserResponse`.
- [ ] **Step 2.2**: Update `app/schemas/auth.py`:
  - Add `can_change_password: bool = True`, `has_avatar: bool = False`, `avatar_updated_at: datetime | None = None`, `password_changed_at: datetime | None = None` to `CompanyUserOut`.
- [ ] **Step 2.3**: Create `app/services/user_security.py` with:
  - `validate_password_complexity(password: str) -> None`: checks min length 8, `[A-Z]`, `[a-z]`, `[0-9]`, and `[!@#$%^&*(),.?":{}|<>\-_=+\\[\\]\\/`~]`. Raises `ValueError` with descriptive message if missing any rule.
  - `detect_image_format(data: bytes) -> str | None`: checks magic bytes for JPEG (`\xff\xd8\xff`), PNG (`\x89PNG\r\n\x1a\n`), WEBP (`RIFF....WEBP`). Returns `"jpg"`, `"png"`, `"webp"` or `None`.

---

### Task 3: Backend API Endpoints

- [ ] **Step 3.1**: In `app/routers/users.py`, implement `POST /api/v1/users/me/change-password`:
  - Authenticate with `get_current_company_user`.
  - Enforce `user.can_change_password is True` (raise 403 if False).
  - Enforce 30-day cooldown: check if `user.password_changed_at` is within 30 days of `now(timezone.utc)` (raise 429).
  - Verify `verify_password(body.old_password, user.hashed_password)` (raise 400 if incorrect).
  - Verify `body.new_password == body.confirm_password` (raise 400 if mismatched).
  - Verify `body.new_password != body.old_password` and not matching existing hash (raise 400 if same).
  - Verify `validate_password_complexity(body.new_password)` (raise 400 if invalid).
  - Hash with `hash_password(body.new_password)` (salted bcrypt).
  - Update `user.hashed_password = new_hash` and `user.password_changed_at = datetime.now(timezone.utc)`.
  - Log `ActivityLog(action="user.password_changed")`.
  - Commit and return `{"success": True, "message": "Password changed successfully"}`.
- [ ] **Step 3.2**: In `app/routers/users.py`, implement `POST /api/v1/users/me/avatar`:
  - Authenticate with `get_current_company_user`.
  - Enforce 3-hour cooldown: check if `user.avatar_updated_at` is within 3 hours (raise 429).
  - Read uploaded file data, enforce size $\le 1\text{ MB}$ ($1,048,576$ bytes, raise 413).
  - Validate magic bytes via `detect_image_format(data)` (raise 415 if invalid).
  - Encrypt with company KEK (`encrypt_file_data(data, kek)`).
  - Store to `data/vault/users/{user_id}/avatar_{uuid}.{ext}.enc`.
  - Remove old avatar file if existing.
  - Update `user.avatar_path = str(path)` and `user.avatar_updated_at = datetime.now(timezone.utc)`.
  - Log `ActivityLog(action="user.avatar_updated")`.
  - Commit and return updated user object.
- [ ] **Step 3.3**: In `app/routers/users.py`, implement `GET /api/v1/users/{user_id}/avatar` & `GET /api/v1/users/me/avatar`:
  - Authenticate with `get_current_company_user`, verify company tenant matching.
  - Read encrypted file, decrypt with company KEK.
  - Return binary `Response` with headers `Content-Type`, `Content-Security-Policy: default-src 'none'; sandbox`, `X-Content-Type-Options: nosniff`, `Cache-Control: private, max-age=3600`.
- [ ] **Step 3.4**: Update `create_user` and `update_user` in `app/routers/users.py` to handle `can_change_password`.

---

### Task 4: Backend Automated Test Suite (`tests/test_user_settings.py`)

- [ ] **Step 4.1**: Create `tests/test_user_settings.py` with test fixtures.
- [ ] **Step 4.2**: Add test cases for password changing:
  - `test_password_change_success`: Verifies correct old password, updates hash, verifies login with new password, sets `password_changed_at`.
  - `test_password_change_wrong_old_password`: Returns 400 Bad Request.
  - `test_password_change_same_password`: Returns 400 Bad Request.
  - `test_password_change_complexity_enforced`: Tests missing uppercase, lowercase, number, special char, length < 8 (returns 400).
  - `test_password_change_permission_denied`: Admin sets `can_change_password=False`, user gets 403 Forbidden.
  - `test_password_change_cooldown_enforced`: After changing, immediate second attempt returns 429 Too Many Requests.
- [ ] **Step 4.3**: Add test cases for avatar upload & streaming:
  - `test_avatar_upload_success_and_stream`: Uploads valid PNG/JPEG/WEBP, verifies encrypted file on disk, streams back decrypted with headers.
  - `test_avatar_upload_size_limit`: Uploads > 1 MB file, returns 413.
  - `test_avatar_upload_invalid_magic_bytes`: Uploads text/html claiming to be image, returns 415.
  - `test_avatar_upload_cooldown_enforced`: Immediate second upload returns 429.
  - `test_avatar_cross_tenant_isolation`: User from Company B cannot access avatar of User from Company A.
- [ ] **Step 4.4**: Run `uv run pytest tests/test_user_settings.py` and verify all tests pass.

---

### Task 5: Frontend API Client & React Query Hooks

- [ ] **Step 5.1**: Update `frontend/src/api/types.ts` with `UserChangePasswordRequest`, `can_change_password`, `has_avatar`, `avatar_updated_at`, and `password_changed_at`.
- [ ] **Step 5.2**: Update `frontend/src/api/endpoints/users.ts`:
  - `changePassword: (body: UserChangePasswordRequest) => companyClient.post(...)`
  - `uploadAvatar: (formData: FormData) => companyClient.post(...)`
- [ ] **Step 5.3**: Update `frontend/src/api/hooks/users.ts`:
  - `useChangePassword()`: Mutation hook that invalidates auth/profile queries and triggers notifications.
  - `useUploadAvatar()`: Mutation hook that invalidates auth/profile queries and refreshes TopBar.

---

### Task 6: Interactive Circular Avatar Cropper (`AvatarCropperModal.tsx`)

- [ ] **Step 6.1**: Create `frontend/src/components/users/AvatarCropperModal.tsx`:
  - Accept `isOpen`, `imageSrc`, `onClose`, `onCropComplete(blob: Blob)`.
  - Viewport displaying the loaded image with circular mask cut-out overlay.
  - Drag-and-pan mouse & touch handlers to reposition the image freely.
  - Zoom slider ($1.0\times$ to $3.0\times$) and `+`/`-` buttons.
  - Live circular preview side-panel.
  - Canvas crop function rendering the selected circular area into a clean $\le 1\text{ MB}$ image blob.
  - "Apply & Save" button invoking `onCropComplete`.

---

### Task 7: User Settings Page & UI Integration

- [ ] **Step 7.1**: Create `frontend/src/pages/company/settings/UserSettingsPage.tsx`:
  - Header with title and breadcrumbs.
  - **Account Info Card**: Displays full name, email, role, department, designation.
  - **Profile Picture Card**:
    - Large 96px circular avatar display.
    - 3-hour cooldown timer display and status badge.
    - File input button that opens `AvatarCropperModal` upon selection.
  - **Change Password Card**:
    - Rendered only if `profile?.can_change_password !== false`.
    - 30-day cooldown banner if within 30 days of last update.
    - Form inputs with show/hide password toggle.
    - Real-time interactive criteria checklist:
      * $\ge 8$ chars
      * 1 uppercase letter
      * 1 lowercase letter
      * 1 number
      * 1 special char
      * Different from old password
      * Passwords match
    - "Update Password" button calling `useChangePassword`.
- [ ] **Step 7.2**: Register route `{ path: 'settings/user', element: <UserSettingsPage /> }` in `frontend/src/routes/company.routes.tsx`.
- [ ] **Step 7.3**: Update `frontend/src/components/ui/TopBar.tsx`:
  - Render user profile image from `/api/v1/users/me/avatar` if `profile.has_avatar` is true, with seamless error fallback to gradient initials.
  - Insert "User Settings" menu option with `Settings` icon above "Log out".
- [ ] **Step 7.4**: Update `frontend/src/pages/company/users/UserModal.tsx`:
  - Add Switch component for "Allow user to change password" (`can_change_password`), default `true`.

---

### Task 8: Frontend Unit & Component Tests

- [ ] **Step 8.1**: Create `frontend/src/components/users/AvatarCropperModal.test.tsx`:
  - Test modal render, image load, zoom slider change, and crop export trigger.
- [ ] **Step 8.2**: Create `frontend/src/pages/company/settings/UserSettingsPage.test.tsx`:
  - Test hiding of password card when `can_change_password` is false.
  - Test real-time checklist validation turning green.
  - Test 30-day and 3-hour cooldown warning displays.
  - Test form submit handling.
- [ ] **Step 8.3**: Update `frontend/src/components/ui/TopBar.test.tsx` and `frontend/src/pages/company/users/UserModal.test.tsx` to verify new settings link and admin switch.

---

### Task 9: Full Verification

- [ ] **Step 9.1**: Run backend pytest suite: `uv run pytest tests/test_user_settings.py`.
- [ ] **Step 9.2**: Run frontend test suite: `npm test` in `frontend/`.
- [ ] **Step 9.3**: Run TypeScript build check: `npx tsc --noEmit` in `frontend/`.
