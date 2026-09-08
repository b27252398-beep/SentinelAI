import uuid
from datetime import datetime
from app.db.redis import get_redis_client

class DetectionLock:
    def __init__(self, service_id: uuid.UUID, window_start: datetime):
        self.redis = get_redis_client()
        self.lock_key = f"lock:detection:{service_id}:{window_start.isoformat()}"
        self.token = str(uuid.uuid4())
        
        # Lua script to ensure we only delete the lock if we still own it
        self.release_script = self.redis.register_script("""
            if redis.call("get", KEYS[1]) == ARGV[1] then
                return redis.call("del", KEYS[1])
            else
                return 0
            end
        """)

    def acquire(self, ttl_seconds: int = 60) -> bool:
        """Attempt to acquire the distributed lock."""
        # SET NX EX
        res = self.redis.set(self.lock_key, self.token, nx=True, ex=ttl_seconds)
        return bool(res)

    def release(self) -> bool:
        """Release the distributed lock safely using Lua script."""
        res = self.release_script(keys=[self.lock_key], args=[self.token])
        return bool(res)
