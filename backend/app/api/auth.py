"""Authentication API: register, login, logout, and current user info."""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import create_access_token, hash_password, verify_password
from app.db.base import get_db
from app.middleware.auth import AuthenticatedUser

logger = logging.getLogger(__name__)

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# Request/Response schemas
# ─────────────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: str
    role: str = "external"  # default role for self-registration


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserInfo"


class UserInfo(BaseModel):
    id: str
    email: str
    name: str
    role: str


# ─────────────────────────────────────────────────────────────────────────────
# Auth endpoints
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Register a new user account."""
    from app.models.user import User

    # Check if email already exists
    result = await db.execute(select(User.id).where(User.email == body.email))
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        name=body.name,
        role=body.role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    token = create_access_token(str(user.id), user.role, user.email)

    return AuthResponse(
        access_token=token,
        user=UserInfo(id=str(user.id), email=user.email, name=user.name, role=user.role),
    )


@router.post("/login")
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Login and receive a JWT access token."""
    from app.models.user import User

    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="User account is disabled")

    # Update last login time
    user.last_login_at = datetime.utcnow()
    await db.commit()

    token = create_access_token(str(user.id), user.role, user.email)

    return AuthResponse(
        access_token=token,
        user=UserInfo(id=str(user.id), email=user.email, name=user.name, role=user.role),
    )


@router.get("/me")
async def get_me(user: AuthenticatedUser):
    """Get current authenticated user info."""
    return UserInfo(id=str(user.id), email=user.email, name=user.name, role=user.role)


@router.post("/logout")
async def logout(user: AuthenticatedUser):
    """
    Logout current user.
    Note: Token invalidation would require a token blacklist (stored in Redis).
    For simplicity, this endpoint just confirms logout on the client side.
    """
    return {"message": "Logged out successfully"}


# Pydantic forward reference resolution
AuthResponse.model_rebuild()
