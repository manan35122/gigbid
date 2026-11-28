# GigBid: a multi-agent freelancer copilot

GigBid scouts freelance jobs, assesses fit and risk, drafts evidence-backed proposals, and handles client replies. **Nothing is sent to a client until a human approves it in the web UI.**

Built for the AI-4016 R&D assignment with LangGraph, MCP, advanced RAG, FastAPI and React.

> Status: working end to end against a **simulated** marketplace (GigSim). The live Upwork adapter is a stub. See [Limitations](#limitations-and-not-built).

## What it does

1. **Scout** pulls new jobs and drops duplicates (reposts).
2. **Analysis (parallel):** Job Analyst structures the post, Risk Assessor flags scams / free-work / off-platform / injected instructions, Fit Matcher maps each requirement to portfolio evidence.
3. **Decide:** skip, watch or bid, from thresholds in `agent/config.yaml`.
4. **Draft:** Pricing Strategist sets a price from real market data; Proposal Writer drafts from retrieved evidence only.
5. **Check:** Claim Verifier deletes unsupported sentences; Critic reviews (max 2 revisions); Compliance Guard enforces policy.
6. **Approve:** a dry-run preview, then a LangGraph `interrupt()` waits for the user (approve / edit / reject).
7. **Submit exactly once** through idempotency keys.
8. **Conversation graph** classifies client replies, drafts a response (offering free slots for interviews) and again waits for approval.
9. **Memory** learns from edits and outcomes only through explicit promotion rules.

## Architecture

| Layer | Details |
|---|---|
| Web UI | React + TypeScript (Vite), `apps/web`. Inbox, Job detail / Proposal studio, Pipeline, Messages, Settings, Analytics, live progress over SSE |
| API | FastAPI, `apps/api/main.py` |
| Graphs | Hand-written LangGraph StateGraphs: `agent/graphs/bid_graph.py`, `conversation_graph.py` |
| MCP servers | Marketplace (8101), Portfolio (8102), Workspace (8103). Per-agent tool allowlists |
| RAG | `rag/`: variants V0, V1, V2, V3, V8 and claim verification (`rag/verify.py`) |
| Marketplace port | `agent/marketplace_port.py`; adapter chosen by `marketplace.mode` in config |
| Storage | Postgres (checkpoints + memory/settings store), Redis (worker queue) |
| Worker | Arq on Redis, `worker/main.py`. Never submits |
| Simulator | `gigsim_local/`: jobs, clients, Connects, proposals, messages, heuristic client |

Models (Groq, open-weight): `openai/gpt-oss-20b` (cheap nodes), `openai/gpt-oss-120b` (Writer, Critic, Client Liaison), `qwen/qwen3.8-27b` (alternate and fallback). Embeddings: `BAAI/bge-small-en-v1.5` via fastembed, run locally.

## Repository layout

```
agent/            graphs, nodes, prompts, memory, llm client, config.yaml
rag/              retrieval variants, retriever factory, claim verification
mcp_servers/      marketplace (with auth), portfolio, workspace
gigsim_local/     simulator, data generator, Kaggle ingest
worker/           Arq worker
apps/api/         FastAPI app
apps/web/         React UI
evals/            eval runners and committed result files
tests/            unit, integration, contract (MCP schema snapshot)
```

## Prerequisites

- Windows / PowerShell (commands below), Python 3.13, Node.js
- Docker Desktop (for Postgres and Redis)
- A Groq API key

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
cd apps\web ; npm install ; cd ..\..
```

Create `.env` in the project root (never commit it):

```
GROQ_API_KEY=your_key_here
# plus the GigSim token and MCP auth values from your local setup
```

A blank `GROQ_API_KEY` makes the verifier fail, so check it first.

Create the containers once, then start them on later runs:

```powershell
docker start gigbid-pg gigbid-redis
```

## Run the demo

Use one terminal per service. In each Python terminal, activate the venv first.

```powershell
# 1. Docker services
docker start gigbid-pg gigbid-redis

# 2. Simulator
uvicorn gigsim_local.app:app --port 8081

# 3-5. MCP servers
python -m mcp_servers.marketplace.server
python -m mcp_servers.portfolio.server
python -m mcp_servers.workspace.server

# 6. API
python -m apps.api.run

# 7. Web UI (http://localhost:5173)
cd apps\web
npm run dev
```

The scheduled-scouting worker is optional. Leave it off unless demonstrating it, because it shares your Groq quota.

## Reset to a clean state

Stop the API and worker first.

```powershell
docker exec gigbid-pg psql -U gigbid -d gigbid -c "TRUNCATE checkpoints, checkpoint_writes, checkpoint_blobs;"
docker exec gigbid-redis redis-cli FLUSHALL
```

Then restart GigSim (this resets jobs, proposals, messages and the Connects balance) and restart the API. The memory/settings store is not cleared by these commands.

## Configuration

Everything tunable lives in `agent/config.yaml`: model routing and fallback tiers, budgets (steps, revisions, tokens per job), the fit threshold (`minimum_fit_score`), marketplace policy (word limits, banned phrases, Connects multiplier, injection defence switch), memory promotion thresholds, pricing and worker settings. GigSim re-reads these rules on every call.

## Tests

```powershell
pytest tests/unit tests/contract
pytest tests/integration   # needs the services above running
```

## Measured results (from this project's own runs)

| Area | Result | Caveat |
|---|---|---|
| Retrieval Recall@5 (144 template queries) | V0 0.614, V2 0.647, V3 0.585, **V1 0.939** | On 4-requirement jobs V0 0.382 vs V1 0.931. Template-generated queries |
| Unsupported claims | 12.5% (9/72) before verification, 0/30 after | Same verifier graded both; no human hand-check |
| Bid decision F1 (60 jobs) | 0.864 at threshold 0.60, **0.95 at 0.70** | Threshold tuned on the same set; scam detection P/R 1.0 is circular |
| Cost and latency (10 runs) | p50 15.9 s, p95 47.4 s, 6,380 tokens, $0.0012 per job at list price | Free tier cost is $0; list prices need checking |
| Prompt injection (n=3 per cell) | Paraphrased attacks: 0/3 skipped without defence, 3/3 with | Tiny sample; I wrote the attacks |
| Exactly-once submit | Balance 90 before and after replay | |

## Safety

- Human approval is mandatory. Autonomy settings only control auto-skipping.
- Job posts and client messages are treated as untrusted data.
- Injection defence: detection (regex + LLM), sanitising, output guard.
- Compliance Guard blocks contact details, off-platform moves and guarantees.
- Marketplace MCP has bearer auth, rate limiting, idempotency keys, `dry_run` and an append-only audit log.
- Failed jobs become dead letters with a reason and a Retry button.

## Limitations and not built

- Live Upwork adapter (stub only), GitHub MCP, incremental re-indexing
- RAG variants V4, V5, V6, V7, V9; V8 has a probe only, not a full eval
- R&D questions A (tool granularity) and C (single agent vs supervisor) were not run
- No signature extension, judge calibration, Playwright tests, CI, tracing, PII masking, multi-user auth or deployment
- Data is synthetic except Kaggle pricing statistics; client outcomes come from a heuristic simulator
- The rate limiter is in-memory; Pipeline "viewed" is always empty (GigSim has no view events)
- Analytics and the Settings preferences card were not fully verified in the UI

## Data

- Synthetic jobs, clients, personas and proposals are tagged `data_origin: synthetic`.
- Real data: Kaggle Upwork 2024 jobs (`upwork-jobs.csv`), fixed-price rows only, used for pricing statistics. See `DATA_CARD.md` (license text still to be added).
- The `.env` file and derived Kaggle file are excluded from git.
