import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db

settings = get_settings()
bearer_scheme = HTTPBearer()


def hash_password(password: str) -> str:
    # Hash password with bcrypt. Encode to bytes, hash, then decode to string
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode('utf-8'), hashed.encode('utf-8'))
    except ValueError:
        return False


def create_access_token(subject_id: uuid.UUID, principal_type: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {
        "sub": str(subject_id),
        "principal_type": principal_type,
        "exp": expire,
        "type": "access",
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(subject_id: uuid.UUID, principal_type: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS
    )
    payload = {
        "sub": str(subject_id),
        "principal_type": principal_type,
        "exp": expire,
        "type": "refresh",
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


async def get_current_company_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Dependency: returns the authenticated CompanyUser."""
    from app.models.company import CompanyUser

    payload = decode_token(credentials.credentials)
    if payload.get("principal_type") != "company_user" or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )
    user_id = uuid.UUID(payload["sub"])
    result = await db.execute(select(CompanyUser).where(CompanyUser.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    # A soft-deleted / deactivated user (or one whose company was archived, which
    # deactivates every user) loses access immediately, not just at token expiry.
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is inactive",
        )
    return user


async def get_current_auditor(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Dependency: returns the authenticated Auditor."""
    from app.models.auditor import Auditor

    payload = decode_token(credentials.credentials)
    if payload.get("principal_type") != "auditor" or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )
    auditor_id = uuid.UUID(payload["sub"])
    result = await db.execute(select(Auditor).where(Auditor.id == auditor_id))
    auditor = result.scalar_one_or_none()
    if auditor is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Auditor not found",
        )
    return auditor


def get_tenant_scope(user):
    """Extract company_id from authenticated company user for tenant scoping."""
    return user.company_id


def require_role(*allowed_roles):
    """Dependency factory: raises 403 if the user's role is not in allowed_roles."""
    from app.models.company import CompanyUser
    async def checker(user: CompanyUser = Depends(get_current_company_user)):
        if user.role not in allowed_roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return checker


def user_has_module(user, module_id: str) -> bool:
    """True if `user` may use `module_id` — admins always pass."""
    from app.models.company import UserRole

    if user.role == UserRole.admin:
        return True
    return module_id in (user.accessible_modules or [])


def require_module(module_id: str):
    """Dependency factory: 403 unless the user has this module granted.

    `accessible_modules` was historically enforced only in the browser
    (ModuleGuard.tsx), which made it a UX affordance rather than a boundary.
    Endpoints that rely on it for authorization must use this. Admins always pass.
    """
    from app.models.company import CompanyUser

    async def checker(user: CompanyUser = Depends(get_current_company_user)):
        if not user_has_module(user, module_id):
            raise HTTPException(
                status_code=403, detail=f"No access to the {module_id} module"
            )
        return user

    return checker


async def get_direct_report_ids(manager_id: uuid.UUID, db: AsyncSession) -> list[uuid.UUID]:
    """Return IDs of all direct reports for a manager."""
    from app.models.company import CompanyUser
    result = await db.execute(
        select(CompanyUser.id).where(CompanyUser.manager_id == manager_id)
    )
    return list(result.scalars().all())


async def get_visible_user_ids(user, db: AsyncSession) -> list[uuid.UUID] | None:
    """Return all user IDs this user is allowed to see data for. None if admin (sees all)."""
    from app.models.company import UserRole
    if user.role == UserRole.admin:
        return None
    return [user.id]

from app.models.company import UserRole
require_admin = require_role(UserRole.admin)
require_manager_or_admin = require_role(UserRole.admin)
# Read access to the fixed-asset register and its master data.
require_assets_module = require_module("assets")
