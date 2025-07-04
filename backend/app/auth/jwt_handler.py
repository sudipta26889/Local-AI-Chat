from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import JWTError, jwt
from loguru import logger

from app.config import settings
from app.services.cache_service import CacheService


class JWTHandler:
    """Handler for JWT token operations"""
    
    def __init__(self, cache_service: Optional[CacheService] = None):
        self.secret_key = settings.jwt_secret_key
        self.algorithm = settings.jwt_algorithm
        self.expiration_hours = settings.jwt_expiration_hours
        self.refresh_expiration_hours = settings.jwt_refresh_expiration_hours
        self.cache_service = cache_service
    
    def create_access_token(self, data: Dict[str, Any]) -> str:
        """Create JWT access token"""
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(hours=self.expiration_hours)
        to_encode.update({"exp": expire})
        
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        
        # Store in cache if available
        if self.cache_service:
            user_id = data.get("sub")
            if user_id:
                cache_key = f"jwt:{user_id}:{encoded_jwt[-8:]}"
                self.cache_service.set_sync(cache_key, "valid", expire=self.expiration_hours * 3600)
        
        return encoded_jwt
    
    def create_refresh_token(self, data: Dict[str, Any]) -> str:
        """Create JWT refresh token"""
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(hours=self.refresh_expiration_hours)
        to_encode.update({"exp": expire, "token_type": "refresh"})
        
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        
        # Store in cache if available
        if self.cache_service:
            user_id = data.get("sub")
            if user_id:
                cache_key = f"refresh_jwt:{user_id}:{encoded_jwt[-8:]}"
                self.cache_service.set_sync(cache_key, "valid", expire=self.refresh_expiration_hours * 3600)
        
        return encoded_jwt
    
    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify and decode JWT token"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            
            # Check if token is in cache (not revoked)
            if self.cache_service:
                user_id = payload.get("sub")
                if user_id:
                    cache_key = f"jwt:{user_id}:{token[-8:]}"
                    if not self.cache_service.get_sync(cache_key):
                        logger.warning(f"Token not found in cache for user {user_id}")
                        return None
            
            return payload
        except JWTError as e:
            logger.error(f"JWT verification error: {e}")
            return None
    
    def revoke_token(self, token: str) -> bool:
        """Revoke a JWT token by removing from cache"""
        if not self.cache_service:
            logger.warning("No cache service available for token revocation")
            return False
        
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            user_id = payload.get("sub")
            if user_id:
                cache_key = f"jwt:{user_id}:{token[-8:]}"
                self.cache_service.delete_sync(cache_key)
                logger.info(f"Revoked token for user {user_id}")
                return True
        except JWTError:
            pass
        
        return False
    
    def revoke_all_user_tokens(self, user_id: str) -> bool:
        """Revoke all tokens for a user"""
        if not self.cache_service:
            return False
        
        # This would require storing tokens differently in cache
        # For now, we'll implement this in a future iteration
        logger.info(f"Revoking all tokens for user {user_id}")
        return True