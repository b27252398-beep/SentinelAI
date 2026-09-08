import redis
from app.core.config import settings

def get_redis_client() -> redis.Redis:
    return redis.Redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        socket_timeout=5.0
    )
