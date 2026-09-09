import re
from typing import Optional
from sqlalchemy.orm import Session
from app.investigations.models import Investigation, Hypothesis
from app.services.models import Service
from app.recommendations.models import Recommendation

ALLOWED_TYPES = {
    "CONFIGURATION_CHANGE",
    "RESOURCE_SCALING",
    "DEPLOYMENT_ROLLBACK",
    "TRAFFIC_MITIGATION",
    "DATABASE_REMEDIATION",
    "DEPENDENCY_RECOVERY"
}

ALLOWED_RISK = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}

DESTRUCTIVE_KEYWORDS = ["rm -rf", "drop table", "truncate table", "delete from"]

def validate_recommendation(db: Session, recommendation: Recommendation) -> tuple[bool, Optional[str]]:
    """
    Deterministic safety validator.
    Returns (True, None) if safe.
    Returns (False, "reason") if fails.
    """
    # 1. Investigation check
    inv = db.query(Investigation).filter(Investigation.id == recommendation.investigation_id).first()
    if not inv or inv.status != "complete":
        return False, "Investigation not found or not complete."

    # 2. Hypothesis check
    hyp = db.query(Hypothesis).filter(Hypothesis.id == recommendation.hypothesis_id).first()
    if not hyp:
        return False, "RCA hypothesis not found."

    if not hyp.is_probable_root_cause:
        return False, "Hypothesis is not the probable root cause."

    if hyp.confidence < 0.4:
        return False, "RCA confidence is too low for automated recommendation."

    # 3. Target service check
    svc = db.query(Service).filter(Service.id == recommendation.target_service_id).first()
    if not svc:
        return False, "Target service not found."

    # 4. Taxonomy check
    if recommendation.recommendation_type not in ALLOWED_TYPES:
        return False, f"Unsupported recommendation type: {recommendation.recommendation_type}"

    # 5. Risk classification
    if recommendation.risk_level not in ALLOWED_RISK:
        return False, f"Unsupported risk level: {recommendation.risk_level}"

    # 6. Destructive keyword check
    text_corpus = f"{recommendation.description} {recommendation.expected_effect}".lower()
    for keyword in DESTRUCTIVE_KEYWORDS:
        if keyword in text_corpus:
            if recommendation.recommendation_type != "DATABASE_REMEDIATION":
                return False, f"Unauthorized destructive command detected: {keyword}"

    # 7. Rollback guidance
    if not recommendation.rollback_guidance or len(recommendation.rollback_guidance.strip()) < 5:
        return False, "Rollback guidance is missing or insufficient."

    return True, None
