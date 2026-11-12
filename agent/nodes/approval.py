"""Human approval gate (R4/C5): preview -> interrupt() -> submit | apply_edit | stop."""
import difflib
import re

from langgraph.types import interrupt

from agent.mcp_client import call
from agent.nodes.common import step


def _key(state, what: str) -> str:
    return f"{state['persona_id']}:{state['job_id']}:{what}"  # deterministic: retries reuse it


async def preview(state):
    """dry_run: exactly what would be sent and what it costs. Read-only, safe to re-run."""
    d, q = state["proposal_draft"], state["price_quote"]
    try:
        p = await call("preview", "marketplace", "create_proposal_draft", dict(
            job_id=state["job_id"], cover_letter=d["cover_letter"], bid_amount=q["bid_amount"],
            screening_answers=d["screening_answers"], idempotency_key=_key(state, "create"), dry_run=True))
    except Exception as e:  # e.g. marketplace policy rejects the text: show it to the human
        p = {"error": str(e)}
    return {"preview": p, "status": "needs_approval", **step("preview", ok="error" not in p)}


async def approval(state):
    d, q, cv = state["proposal_draft"], state["price_quote"], state["claim_verification"]
    crit, risk, pv = state["critique"], state["risk_report"], state["preview"]
    ev = {e["evidence_id"]: dict(title=e["title"], type=e["type"], text=e["text"])
          for e in state.get("evidence", [])}
    warnings = []
    if not crit["approved"]:
        warnings.append("Critic did not approve the final draft: " + "; ".join(crit["issues"]))
    if not q["worth_connects"]:
        warnings.append("Connects cost may not be worth it for this job")
    if "error" in pv:
        warnings.append(f"Marketplace dry-run failed: {pv['error']}")
    if risk["flags"]:
        warnings.append(f"Risk flags: {risk['flags']}")
    answer = interrupt(dict(
        job_id=state["job_id"], title=state["job"]["title"], draft=d, price=q, risk_report=risk,
        claims=[dict(c, evidence={i: ev[i] for i in c["evidence_ids"] if i in ev}) for c in cv["claims"]],
        preview=pv, warnings=warnings, edited=bool(state.get("edits"))))
    action = answer.get("action") if isinstance(answer, dict) else None
    if action not in ("approve", "edit"):  # fail closed: anything else is a rejection
        answer = {"action": "reject", "reason": (answer or {}).get("reason", "rejected")}
        action = "reject"
    status = {"approve": "approved", "edit": "edited", "reject": "rejected"}[action]
    return {"approval": answer, "status": status, **step("approval", action=action)}


def _sents(t: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", t.strip()) if s]


async def apply_edit(state):
    """Save the diff (feeds style memory in 9f); the edited text goes back through Compliance."""
    d = state["proposal_draft"]
    old, new = d["cover_letter"], (state["approval"].get("edited_text") or "").strip() or d["cover_letter"]
    diff = "\n".join(difflib.unified_diff(_sents(old), _sents(new), lineterm="", n=0))
    return {"proposal_draft": dict(d, cover_letter=new), "status": "running",
            "edits": [dict(job_id=state["job_id"], before=old, after=new, diff=diff)],
            **step("apply_edit", changed=old != new)}


async def submit(state):
    d, q = state["proposal_draft"], state["price_quote"]
    try:  # both keys are deterministic, so a crash/resume/replay never submits or charges twice
        draft = await call("submit", "marketplace", "create_proposal_draft", dict(
            job_id=state["job_id"], cover_letter=d["cover_letter"], bid_amount=q["bid_amount"],
            screening_answers=d["screening_answers"], idempotency_key=_key(state, "create")))
        rec = await call("submit", "marketplace", "submit_proposal",
                         dict(proposal_id=draft["id"], idempotency_key=_key(state, "submit")))
    except Exception as e:
        return {"status": "needs_attention", "errors": [f"submit failed: {e}"], **step("submit", error=str(e))}
    return {"submission": rec, "status": "submitted", **step("submit", proposal_id=rec["id"])}