"""Password hashing, JWT authentication and role-based permissions."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from enum import StrEnum

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_session
from app.models.enums import UserRole
from app.models.user import User


class Permission(StrEnum):
    MANAGE_USERS = "manage_users"
    VIEW_RESULTS = "view_results"
    EXPORT_RESULTS = "export_results"
    RUN_EXPERIMENTS = "run_experiments"
    EDIT_PROMPTS = "edit_prompts"
    MANAGE_PROJECTS = "manage_projects"
    OPERATE_HARDWARE = "operate_hardware"
    LABEL_GESTURES = "label_gestures"
    MANAGE_MYO = "manage_myo"


ROLE_PERMISSIONS: dict[UserRole, frozenset[Permission]] = {
    UserRole.ADMIN: frozenset(Permission),
    UserRole.RESEARCHER: frozenset({
        Permission.VIEW_RESULTS, Permission.EXPORT_RESULTS,
        Permission.RUN_EXPERIMENTS, Permission.EDIT_PROMPTS,
        Permission.MANAGE_PROJECTS, Permission.OPERATE_HARDWARE,
        Permission.LABEL_GESTURES, Permission.MANAGE_MYO,
    }),
    UserRole.INTERN: frozenset({
        Permission.VIEW_RESULTS, Permission.RUN_EXPERIMENTS,
        Permission.LABEL_GESTURES, Permission.MANAGE_MYO,
    }),
    UserRole.OTHER: frozenset({Permission.VIEW_RESULTS}),
}

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

_PREHASH_PREFIX = "sha256$"


def _prehash(password: str) -> bytes:
    """Produce a fixed-size ASCII secret before bcrypt's 72-byte boundary."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest().encode("ascii")


def hash_password(password: str) -> str:
    digest = bcrypt.hashpw(_prehash(password), bcrypt.gensalt()).decode("ascii")
    return _PREHASH_PREFIX + digest


def verify_password(password: str, hashed: str) -> bool:
    try:
        if hashed.startswith(_PREHASH_PREFIX):
            return bcrypt.checkpw(
                _prehash(password), hashed[len(_PREHASH_PREFIX):].encode("ascii")
            )
        # Compatibility with accounts created by the original passlib/bcrypt
        # implementation. Such accounts could never contain more than 72 bytes.
        raw = password.encode("utf-8")
        return len(raw) <= 72 and bcrypt.checkpw(raw, hashed.encode("ascii"))
    except (ValueError, TypeError):
        return False


def create_access_token(user: User) -> tuple[str, datetime]:
    expires = datetime.now(UTC) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload = {"sub": str(user.id), "role": user.role, "exp": expires}
    return jwt.encode(payload, settings.secret_key, algorithm="HS256"), expires


async def current_user(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_session),
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired access token.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        user_id = uuid.UUID(payload.get("sub", ""))
    except (JWTError, ValueError):
        raise credentials_error from None
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise credentials_error
    return user


def require_permission(permission: Permission):
    async def dependency(user: User = Depends(current_user)) -> User:
        try:
            role = UserRole(user.role)
        except ValueError:
            raise HTTPException(status_code=403, detail="Unknown account role.") from None
        if permission not in ROLE_PERMISSIONS[role]:
            raise HTTPException(status_code=403, detail=f"Missing permission: {permission.value}.")
        return user
    return dependency
