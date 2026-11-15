"""Thin Groq client (OpenAI-compatible) with usage tracking. Model per node comes from agent/config.yaml."""
import contextvars
import hashlib
import json
import os
import threading
import time
from pathlib import Path

import httpx
import yaml
from dotenv import load_dotenv

load_dotenv()
ROOT = Path(__file__).resolve().parents[1]
CACHE_FILE = ROOT / "data" / "processed" / "llm_cache.json"
CALLS_LOG = ROOT / "data" / "processed" / "llm_calls.jsonl"
_cache: dict | None = None
_lock = threading.Lock()
_totals: dict[str, int] = {}

# which job/conversation the current LLM calls belong to (propagates into asyncio tasks and to_thread)
run_id: contextvars.ContextVar[str] = contextvars.ContextVar("run_id", default="unscoped")


def _cfg() -> dict:
    return yaml.safe_load((ROOT / "agent" / "config.yaml").read_text(encoding="utf-8"))


def model_for(node: str) -> str:
    m = _cfg()["models"]
    return m["profiles"][m["profile"]]["tiers"][m["nodes"][node]]


def prompt(name: str) -> str:
    return (ROOT / "agent" / "prompts" / f"{name}.md").read_text(encoding="utf-8")


def run_tokens(rid: str | None = None) -> int:
    """Tokens used so far by this run (0 when unscoped, so the budget never fires by accident)."""
    rid = rid or run_id.get()
    return 0 if rid == "unscoped" else _totals.get(rid, 0)


def _cost(model: str, pt: int, ct: int) -> float | None:
    p = (_cfg().get("pricing") or {}).get(model) or {}
    if p.get("in") is None or p.get("out") is None:
        return None  # unknown price: reported as unpriced, never guessed
    return round((pt * p["in"] + ct * p["out"]) / 1_000_000, 6)


def _log(node, model, pt, ct, latency, cached):
    rid = run_id.get()
    entry = dict(ts=time.time() - latency, run=rid, node=node, model=model, prompt_tokens=pt,
                 completion_tokens=ct, latency_s=round(latency, 3), cached=cached,
                 cost_usd=0.0 if cached else _cost(model, pt, ct))
    with _lock:
        _totals[rid] = _totals.get(rid, 0) + pt + ct
        CALLS_LOG.parent.mkdir(parents=True, exist_ok=True)
        with CALLS_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")


def chat(node: str, system: str, user: str, max_tokens: int = 1500) -> str:
    global _cache
    if _cache is None:
        _cache = json.loads(CACHE_FILE.read_text(encoding="utf-8")) if CACHE_FILE.exists() else {}
    model = model_for(node)
    key = hashlib.sha256(json.dumps([model, system, user]).encode()).hexdigest()
    if os.getenv("LLM_CACHE", "1") != "0" and key in _cache:  # LLM_CACHE=0 forces real calls (for measuring)
        _log(node, model, 0, 0, 0.0, True)
        return _cache[key]
    body = dict(model=model, temperature=0, max_tokens=max_tokens,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
    if model.startswith("openai/gpt-oss"):
        body["reasoning_effort"] = "low"
    t0 = time.time()
    for attempt in range(6):
        r = httpx.post("https://api.groq.com/openai/v1/chat/completions", json=body, timeout=60,
                       headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"})
        if r.status_code in (429, 500, 502, 503):
            time.sleep(min(2 ** attempt, 20))
            continue
        r.raise_for_status()
        data = r.json()
        out = data["choices"][0]["message"]["content"] or ""
        u = data.get("usage") or {}
        _log(node, model, u.get("prompt_tokens", 0), u.get("completion_tokens", 0), time.time() - t0, False)
        with _lock:
            _cache[key] = out
            CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            CACHE_FILE.write_text(json.dumps(_cache), encoding="utf-8")
        return out
    raise RuntimeError("LLM unavailable after retries")