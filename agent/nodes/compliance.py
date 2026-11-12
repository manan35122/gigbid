"""Compliance Guard: enforce the policy pack by deleting offending sentences; block if the draft is unusable."""
import re

from agent.handoffs import ComplianceVerdict
from agent.nodes.common import cfg, step

RULES = {
    "email": re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),
    "phone": re.compile(r"\+?\d[\d\s().-]{8,}\d"),
    "link": re.compile(r"https?://\S+|www\.\S+", re.I),
    "guarantee": re.compile(r"\bguarantee[sd]?\b|100\s*%\s*(success|satisf)|risk[- ]free", re.I),
}


async def compliance(state):
    d, pol, viol = state["proposal_draft"], cfg()["policy"], []

    def clean(text: str) -> str:
        keep = []
        for s in re.split(r"(?<=[.!?])\s+|\n+", text.strip()):
            hit = [n for n, rx in RULES.items() if rx.search(s)] + [b for b in pol["banned_phrases"] if b in s.lower()]
            if hit:
                viol.extend(f"{h}: removed '{s[:60]}'" for h in hit)
            elif s.strip():
                keep.append(s.strip())
        return " ".join(keep)

    cover = clean(d["cover_letter"])
    answers = [clean(a) for a in d["screening_answers"]]
    words = len(cover.split())
    ok = pol["min_proposal_words"] <= words <= pol["max_proposal_words"]
    if not ok:
        viol.append(f"BLOCKED: length {words} words outside {pol['min_proposal_words']}-{pol['max_proposal_words']}")
    v = ComplianceVerdict(passed=ok, violations=viol, cleaned_text=cover)
    return {"proposal_draft": dict(d, cover_letter=cover, screening_answers=answers),
            "compliance_verdict": v.model_dump(), "status": "ready_for_approval" if ok else "blocked",
            **step("compliance", passed=ok, removed=len(viol))}