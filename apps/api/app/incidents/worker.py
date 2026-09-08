"""
Correlation Worker — standalone process.

Runs independently of FastAPI. No Celery. No Kafka.
Pattern mirrors the Detection Worker (app/detection/worker.py).

Usage:
    python -m app.incidents.worker
"""
import time
import logging
from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.detection.models import AnomalyEvent
from app.incidents.models import IncidentAnomaly
from app.incidents.correlation import CorrelationLock, process_anomaly

logger = logging.getLogger(__name__)


def _get_unattached_open_anomalies(db: Session) -> list[AnomalyEvent]:
    """
    Query OPEN anomaly_events not yet present in incident_anomalies.

    Attachment state is determined exclusively by querying incident_anomalies.
    This function does NOT read or write anomaly_events.status beyond filtering
    for OPEN. It does NOT add any field to anomaly_events.
    """
    attached_subq = select(IncidentAnomaly.anomaly_id)
    return db.execute(
        select(AnomalyEvent).where(
            and_(
                AnomalyEvent.status == "OPEN",
                AnomalyEvent.id.notin_(attached_subq),
            )
        ).order_by(AnomalyEvent.window_start.asc())
    ).scalars().all()


def run_worker_iteration() -> None:
    """One pass: find all unattached OPEN anomalies, correlate per service."""
    db = SessionLocal()
    try:
        unattached = _get_unattached_open_anomalies(db)
        if not unattached:
            return

        # Group by service_id for per-service locking
        by_service: dict = {}
        for anomaly in unattached:
            by_service.setdefault(anomaly.service_id, []).append(anomaly)

        for service_id, anomalies in by_service.items():
            lock = CorrelationLock(service_id)
            if not lock.acquire(ttl_seconds=30):
                logger.debug(
                    f"[correlation-worker] Could not acquire lock for "
                    f"service {service_id} — skipping this iteration"
                )
                continue
            try:
                for anomaly in anomalies:
                    try:
                        process_anomaly(db, anomaly)
                    except Exception as exc:
                        logger.exception(
                            f"[correlation-worker] Error processing anomaly "
                            f"{anomaly.id}: {exc}"
                        )
                        # Failure is isolated per anomaly — continue to next
            finally:
                lock.release()

    except Exception as exc:
        logger.exception(
            f"[correlation-worker] Fatal error in worker iteration: {exc}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting Correlation Worker...")
    while True:
        run_worker_iteration()
        time.sleep(30)
