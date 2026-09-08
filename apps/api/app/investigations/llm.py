import json
import asyncio
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

class LLMProvider(ABC):
    @abstractmethod
    async def generate_hypotheses(self, prompt: str, evidence: str) -> LLMResponse:
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
            # We bypass the standard return and simulate a raw JSON parse error in the caller,
            # or just raise ValidationError by feeding it bad data if we structured it that way.
            # But the caller expects LLMResponse. 
            # We'll simulate a failure that the caller's try/except for malformed JSON would catch.
            raise ValueError("Malformed JSON returned by LLM")

        # Extract evidence IDs to pretend we reasoned about them
        # In a real mock we might regex them out, but for tests we can just return dummy
        
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


# A factory or dependency injection can provide the real one in prod.
def get_llm_provider() -> LLMProvider:
    return DevMockLLMProvider()
