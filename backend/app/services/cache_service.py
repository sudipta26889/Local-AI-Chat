import json
from typing import Optional, Any, Dict, List
import redis.asyncio as aioredis
import redis
from loguru import logger

from app.config import settings


class CacheService:
    """Service for Redis caching operations"""
    
    def __init__(self):
        self.redis_url = settings.redis_url
        self.async_client: Optional[aioredis.Redis] = None
        self.sync_client: Optional[redis.Redis] = None
    
    async def initialize(self):
        """Initialize Redis connection"""
        try:
            self.async_client = await aioredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True
            )
            await self.async_client.ping()
            logger.info("Redis async connection established")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise
    
    def _get_sync_client(self) -> redis.Redis:
        """Get synchronous Redis client"""
        if not self.sync_client:
            self.sync_client = redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True
            )
        return self.sync_client
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        if not self.async_client:
            return None
        
        try:
            value = await self.async_client.get(key)
            if value:
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    return value
            return None
        except Exception as e:
            logger.error(f"Cache get error: {e}")
            return None
    
    def get_sync(self, key: str) -> Optional[Any]:
        """Get value from cache synchronously"""
        try:
            client = self._get_sync_client()
            value = client.get(key)
            if value:
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    return value
            return None
        except Exception as e:
            logger.error(f"Cache get error: {e}")
            return None
    
    async def set(self, key: str, value: Any, expire: Optional[int] = None) -> bool:
        """Set value in cache"""
        if not self.async_client:
            return False
        
        try:
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            
            if expire:
                await self.async_client.setex(key, expire, value)
            else:
                await self.async_client.set(key, value)
            return True
        except Exception as e:
            logger.error(f"Cache set error: {e}")
            return False
    
    def set_sync(self, key: str, value: Any, expire: Optional[int] = None) -> bool:
        """Set value in cache synchronously"""
        try:
            client = self._get_sync_client()
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            
            if expire:
                client.setex(key, expire, value)
            else:
                client.set(key, value)
            return True
        except Exception as e:
            logger.error(f"Cache set error: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete key from cache"""
        if not self.async_client:
            return False
        
        try:
            await self.async_client.delete(key)
            return True
        except Exception as e:
            logger.error(f"Cache delete error: {e}")
            return False
    
    def delete_sync(self, key: str) -> bool:
        """Delete key from cache synchronously"""
        try:
            client = self._get_sync_client()
            client.delete(key)
            return True
        except Exception as e:
            logger.error(f"Cache delete error: {e}")
            return False
    
    async def exists(self, key: str) -> bool:
        """Check if key exists in cache"""
        if not self.async_client:
            return False
        
        try:
            return await self.async_client.exists(key) > 0
        except Exception as e:
            logger.error(f"Cache exists error: {e}")
            return False
    
    async def get_keys(self, pattern: str) -> List[str]:
        """Get keys matching pattern"""
        if not self.async_client:
            return []
        
        try:
            return await self.async_client.keys(pattern)
        except Exception as e:
            logger.error(f"Cache keys error: {e}")
            return []
    
    async def increment(self, key: str, amount: int = 1) -> Optional[int]:
        """Increment a counter"""
        if not self.async_client:
            return None
        
        try:
            return await self.async_client.incrby(key, amount)
        except Exception as e:
            logger.error(f"Cache increment error: {e}")
            return None
    
    async def set_hash(self, key: str, field: str, value: Any) -> bool:
        """Set hash field value"""
        if not self.async_client:
            return False
        
        try:
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            await self.async_client.hset(key, field, value)
            return True
        except Exception as e:
            logger.error(f"Cache hset error: {e}")
            return False
    
    async def get_hash(self, key: str, field: str) -> Optional[Any]:
        """Get hash field value"""
        if not self.async_client:
            return None
        
        try:
            value = await self.async_client.hget(key, field)
            if value:
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    return value
            return None
        except Exception as e:
            logger.error(f"Cache hget error: {e}")
            return None
    
    async def get_all_hash(self, key: str) -> Dict[str, Any]:
        """Get all hash fields"""
        if not self.async_client:
            return {}
        
        try:
            data = await self.async_client.hgetall(key)
            result = {}
            for field, value in data.items():
                try:
                    result[field] = json.loads(value)
                except json.JSONDecodeError:
                    result[field] = value
            return result
        except Exception as e:
            logger.error(f"Cache hgetall error: {e}")
            return {}
    
    async def close(self):
        """Close Redis connection"""
        if self.async_client:
            await self.async_client.close()
        if self.sync_client:
            self.sync_client.close()