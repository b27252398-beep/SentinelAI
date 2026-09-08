import time
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.detection.models import DetectorConfig
from app.detection.engine import (
    get_tumbling_window,
    evaluate_z_score_detector,
    evaluate_static_threshold
)
from app.detection.repository import (
    get_db_connections_avg,
    get_memory_usage_avg,
    get_api_latency_p95,
    get_baseline_stats
)
from app.detection.lifecycle import process_detection_result
from app.detection.lock import DetectionLock

logger = logging.getLogger(__name__)

def process_config(db: Session, config: DetectorConfig, window_start: datetime, window_end: datetime):
    lock = DetectionLock(config.service_id, window_start)
    if not lock.acquire(ttl_seconds=60):
        logger.debug(f"Could not acquire lock for {config.id} at {window_start}")
        return
        
    try:
        # Get raw aggregate
        if config.detector_type == "DB Connection Exhaustion":
            observed_val, raw_count = get_db_connections_avg(db, config.service_id, window_start, window_end)
        elif config.detector_type == "Memory Leak":
            observed_val, raw_count = get_memory_usage_avg(db, config.service_id, window_start, window_end)
        elif config.detector_type == "API Latency":
            observed_val, raw_count = get_api_latency_p95(db, config.service_id, window_start, window_end)
        else:
            logger.warning(f"Unknown detector type {config.detector_type}")
            return
            
        if observed_val is None:
            observed_val = 0.0

        if "warning_threshold" in config.config or "critical_threshold" in config.config:
            # Static threshold
            result = evaluate_static_threshold(
                observed_val, raw_count, config.min_raw_samples,
                config.config, config.detector_type, str(config.id),
                config.version, window_start, window_end
            )
        else:
            # Z-score based
            baseline_start = window_start - timedelta(minutes=5 * config.min_baseline_observations)
            b_mean, b_stddev, b_count = get_baseline_stats(
                db, config.service_id, config.detector_type, baseline_start, window_start
            )
            
            result = evaluate_z_score_detector(
                observed_val, b_mean, b_stddev, raw_count, b_count,
                config.min_raw_samples, config.min_baseline_observations,
                config.detector_type, str(config.id), config.version,
                window_start, window_end
            )
            
        process_detection_result(db, config, window_start, window_end, result)
        
    except Exception as e:
        logger.exception(f"Error processing config {config.id}: {str(e)}")
    finally:
        lock.release()


def run_worker_iteration():
    now = datetime.now(timezone.utc)
    # The window that just completed
    window_end = get_tumbling_window(now)
    window_start = window_end - timedelta(minutes=5)
    
    db = SessionLocal()
    try:
        active_configs = db.execute(
            select(DetectorConfig).where(DetectorConfig.enabled == True)
        ).scalars().all()
        
        for config in active_configs:
            process_config(db, config, window_start, window_end)
    except Exception as e:
        logger.exception("Error in worker iteration")
    finally:
        db.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting Detection Worker...")
    while True:
        run_worker_iteration()
        # Sleep for a bit. A robust worker might sleep until the next 5-minute boundary
        # For simplicity, sleep 30 seconds and let idempotency/locks handle the rest.
        time.sleep(30)
