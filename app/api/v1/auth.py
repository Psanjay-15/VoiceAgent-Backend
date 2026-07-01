from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.schemas.auth import AuthResponse, LoginRequest, SignupRequest
from app.services.security import create_access_token
from app.services.users import authenticate_user, create_user, to_public_user

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def signup(payload: SignupRequest) -> AuthResponse:
    user = await create_user(email=payload.email, password=payload.password)
    public = to_public_user(user)
    token = create_access_token(subject=public["id"], email=public["email"])
    return AuthResponse(access_token=token, user=public)


@router.post("/login", response_model=AuthResponse)
async def login(payload: LoginRequest) -> AuthResponse:
    user = await authenticate_user(email=payload.email, password=payload.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )
    public = to_public_user(user)
    token = create_access_token(subject=public["id"], email=public["email"])
    return AuthResponse(access_token=token, user=public)
