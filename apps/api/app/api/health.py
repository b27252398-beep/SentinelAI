from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.db.session import get_db
from app.db.redis import get_redis_client
import redis
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/health")
def health_check():
    """Basic health check indicating the API is running."""
    return {"status": "ok"}

@router.get("/ready")
def readiness_check(db: Session = Depends(get_db)):
    """Verifies dependencies (PostgreSQL, Redis) are available."""
    dependencies = {
        "database": "down",
        "redis": "down"
    }
    is_ready = True

    # Check Database
    try:
        db.execute(text("SELECT 1"))
        dependencies["database"] = "up"
    except Exception as e:
        logger.error(f"Readiness check failed - Database unavailable: {str(e)}")
        is_ready = False

    # Check Redis
    try:
        redis_client = get_redis_client()
        if redis_client.ping():
            dependencies["redis"] = "up"
    except redis.RedisError as e:
        logger.error(f"Readiness check failed - Redis unavailable: {str(e)}")
        is_ready = False
    except Exception as e:
        logger.error(f"Readiness check failed - Redis check exception: {str(e)}")
        is_ready = False

    if not is_ready:
        raise HTTPException(
            status_code=503,
            detail={"status": "unavailable", "dependencies": dependencies}
        )

    return {"status": "ready", "dependencies": dependencies}
