"""Typed hand-offs between agents. Later steps decide on these objects, never on free text."""
from typing import Literal

from pydantic import BaseModel, Field


class JobSpec(BaseModel):
    job_id: str
    title: str
    deliverables: list[str] = Field(default_factory=list)
    required_skills: list[str] = Field(default_factory=list)
    budget_min: float | None = None
    budget_max: float | None = None
    timeline_days: int | None = None
    screening_questions: list[str] = Field(default_factory=list)
    hidden_needs: list[str] = Field(default_factory=list)


class RiskReport(BaseModel):
    score: float = Field(ge=0, le=1)
    flags: list[str] = Field(default_factory=list)
    explanation: str
    injection_detected: bool = False


class RequirementMatch(BaseModel):
    requirement: str
    evidence_ids: list[str] = Field(default_factory=list)
    strength: Literal["strong", "partial", "none"] = "none"


class FitReport(BaseModel):
    score: float = Field(ge=0, le=1)
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    matrix: list[RequirementMatch] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class BidDecision(BaseModel):
    action: Literal["skip", "watch", "bid"]
    reasons: list[str] = Field(default_factory=list)


class PriceQuote(BaseModel):
    bid_amount: float = Field(gt=0)
    market_low: float | None = None
    market_high: float | None = None
    connects_cost: int = 0
    worth_connects: bool = True
    rationale: str = ""


class ProposalDraft(BaseModel):
    job_id: str
    cover_letter: str
    screening_answers: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    status: str = "pending_review"
    revision: int = 0


class Critique(BaseModel):
    approved: bool
    issues: list[str] = Field(default_factory=list)
    revision: int = 0
    send_back: bool = False


class ComplianceVerdict(BaseModel):
    passed: bool
    violations: list[str] = Field(default_factory=list)
    cleaned_text: str | None = None