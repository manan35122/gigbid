"""Proposal Writer, claim Verifier (B3), Critic. Strong model on writer/critic comes from config."""
import asyncio
import json
import re

from agent.handoffs import Critique, ProposalDraft
from agent.llm import chat, prompt
from agent.nodes.common import cfg, step
from rag.verify import verify


def _json(out: str) -> dict:
    return json.loads(re.search(r"\{.*\}", out, re.S).group(0))


async def writer(state):
    j, spec, ev = state["job"], state["job_spec"], state.get("evidence", [])
    ev_txt = "\n".join(f"[{e['evidence_id']}] {e['title']} ({e['type']}): {e['text']}" for e in ev)
    user = (f"<job_post>\n{j['title']}\n{j['description']}\n</job_post>\n"
            f"SCREENING QUESTIONS: {json.dumps(spec['screening_questions'])}\n<evidence>\n{ev_txt}\n</evidence>")
    prev, crit = state.get("proposal_draft"), state.get("critique")
    if prev and crit and crit.get("send_back"):
        user += (f"\n<previous_draft>\n{prev['cover_letter']}\n</previous_draft>\n"
                 f"Fix these issues: {json.dumps(crit['issues'])}")
    try:
        data = _json(await asyncio.to_thread(chat, "writer", prompt("writer"), user, 3000))
        n = len(spec["screening_questions"])
        answers = ([str(a) for a in data.get("screening_answers", [])] + [""] * n)[:n]
        draft = ProposalDraft(job_id=j["job_id"], cover_letter=str(data["cover_letter"]),
                              screening_answers=answers, revision=state.get("revisions", 0))
    except Exception as e:
        return {"status": "needs_attention", "errors": [f"writer failed: {e}"], **step("writer", error=str(e))}
    return {"proposal_draft": draft.model_dump(), **step("writer", words=len(draft.cover_letter.split()))}


async def verifier(state):
    d, ev = state["proposal_draft"], state.get("evidence", [])
    valid = {e["evidence_id"] for e in ev}
    results = [await asyncio.to_thread(verify, d["cover_letter"], ev)]
    answers = []
    for a in d["screening_answers"]:
        if not a.strip():
            answers.append("")
            continue
        ra = await asyncio.to_thread(verify, a, ev)
        results.append(ra)
        answers.append(ra["clean_text"] or "I would be glad to go through this on a call.")
    graded = sum(c["verdict"] != "no_claim" for r in results for c in r["claims"])
    unsup = sum(r["unsupported"] for r in results)
    removed = [c["sentence"] for r in results for c in r["claims"] if c["verdict"] == "unsupported"]
    ids = sorted({i for r in results for c in r["claims"] if c["verdict"] in ("supported", "partial")
                  for i in c["evidence_ids"] if i in valid})
    cv = dict(graded=graded, unsupported_before=unsup, rate_before=round(unsup / graded, 3) if graded else 0.0,
              removed=removed, claims=results[0]["claims"])
    d = dict(d, cover_letter=results[0]["clean_text"], screening_answers=answers, evidence_ids=ids)
    return {"proposal_draft": d, "claim_verification": cv,
            **step("verifier", graded=graded, unsupported_before=unsup)}


async def critic(state):
    j, d, cv, ev = state["job"], state["proposal_draft"], state["claim_verification"], state.get("evidence", [])
    pol, bud = cfg()["policy"], cfg()["budgets"]
    words, rule = len(d["cover_letter"].split()), []
    if words < pol["min_proposal_words"]:
        rule.append(f"too short ({words} words, minimum {pol['min_proposal_words']})")
    if words > pol["max_proposal_words"]:
        rule.append(f"too long ({words} words, maximum {pol['max_proposal_words']})")
    skills = sorted({s for e in ev for s in e.get("skills", [])})
    user = (f"<job_post>\n{j['title']}\n{j['description']}\n</job_post>\n<draft>\n{d['cover_letter']}\n</draft>\n"
            f"SCREENING ANSWERS: {json.dumps(d['screening_answers'])}\n"
            f"REMOVED_UNSUPPORTED_SENTENCES: {json.dumps(cv['removed'])}\nEVIDENCE_SKILLS: {json.dumps(skills)}")
    try:
        data = _json(await asyncio.to_thread(chat, "critic", prompt("critic"), user, 3000))
        llm_ok, issues = bool(data.get("approved")), [str(x) for x in data.get("issues", [])][:4]
    except Exception:
        llm_ok, issues = True, ["critic model unavailable; only rule checks ran"]
    approved = llm_ok and not rule
    rev = state.get("revisions", 0)
    send_back = (not approved) and rev < bud["max_revisions"]
    crit = Critique(approved=approved, issues=rule + issues, revision=rev, send_back=send_back)
    return {"critique": crit.model_dump(), "revisions": rev + 1 if send_back else rev,
            **step("critic", approved=approved, send_back=send_back, issues=len(crit.issues))}