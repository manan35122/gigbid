"""Thin Groq client (OpenAI-compatible). Model per node comes from agent/config.yaml, never from code."""
import hashlib
import json
import os
import time
from pathlib import Path

import httpx
import yaml
from dotenv import load_dotenv

load_dotenv()
ROOT = Path(__file__).resolve().parents[1]
CACHE_FILE = ROOT / "data" / "processed" / "llm_cache.json"
_cache: dict | None = None


def _cfg() -> dict:
    return yaml.safe_load((ROOT / "agent" / "config.yaml").read_text(encoding="utf-8"))


def model_for(node: str) -> str:
    m = _cfg()["models"]
    return m["profiles"][m["profile"]]["tiers"][m["nodes"][node]]


def prompt(name: str) -> str:
    return (ROOT / "agent" / "prompts" / f"{name}.md").read_text(encoding="utf-8")


def chat(node: str, system: str, user: str, max_tokens: int = 1500) -> str:
    global _cache
    if _cache is None:
        _cache = json.loads(CACHE_FILE.read_text(encoding="utf-8")) if CACHE_FILE.exists() else {}
    model = model_for(node)
    key = hashlib.sha256(json.dumps([model, system, user]).encode()).hexdigest()
    if key in _cache:
        return _cache[key]
    body = dict(model=model, temperature=0, max_tokens=max_tokens,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
    if model.startswith("openai/gpt-oss"):
        body["reasoning_effort"] = "low"
    for attempt in range(6):
        r = httpx.post("https://api.groq.com/openai/v1/chat/completions", json=body, timeout=60,
                       headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"})
        if r.status_code in (429, 500, 502, 503):
            time.sleep(min(2 ** attempt, 20))
            continue
        r.raise_for_status()
        out = r.json()["choices"][0]["message"]["content"] or ""
        _cache[key] = out
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps(_cache), encoding="utf-8")
        return out
    raise RuntimeError("LLM unavailable after retries")