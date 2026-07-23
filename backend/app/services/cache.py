import redis.asyncio as redis
from typing import Optional, Any
import json
from app.core.config import get_settings

settings = get_settings()

class CacheService:
    def __init__(self):
        self.redis = redis.from_url(settings.redis_url, decode_responses=True)

    async def get(self, key: str) -> Optional[Any]:
        val = await self.redis.get(key)
        if val:
            try:
                return json.loads(val)
            except json.JSONDecodeError:
                return val
        return None

    async def set(self, key: str, value: Any, ex: int = 3600):
        if isinstance(value, (dict, list)):
            value = json.dumps(value)
        await self.redis.set(key, value, ex=ex)

    async def delete(self, key: str):
        await self.redis.delete(key)

    async def get_client(self):
        return self.redis

cache_service = CacheService()
