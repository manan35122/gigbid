"""API: run a job through the graph (SSE progress), list jobs, and resume approvals."""
import json
from contextlib import asynccontextmanager
from typing import Literal
import asyncio
import logging

from agent.memory.promotion_rules import record_edit, record_outcome
from agent.memory.store import category_of, open_store
from agent.nodes.common import cfg as load_cfg
from agent.llm import chat, prompt
from agent.nodes.compliance import compliance
from rag.verify import verify
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from langgraph.types import Command
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from agent.checkpoint import saver
from agent.graphs.bid_graph import build
from mcp_servers.marketplace.adapters.gigsim import GigSimAdapter, MarketplaceUnavailable

adapter = GigSimAdapter()  # read-only job listing for the inbox; agents still go through MCP


@asynccontextmanager
async def lifespan(app):
    async with saver() as cp, open_store() as store:
        app.state.store = store
        app.state.graph = build(cp, store)
        yield


app = FastAPI(title="GigBid API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://localhost:3000"],
                   allow_methods=["*"], allow_headers=["*"])


def cfg(persona, job_id):
    return {"configurable": {"thread_id": f"{persona}:{job_id}"}}


async def snapshot(graph, c):
    st = await graph.aget_state(c)
    v, pending = st.values, None
    for t in st.tasks:
        for i in t.interrupts:
            pending = i.value
    return dict(status=v.get("status"), job=v.get("job"), spec=v.get("job_spec"), decision=v.get("decision"), fit=v.get("fit_report"),
                risk=v.get("risk_report"), price=v.get("price_quote"), pending_approval=pending,
                submission=v.get("submission"), errors=v.get("errors", []), trace=v.get("trace", []))


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/jobs")
async def jobs(persona: str = "ai_engineer", limit: int = 20):
    try:
        rows = await adapter.search_jobs("", limit, 0)
    except MarketplaceUnavailable as e:
        raise HTTPException(503, f"marketplace unavailable: {e}")
    out = []
    for j in rows:
        st = await app.state.graph.aget_state(cfg(persona, j["job_id"]))
        out.append(dict(job_id=j["job_id"], title=j["title"], skills=j["required_skills"],
                        budget=j["budget"], connects_cost=j["connects_cost"],
                        status=st.values.get("status") if st.values else "new",
                        action=(st.values.get("decision") or {}).get("action") if st.values else None))
    return out


@app.get("/api/runs/{persona}/{job_id}")
async def run_state(persona: str, job_id: str):
    return await snapshot(app.state.graph, cfg(persona, job_id))


@app.get("/api/runs/{persona}/{job_id}/stream")
async def stream(persona: str, job_id: str):
    graph, c = app.state.graph, cfg(persona, job_id)

    async def gen():
        if not (await graph.aget_state(c)).values:
            try:
                async for chunk in graph.astream({"job_id": job_id, "persona_id": persona}, c,
                                                 stream_mode="updates"):
                    for node in chunk:
                        if node != "__interrupt__":
                            yield {"event": "node", "data": json.dumps({"node": node})}
            except Exception as e:
                yield {"event": "error", "data": json.dumps({"error": str(e)})}
        yield {"event": "done", "data": json.dumps(await snapshot(graph, c), default=str)}

    return EventSourceResponse(gen())


class Decision(BaseModel):
    action: Literal["approve", "edit", "reject"]
    reason: str | None = None
    edited_text: str | None = None


@app.post("/api/runs/{persona}/{job_id}/decision")
async def decision(persona: str, job_id: str, body: Decision):
    graph, c = app.state.graph, cfg(persona, job_id)
    st = await graph.aget_state(c)
    if not any(t.interrupts for t in st.tasks):
        raise HTTPException(409, "no pending approval for this job")
    before, job = st.values["proposal_draft"]["cover_letter"], st.values["job"]
    await graph.ainvoke(Command(resume=body.model_dump()), c)
    snap = await snapshot(graph, c)
    try:  # memory must never break an approval
        if body.action == "edit" and body.edited_text:
            await record_edit(app.state.store, persona, job_id, before, body.edited_text)
        sub = snap.get("submission")
        if sub:
            await record_outcome(app.state.store, persona, category_of(job["required_skills"]),
                                 job_id, sub.get("outcome") or "ignored", sub.get("cover_letter", ""))
    except Exception:
        logging.exception("memory update failed")
    return snap


@app.get("/api/memory/{persona}")
async def memory(persona: str):
    s = app.state.store

    async def ns(name):
        return [dict(key=i.key, **i.value) for i in await s.asearch((persona, name), limit=100)]
    return dict(style=await ns("style"), style_candidates=await ns("style_candidates"),
                outcome=await ns("outcome"), outcome_candidates=await ns("outcome_candidates"),
                rules=load_cfg()["memory"])


@app.delete("/api/memory/{persona}/{kind}/{key}")
async def forget(persona: str, kind: Literal["style", "outcome"], key: str):
    s = app.state.store
    await s.adelete((persona, kind), key)
    await s.adelete((persona, kind + "_candidates"), key)   # reset the counter so it must be re-earned
    return {"deleted": key}

COLUMNS = ["drafted", "submitted", "viewed", "replied", "interview", "hired", "lost"]
OUTCOME_COL = {"replied": "replied", "interview": "interview", "hired": "hired", "ignored": "lost"}


@app.get("/api/pipeline")
async def pipeline(persona: str = "ai_engineer"):
    graph = app.state.graph
    cols = {k: [] for k in COLUMNS}
    try:
        jobs = await adapter.search_jobs("", 200, 0)
        props = await adapter.list_proposals()
    except MarketplaceUnavailable as e:
        raise HTTPException(503, f"marketplace unavailable: {e}")
    titles = {j["job_id"]: j["title"] for j in jobs}
    for j in jobs:
        st = await graph.aget_state(cfg(persona, j["job_id"]))
        if st.values and st.values.get("status") == "needs_approval":
            cols["drafted"].append(dict(job_id=j["job_id"], title=j["title"],
                                        bid=(st.values.get("price_quote") or {}).get("bid_amount")))
    for p in props:
        st = await graph.aget_state(cfg(persona, p["job_id"]))
        if not (st.values and st.values.get("submission")):
            continue  # proposals of other personas / not made by GigBid
        col = OUTCOME_COL.get(p.get("outcome"), "submitted")
        cols[col].append(dict(job_id=p["job_id"], title=titles.get(p["job_id"], p["job_id"]),
                              bid=p["bid_amount"], connects=p.get("connects_spent"), proposal_id=p["id"]))
    return dict(columns=cols, order=COLUMNS)

class Regen(BaseModel):
    sentence: str
    instruction: str | None = None


@app.post("/api/runs/{persona}/{job_id}/regenerate")
async def regenerate(persona: str, job_id: str, body: Regen):
    graph, c = app.state.graph, cfg(persona, job_id)
    st = await graph.aget_state(c)
    if not any(t.interrupts for t in st.tasks):
        raise HTTPException(409, "no pending approval for this job")
    v = st.values
    d = v["proposal_draft"]
    if body.sentence not in d["cover_letter"]:
        raise HTTPException(422, "that sentence is not in the current draft")
    ev = v.get("evidence", [])
    ev_txt = "\n".join(f"[{e['evidence_id']}] {e['title']}: {e['text']}" for e in ev)
    j = v["job"]
    user = (f"<job_post>\n{j['title']}\n{j['description']}\n</job_post>\n<evidence>\n{ev_txt}\n</evidence>\n"
            f"<full_letter>\n{d['cover_letter']}\n</full_letter>\n"
            f"<sentence_to_rewrite>\n{body.sentence}\n</sentence_to_rewrite>\n"
            f"INSTRUCTION: {body.instruction or 'Rewrite it to be more specific to this job.'}")
    new = (await asyncio.to_thread(chat, "writer", prompt("rewrite_sentence"), user, 1500)).strip().strip('"')
    if not new:
        raise HTTPException(502, "the model returned nothing")
    letter = d["cover_letter"].replace(body.sentence, new, 1)
    res = await asyncio.to_thread(verify, letter, ev)          # claims are re-verified
    comp = await compliance({"proposal_draft": dict(d, cover_letter=res["clean_text"])})  # and re-checked
    cv = dict(v["claim_verification"], claims=res["claims"],
              removed=v["claim_verification"]["removed"] +
              [x["sentence"] for x in res["claims"] if x["verdict"] == "unsupported"])
    await graph.aupdate_state(c, {"proposal_draft": comp["proposal_draft"],
                                  "compliance_verdict": comp["compliance_verdict"],
                                  "claim_verification": cv, "status": comp["status"]},
                              as_node="compliance")
    await graph.ainvoke(None, c)   # runs preview, then pauses at approval again
    return await snapshot(graph, c)