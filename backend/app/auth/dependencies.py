from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.database import get_db
from app.models.user import User
from app.auth.jwt_handler import JWTHandler
from app.services.cache_service import CacheService


# Security scheme
security = HTTPBearer()

# Global instances
_jwt_handler: Optional[JWTHandler] = None
_cache_service: Optional[CacheService] = None


def get_jwt_handler() -> JWTHandler:
    """Get JWT handler instance"""
    global _jwt_handler, _cache_service
    if not _jwt_handler:
        if not _cache_service:
            _cache_service = CacheService()
        _jwt_handler = JWTHandler(_cache_service)
    return _jwt_handler


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
    jwt_handler: JWTHandler = Depends(get_jwt_handler)
) -> User:
    """Get current authenticated user from JWT token"""
    token = credentials.credentials
    
    # Verify token
    payload = jwt_handler.verify_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
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
    
    return user


async def require_auth(user: User = Depends(get_current_user)) -> User:
    """Require authenticated user"""
    return user


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
    jwt_handler: JWTHandler = Depends(get_jwt_handler)
) -> Optional[User]:
    """Get current user if authenticated, otherwise None"""
    if not credentials:
        return None
    
    try:
        return await get_current_user(credentials, db, jwt_handler)
    except HTTPException:
        return None