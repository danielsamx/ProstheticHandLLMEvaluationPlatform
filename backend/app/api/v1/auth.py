from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    ROLE_PERMISSIONS,
    Permission,
    create_access_token,
    current_user,
    hash_password,
    require_permission,
    verify_password,
)
from app.db.session import get_session
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.auth import LoginIn, PasswordChange, TokenOut, UserCreate, UserOut, UserUpdate

router = APIRouter(prefix="/auth", tags=["authentication"])


def _out(user: User) -> UserOut:
    role = UserRole(user.role)
    payload = UserOut.model_validate(user)
    payload.permissions = sorted(p.value for p in ROLE_PERMISSIONS[role])
    return payload


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(payload: UserCreate, session: AsyncSession = Depends(get_session)):
    if await session.scalar(select(User).where(func.lower(User.email) == payload.email.lower())):
        raise HTTPException(409, "An account with this email already exists.")
    count = await session.scalar(select(func.count()).select_from(User)) or 0
    role = UserRole.ADMIN if count == 0 else UserRole.OTHER
    user = User(email=payload.email.lower(), full_name=payload.full_name,
                institution=payload.institution, role=role.value,
                hashed_password=hash_password(payload.password))
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return _out(user)


@router.post("/login", response_model=TokenOut)
async def login(payload: LoginIn, session: AsyncSession = Depends(get_session)):
    user = await session.scalar(select(User).where(func.lower(User.email) == payload.email.lower()))
    if user is None or not user.is_active or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(401, "Invalid email or password.")
    token, expires = create_access_token(user)
    return TokenOut(access_token=token, expires_at=expires, user=_out(user))


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(current_user)):
    return _out(user)


@router.get("/users", response_model=list[UserOut])
async def users(_: User = Depends(require_permission(Permission.MANAGE_USERS)),
                session: AsyncSession = Depends(get_session)):
    return [_out(u) for u in (await session.scalars(select(User).order_by(User.created_at))).all()]


@router.post("/users", response_model=UserOut, status_code=201)
async def create_user(payload: UserCreate,
                      _: User = Depends(require_permission(Permission.MANAGE_USERS)),
                      session: AsyncSession = Depends(get_session)):
    if await session.scalar(select(User).where(func.lower(User.email) == payload.email.lower())):
        raise HTTPException(409, "An account with this email already exists.")
    user = User(email=payload.email.lower(), full_name=payload.full_name,
                institution=payload.institution, role=payload.role.value,
                hashed_password=hash_password(payload.password))
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return _out(user)


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_user(user_id: uuid.UUID, payload: UserUpdate,
                      actor: User = Depends(require_permission(Permission.MANAGE_USERS)),
                      session: AsyncSession = Depends(get_session)):
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found.")
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("role") is not None:
        changes["role"] = changes["role"].value
    if actor.id == user.id and changes.get("is_active") is False:
        raise HTTPException(400, "An administrator cannot deactivate their own session.")
    for key, value in changes.items():
        setattr(user, key, value)
    await session.commit()
    await session.refresh(user)
    return _out(user)


@router.post("/password", status_code=204)
async def change_password(payload: PasswordChange, user: User = Depends(current_user),
                          session: AsyncSession = Depends(get_session)):
    if not verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(400, "Current password is incorrect.")
    user.hashed_password = hash_password(payload.new_password)
    await session.commit()
