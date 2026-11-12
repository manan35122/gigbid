"""Parallel analysis nodes: Job Analyst, Risk Assessor, Fit Matcher. Pydantic hand-offs out."""
import asyncio
import json
import re

from agent.handoffs import FitReport, JobSpec, RequirementMatch, RiskReport
from agent.llm import chat, prompt
from agent.mcp_client import call
from agent.nodes.common import cfg, step

INJECTION = re.compile(r"ignore (all )?(previous|prior) instructions|system note|disregard .*instructions|"
                       r"you are now|approve (it )?automatically", re.I)
OFFPLATFORM = re.compile(r"whatsapp|telegram|paypal|outside (of )?the platform|off[- ]platform|skype", re.I)
UNPAID = re.compile(r"unpaid|free (test|trial|sample)|for free|without pay", re.I)


async def load_job(state):
    try:
        job = await call("load_job", "marketplace", "get_job", {"job_id": state["job_id"]})
        client = await call("load_job", "marketplace", "get_client_history", {"client_id": job["client_id"]})
    except Exception as e:  # marketplace down -> visible needs_attention state, not a crash
        return {"status": "needs_attention", "errors": [f"marketplace unavailable: {e}"],
                **step("load_job", error=str(e))}
    return {"job": job, "client": client, "status": "running", **step("load_job", job_id=job["job_id"])}


async def analyst(state):
    j = state["job"]
    spec = dict(job_id=j["job_id"], title=j["title"], required_skills=j["required_skills"],
                budget_min=j["budget"]["min"], budget_max=j["budget"]["max"],
                timeline_days=j.get("duration_days"), screening_questions=j.get("screening_questions", []))
    try:
        out = await asyncio.to_thread(chat, "analyst", prompt("analyst"),
                                      f"<job_post>\n{j['title']}\n{j['description']}\n</job_post>")
        m = re.search(r"\{.*\}", out, re.S)
        extra = json.loads(m.group(0)) if m else {}
        spec["deliverables"] = [str(x) for x in extra.get("deliverables", [])][:5]
        spec["hidden_needs"] = [str(x) for x in extra.get("hidden_needs", [])][:3]
    except Exception:
        pass  # degraded: structured fields from the post itself are still usable
    return {"job_spec": JobSpec(**spec).model_dump(), **step("analyst")}


async def risk_assessor(state):
    j, c = state["job"], state["client"]
    text = f"{j['title']} {j['description']}"
    flags = []
    if INJECTION.search(text):
        flags.append("prompt_injection")
    if OFFPLATFORM.search(text):
        flags.append("off_platform_contact")
    if UNPAID.search(text) or j["budget"]["max"] == 0:
        flags.append("unpaid_work")
    if c["completed_projects"] < 4 or c["average_rating"] < 4.4 or c["hire_rate"] < 0.3:
        flags.append("weak_client")
    hard = {"prompt_injection", "off_platform_contact", "unpaid_work"} & set(flags)
    score = min(1.0, 0.85 * bool(hard) + 0.2 * ("weak_client" in flags) + 0.1)
    rep = RiskReport(score=score, flags=flags, injection_detected="prompt_injection" in flags,
                     explanation=f"flags={flags}; client rating {c['average_rating']}, "
                                 f"{c['completed_projects']} projects, hire rate {c['hire_rate']}")
    return {"risk_report": rep.model_dump(), **step("risk_assessor", flags=flags)}


async def fit_matcher(state):
    from rag.variants.v1_decompose import decompose  # V1 decomposition won the RAG eval
    j, t = state["job"], cfg()["thresholds"]
    strong, partial = t.get("strong_evidence_score", 0.65), t.get("partial_evidence_score", 0.55)
    reqs = await asyncio.to_thread(decompose, f"{j['title']}. {j['description']}")
    matrix, seen = [], {}
    for r in reqs:
        hits = await call("fit_matcher", "portfolio", "search_evidence",
                          {"requirement": r, "k": 3, "persona_id": state["persona_id"]})
        top = hits[0]["score"] if hits else 0
        for h in hits:
            seen.setdefault(h["evidence_id"], h)
        matrix.append(RequirementMatch(requirement=r, evidence_ids=[h["evidence_id"] for h in hits],
                                       strength="strong" if top >= strong else "partial" if top >= partial else "none"))
    ev_text = " ".join(f"{h['text']} {' '.join(h['skills'])}" for h in seen.values()).lower()
    req_skills = j["required_skills"]
    matched = [s for s in req_skills if s.lower() in ev_text]
    cov = len(matched) / max(len(req_skills), 1)
    rq = sum({"strong": 1, "partial": .5, "none": 0}[m.strength] for m in matrix) / max(len(matrix), 1)
    rep = FitReport(score=round(0.5 * cov + 0.5 * rq, 3), matched_skills=matched,
                    missing_skills=[s for s in req_skills if s not in matched],
                    evidence_ids=list(seen), matrix=matrix,
                    reasons=[f"skill coverage {cov:.2f}, requirement strength {rq:.2f}"])
    return {"fit_report": rep.model_dump(), "evidence": list(seen.values()), **step("fit_matcher")}