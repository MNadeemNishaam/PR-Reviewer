from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class AgentResult(BaseModel):
    agent_name: str = Field(..., description="Name of the agent (scout, guardian, etc.)")
    output: str = Field(..., description="Agent's analysis output")
    tokens_used: int = Field(0, description="Number of tokens consumed")
    model_used: str = Field(..., description="LLM model used")
    processing_time: float = Field(0.0, description="Processing time in seconds")
    error: Optional[str] = Field(None, description="Error message if any")


class ReviewResult(BaseModel):
    pr_id: int
    repository: str
    scout_result: Optional[AgentResult] = None
    guardian_result: Optional[AgentResult] = None
    architect_result: Optional[AgentResult] = None
    stylist_result: Optional[AgentResult] = None
    synthesizer_result: Optional[AgentResult] = None
    final_comment: Optional[str] = Field(None, description="Final synthesized comment")
    total_tokens: int = Field(0, description="Total tokens used across all agents")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class APIUsage(BaseModel):
    pr_id: int
    repository: str
    agent_name: str
    model: str
    tokens_used: int
    cost_estimate: float = Field(0.0, description="Estimated cost in USD")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

