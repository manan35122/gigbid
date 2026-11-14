"""API: run a job through the graph (SSE progress), list jobs, and resume approvals."""
import json
from contextlib import asynccontextmanager
from typing import Literal

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
    async with saver() as cp:
        app.state.graph = build(cp)
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
    await graph.ainvoke(Command(resume=body.model_dump()), c)
    return await snapshot(graph, c)