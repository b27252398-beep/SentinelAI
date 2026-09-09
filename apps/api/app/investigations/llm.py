import json
import asyncio
import uuid
from typing import List, Dict, Any, Optional
from abc import ABC, abstractmethod
from pydantic import BaseModel, ValidationError

class LLMHypothesis(BaseModel):
    statement: str
    reasoning: str
    confidence: float
    supporting_evidence_ids: List[str]
    contradicting_evidence_ids: List[str]

class LLMResponse(BaseModel):
    hypotheses: List[LLMHypothesis]

class LLMRecommendation(BaseModel):
    title: str
    description: str
    rationale: str
    recommendation_type: str
    expected_effect: str
    risk_level: str
    confidence: float
    preconditions: List[str]
    validation_steps: List[str]
    rollback_guidance: str

class LLMRecommendationResponse(BaseModel):
    recommendation: LLMRecommendation

class LLMProvider(ABC):
    @abstractmethod
    async def generate_hypotheses(self, prompt: str, evidence: str) -> LLMResponse:
        pass
    
    @abstractmethod
    async def generate_recommendations(self, prompt: str, rca_statement: str, evidence: str) -> LLMRecommendationResponse:
        pass

    @property
    @abstractmethod
    def model_identifier(self) -> str:
        pass


class DevMockLLMProvider(LLMProvider):
    """
    A safe development/test provider that deterministically returns 
    structured JSON without requiring an external API key.
    """
    def __init__(self, should_fail: bool = False, malformed: bool = False, timeout: bool = False):
        self.should_fail = should_fail
        self.malformed = malformed
        self.timeout = timeout
        
    @property
    def model_identifier(self) -> str:
        return "mock-dev-llm-v1"

    async def generate_hypotheses(self, prompt: str, evidence: str) -> LLMResponse:
        if self.timeout:
            await asyncio.sleep(65)
            raise TimeoutError("LLM Request Timed Out")
        
        if self.should_fail:
            raise RuntimeError("LLM Service Unavailable")
            
        if self.malformed:
            raise ValueError("Malformed JSON returned by LLM")

        h1 = LLMHypothesis(
            statement="Database connection pool was exhausted due to high load.",
            reasoning="Observed latency spike and db_connections metric maxed out.",
            confidence=0.8,
            supporting_evidence_ids=["dummy-id-1"],
            contradicting_evidence_ids=[]
        )
        h2 = LLMHypothesis(
            statement="Network partition between API and Database.",
            reasoning="Errors occurred but DB metrics showed idle.",
            confidence=0.4,
            supporting_evidence_ids=["dummy-id-2"],
            contradicting_evidence_ids=["dummy-id-1"]
        )
        return LLMResponse(hypotheses=[h1, h2])

    async def generate_recommendations(self, prompt: str, rca_statement: str, evidence: str) -> LLMRecommendationResponse:
        if self.timeout:
            await asyncio.sleep(65)
            raise TimeoutError("LLM Request Timed Out")
        
        if self.should_fail:
            raise RuntimeError("LLM Service Unavailable")
            
        if self.malformed:
            raise ValueError("Malformed JSON returned by LLM")
            
        return LLMRecommendationResponse(
            recommendation=LLMRecommendation(
                title="Scale up DB connection pool",
                description="Increase max_connections in Postgres config.",
                rationale=f"Addresses RCA: {rca_statement}",
                recommendation_type="CONFIGURATION_CHANGE",
                expected_effect="Errors will drop, latency will stabilize.",
                risk_level="MEDIUM",
                confidence=0.85,
                preconditions=["DB is currently in healthy CPU state"],
                validation_steps=["Monitor db_connections metric", "Check error rates"],
                rollback_guidance="Revert max_connections to previous value."
            )
        )


# A factory or dependency injection can provide the real one in prod.
def get_llm_provider() -> LLMProvider:
    return DevMockLLMProvider()
