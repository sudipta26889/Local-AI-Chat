from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.models.database import get_db
from app.auth.ldap_auth import LDAPAuthService
from app.auth.jwt_handler import JWTHandler
from app.auth.dependencies import get_current_user, get_jwt_handler
from app.models.user import User
from app.services.cache_service import CacheService


router = APIRouter()
security = HTTPBearer()


class LoginRequest(BaseModel):
    username: str
    password: str
    remember_me: bool = True


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: str
    ldap_uid: str
    email: Optional[str]
    display_name: Optional[str]
    created_at: str
    last_login: Optional[str]


@router.post("/login", response_model=LoginResponse)
async def login(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db),
    jwt_handler: JWTHandler = Depends(get_jwt_handler)
):
    """Login with LDAP credentials"""
    # Initialize LDAP service
    ldap_service = LDAPAuthService()
    
    # Authenticate against LDAP
    ldap_data = ldap_service.authenticate(request.username, request.password)
    if not ldap_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    
    # Get or create user in database
    user = await ldap_service.get_or_create_user(db, ldap_data)
    
    # Create JWT tokens
    token_data = {
        "sub": str(user.id),
        "ldap_uid": user.ldap_uid,
        "display_name": user.display_name
    }
    access_token = jwt_handler.create_access_token(token_data)
    refresh_token = jwt_handler.create_refresh_token(token_data)
    
    logger.info(f"User {user.ldap_uid} logged in successfully")
    
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=jwt_handler.expiration_hours * 3600,  # in seconds
        user=user.to_dict()
    )


@router.post("/logout")
async def logout(
    current_user: User = Depends(get_current_user),
    jwt_handler: JWTHandler = Depends(get_jwt_handler),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Logout and revoke token"""
    token = credentials.credentials
    success = jwt_handler.revoke_token(token)
    
    if success:
        logger.info(f"User {current_user.ldap_uid} logged out")
        return {"message": "Logged out successfully"}
    else:
        return {"message": "Logout completed"}


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """Get current user information"""
    return UserResponse(
        id=str(current_user.id),
        ldap_uid=current_user.ldap_uid,
        email=current_user.email,
        display_name=current_user.display_name,
        created_at=current_user.created_at.isoformat(),
        last_login=current_user.last_login.isoformat() if current_user.last_login else None
    )


@router.put("/me/preferences")
async def update_user_preferences(
    preferences: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update user preferences"""
    current_user.preferences = preferences
    await db.commit()
    await db.refresh(current_user)
    
    return {"message": "Preferences updated successfully", "preferences": current_user.preferences}


@router.post("/refresh", response_model=LoginResponse)
async def refresh_access_token(
    request: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
    jwt_handler: JWTHandler = Depends(get_jwt_handler)
):
    """Refresh access token using refresh token"""
    # Verify refresh token
    payload = jwt_handler.verify_token(request.refresh_token)
    if not payload or payload.get("token_type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )
    
    # Get user from database
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )
    
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    # Create new tokens
    token_data = {
        "sub": str(user.id),
        "ldap_uid": user.ldap_uid,
        "display_name": user.display_name
    }
    new_access_token = jwt_handler.create_access_token(token_data)
    new_refresh_token = jwt_handler.create_refresh_token(token_data)
    
    # Revoke old refresh token
    jwt_handler.revoke_token(request.refresh_token)
    
    logger.info(f"Tokens refreshed for user {user.ldap_uid}")
    
    return LoginResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        expires_in=jwt_handler.expiration_hours * 3600,
        user=user.to_dict()
    )


# Import at the end to avoid circular import
from typing import Optional
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

security = HTTPBearer()