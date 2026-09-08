from typing import List
import json
from sqlalchemy.orm import Session
from app.investigations.models import Investigation, Hypothesis, Recommendation
from app.investigations.normalizer import normalize_evidence
from app.investigations.llm import get_llm_provider, LLMHypothesis

def _score_hypothesis(h: LLMHypothesis) -> float:
    """
    Deterministic hypothesis evaluation:
    - Base confidence from LLM
    - +0.1 per supporting evidence ID (up to some max to prevent gaming? Let's say +0.1 each)
    - -0.2 per contradicting evidence ID
    """
    score = h.confidence
    # Evidence support
    score += (0.1 * len(h.supporting_evidence_ids))
    # Contradiction penalty
    score -= (0.2 * len(h.contradicting_evidence_ids))
    return score

async def evaluate_and_persist_hypotheses(
    db: Session, 
    investigation: Investigation, 
    llm_hypotheses: List[LLMHypothesis]
):
    """
    Evaluates LLM hypotheses, ranks them, selects Probable Root Cause, and saves.
    """
    if not llm_hypotheses:
        # No credible root cause
        fallback = Hypothesis(
            investigation_id=investigation.id,
            statement="Insufficient Evidence / No Hypotheses generated.",
            confidence=0.0,
            reasoning="The LLM returned no hypotheses.",
            is_probable_root_cause=True
        )
        db.add(fallback)
        db.commit()
        return
        
    scored = []
    for h in llm_hypotheses:
        # Score the hypothesis
        final_score = _score_hypothesis(h)
        scored.append((final_score, h))
        
    # Rank them
    scored.sort(key=lambda x: x[0], reverse=True)
    
    # Check for conflicts / low confidence
    top_score, top_h = scored[0]
    
    # Save all hypotheses
    db_hypotheses = []
    for idx, (score, h) in enumerate(scored):
        is_rc = (idx == 0) # Top is probable root cause
        
        statement = h.statement
        if is_rc:
            if score < 0.4:
                statement = "[Probable Root Cause (Low Confidence - Inconclusive)] " + statement
            # Check for conflict (e.g. #1 and #2 have identical scores and conflicting evidence)
            if len(scored) > 1 and score == scored[1][0] and h.contradicting_evidence_ids:
                statement = "[Conflicting Evidence - Manual Investigation Required] " + statement
                
        db_h = Hypothesis(
            investigation_id=investigation.id,
            statement=statement,
            confidence=score, # store the adjusted score
            reasoning=h.reasoning,
            is_probable_root_cause=is_rc,
            supporting_evidence_ids=h.supporting_evidence_ids,
            contradicting_evidence_ids=h.contradicting_evidence_ids
        )
        db_hypotheses.append(db_h)
        db.add(db_h)
        
    db.commit()
    
    # Optionally generate a stub recommendation for the RC (as required by architecture, 
    # the subsystem drafts recommendations for the probable root cause).
    for db_h in db_hypotheses:
        if db_h.is_probable_root_cause:
            # Draft recommendation
            rec = Recommendation(
                investigation_id=investigation.id,
                hypothesis_id=db_h.id,
                action_description="Review logs and address the identified root cause.",
                risk_level="Low",
                status="pending"
            )
            db.add(rec)
            db.commit()
            break
