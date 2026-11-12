"""Graph state. Three things are kept apart:
 - STATE: what this job needs right now (this file)
 - TRACE: append-only record of every step/tool call (`trace`), for audit and debugging
 - LONG-TERM MEMORY: promoted knowledge only, in a LangGraph store (agent/memory/), never raw tool output
"""
import operator
from typing import Annotated, Any, TypedDict


class GigBidState(TypedDict, total=False):
    job_id: str
    persona_id: str
    job: dict[str, Any]
    client: dict[str, Any]
    job_spec: dict[str, Any]
    risk_report: dict[str, Any]
    fit_report: dict[str, Any]
    evidence: list[dict[str, Any]]
    decision: dict[str, Any]
    price_quote: dict[str, Any]
    proposal_draft: dict[str, Any]
    claim_verification: dict[str, Any]
    critique: dict[str, Any]
    compliance_verdict: dict[str, Any]
    revisions: int
    approval: dict[str, Any]
    submission: dict[str, Any]
    status: str
    steps: Annotated[int, operator.add]
    tokens: Annotated[int, operator.add]
    trace: Annotated[list[dict[str, Any]], operator.add]
    errors: Annotated[list[str], operator.add]
    preview: dict[str, Any]
    edits: Annotated[list[dict[str, Any]], operator.add]