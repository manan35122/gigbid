"""Local GigSim stand-in (SYNTHETIC). Run: uvicorn gigsim_local.app:app --port 8081"""
import hashlib
import json
import math
import os
import random
import time
from collections import defaultdict, deque
from pathlib import Path

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

load_dotenv()
HERE = Path(__file__).parent
DATA = HERE / "data"
TOKEN = os.getenv("GIGSIM_API_TOKEN", "dev-token-123")
ERROR_RATE = float(os.getenv("GIGSIM_ERROR_RATE", "0.03"))
RATE_LIMIT = int(os.getenv("GIGSIM_RATE_LIMIT", "30"))  # requests per minute per token
START_CONNECTS = 100


def load(name):
    return json.loads((DATA / f"{name}.json").read_text(encoding="utf-8"))


def policy():
    # re-read on every call so a policy change takes effect without a restart
    return json.loads((HERE / "policy.json").read_text(encoding="utf-8"))


JOBS = {j["job_id"]: j for j in load("jobs_stream")}
HIST = load("jobs_history")
CLIENTS = {c["client_id"]: c for c in load("clients")}
HIDDEN = load("clients_hidden")
S: dict = {}


def reset():
    S.clear()
    S.update(connects=START_CONNECTS, proposals={}, messages=[], idem={}, bids_today=0)


reset()
hits: dict = defaultdict(deque)


def guard(authorization: str = Header(default="")):
    if authorization != f"Bearer {TOKEN}":
        raise HTTPException(401, "invalid token")
    now = time.time()
    q = hits[authorization]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= RATE_LIMIT:
        raise HTTPException(429, "rate limit exceeded", headers={"Retry-After": "10"})
    q.append(now)
    if random.random() < ERROR_RATE:
        raise HTTPException(503, "simulated upstream error")


app = FastAPI(title="GigSim-local (synthetic)")
api = APIRouter(dependencies=[Depends(guard)])


def pub(job):
    return {k: v for k, v in job.items() if k != "category"}  # category is gold-ish; hide it


def cost_of(job):
    return math.ceil(job["connects_cost"] * policy()["connects_multiplier"])


@app.get("/health")
def health():
    return {"ok": True, "jobs": len(JOBS)}


@app.post("/admin/reset")
def admin_reset(authorization: str = Header(default="")):
    if authorization != f"Bearer {TOKEN}":
        raise HTTPException(401, "invalid token")
    reset()
    return {"reset": True}


@api.get("/jobs")
def search_jobs(q: str = "", limit: int = 20, offset: int = 0):
    ql = q.lower()
    out = [j for j in JOBS.values()
           if not ql or ql in (j["title"] + j["description"] + " ".join(j["required_skills"])).lower()]
    return [pub(j) for j in out[offset: offset + limit]]


@api.get("/jobs/history")  # must be declared before /jobs/{job_id}
def job_history(skill: str = "", limit: int = 200):
    sl = skill.lower()
    rows = [dict(title=j["title"], required_skills=j["required_skills"], budget=j["budget"],
                 duration_days=j["duration_days"])
            for j in HIST if not sl or sl in " ".join(j["required_skills"]).lower()]
    return rows[:limit]


@api.get("/jobs/{job_id}")
def get_job(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(404, "job not found")
    return pub(JOBS[job_id])


@api.get("/clients/{client_id}")
def get_client(client_id: str):
    if client_id not in CLIENTS:
        raise HTTPException(404, "client not found")
    return CLIENTS[client_id]


@api.get("/connects")
def connects():
    return {"balance": S["connects"]}


class ProposalIn(BaseModel):
    job_id: str
    cover_letter: str
    screening_answers: list[str] = Field(default_factory=list)
    bid_amount: float = Field(gt=0)
    idempotency_key: str
    dry_run: bool = False


def validate(p: ProposalIn):
    pol = policy()
    words = len(p.cover_letter.split())
    if words > pol["max_proposal_words"] or words < pol["min_proposal_words"]:
        raise HTTPException(422, f"cover letter must be {pol['min_proposal_words']}-"
                                 f"{pol['max_proposal_words']} words (got {words})")
    low = (p.cover_letter + " " + " ".join(p.screening_answers)).lower()
    bad = [b for b in pol["banned_phrases"] if b in low]
    if bad:
        raise HTTPException(422, f"banned phrases: {bad}")


@api.post("/proposals")
def create_proposal(p: ProposalIn):
    if p.job_id not in JOBS:
        raise HTTPException(404, "job not found")
    validate(p)
    job = JOBS[p.job_id]
    preview = dict(job_id=p.job_id, cover_letter=p.cover_letter, bid_amount=p.bid_amount,
                   screening_answers=p.screening_answers, connects_cost=cost_of(job))
    if p.dry_run:
        return {"dry_run": True, "would_send": preview, "connects_cost": preview["connects_cost"],
                "balance_after": S["connects"] - preview["connects_cost"]}
    key = f"create:{p.idempotency_key}"
    if key in S["idem"]:
        return S["idem"][key]
    if any(x["job_id"] == p.job_id for x in S["proposals"].values()):
        raise HTTPException(409, "a proposal for this job already exists")
    pid = f"prop-{len(S['proposals']) + 1:04d}"
    rec = dict(id=pid, status="draft", outcome=None, **preview)
    S["proposals"][pid] = rec
    S["idem"][key] = rec
    return rec


class SubmitIn(BaseModel):
    idempotency_key: str


def simulate_client(rec):
    job = JOBS[rec["job_id"]]
    hid = HIDDEN[job["client_id"]]
    r = random.Random(int(hashlib.md5(rec["id"].encode()).hexdigest(), 16))
    text = rec["cover_letter"].lower()
    skills = job["required_skills"]
    overlap = sum(s.lower() in text for s in skills) / max(len(skills), 1)
    prob = hid["reply_bias"] * (0.4 + 0.6 * overlap)
    generic = text.startswith(("dear sir", "hello sir", "i am writing to apply", "i am the best"))
    if generic and hid["dislikes_generic"]:
        prob *= 0.3
    if len(text.split()) < 40:
        prob *= 0.5
    if r.random() > prob:
        return "ignored"
    y = r.random()
    return "hired" if y < 0.15 else "interview" if y < 0.5 else "replied"


@api.post("/proposals/{pid}/submit")
def submit(pid: str, body: SubmitIn):
    key = f"submit:{body.idempotency_key}"
    if key in S["idem"]:
        return S["idem"][key]
    rec = S["proposals"].get(pid)
    if not rec:
        raise HTTPException(404, "proposal not found")
    if rec["status"] != "draft":
        return rec  # already submitted: never charge twice
    if S["bids_today"] >= policy()["max_bids_per_day"]:
        raise HTTPException(429, "daily bid limit reached")
    cost = cost_of(JOBS[rec["job_id"]])
    if S["connects"] < cost:
        raise HTTPException(402, "not enough Connects")
    S["connects"] -= cost
    S["bids_today"] += 1
    rec["status"] = "submitted"
    rec["connects_spent"] = cost
    rec["outcome"] = simulate_client(rec)
    if rec["outcome"] != "ignored":
        text = {"replied": "Thanks for your proposal, a couple of questions before we continue.",
                "interview": "Your background looks relevant. Can we have a call this week?",
                "hired": "We'd like to hire you. When can you start?"}[rec["outcome"]]
        S["messages"].append(dict(id=f"msg-{len(S['messages']) + 1:04d}", proposal_id=pid,
                                  sender="client", text=text, at=time.time()))
    S["idem"][key] = rec
    return rec


@api.get("/proposals")
def list_proposals():
    return list(S["proposals"].values())


@api.get("/proposals/{pid}")
def get_proposal(pid: str):
    if pid not in S["proposals"]:
        raise HTTPException(404, "proposal not found")
    return S["proposals"][pid]


@api.get("/messages")
def list_messages(proposal_id: str = ""):
    return [m for m in S["messages"] if not proposal_id or m["proposal_id"] == proposal_id]


class MessageIn(BaseModel):
    proposal_id: str
    text: str = Field(min_length=1, max_length=2000)
    idempotency_key: str


@api.post("/messages")
def send_message(m: MessageIn):
    key = f"msg:{m.idempotency_key}"
    if key in S["idem"]:
        return S["idem"][key]
    if m.proposal_id not in S["proposals"]:
        raise HTTPException(404, "proposal not found")
    low = m.text.lower()
    bad = [b for b in policy()["banned_phrases"] if b in low]
    if bad:
        raise HTTPException(422, f"banned phrases: {bad}")
    rec = dict(id=f"msg-{len(S['messages']) + 1:04d}", proposal_id=m.proposal_id,
               sender="freelancer", text=m.text, at=time.time())
    S["messages"].append(rec)
    S["idem"][key] = rec
    return rec


app.include_router(api)