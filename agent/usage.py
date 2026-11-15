"""Aggregate agent/llm.py's call log into per-node, per-job and per-proposal latency, tokens and cost."""
import json
from collections import defaultdict

from agent.llm import CALLS_LOG


def pct(xs, p):
    if not xs:
        return None
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, round(p / 100 * (len(xs) - 1)))], 3)


def _stats(rows):
    if not rows:
        return None
    priced = [r["cost"] for r in rows if r["cost"] is not None]
    return dict(runs=len(rows),
                wall_s_p50=pct([r["wall_s"] for r in rows], 50), wall_s_p95=pct([r["wall_s"] for r in rows], 95),
                tokens_mean=round(sum(r["tokens"] for r in rows) / len(rows)),
                cost_usd_mean=round(sum(priced) / len(priced), 6) if priced else None,
                cost_priced_runs=len(priced))


def summarize() -> dict:
    calls = [json.loads(line) for line in CALLS_LOG.read_text(encoding="utf-8").splitlines()] \
        if CALLS_LOG.exists() else []
    runs = defaultdict(list)
    for c in calls:
        if c["run"] != "unscoped":
            runs[c["run"]].append(c)
    real = {r: cs for r, cs in runs.items() if not any(c["cached"] for c in cs)}  # cached runs are not real timings
    nodes = defaultdict(lambda: dict(calls=0, tokens=0, cost=0.0, lat=[], unpriced=0))
    rows = []
    for r, cs in real.items():
        for c in cs:
            n = nodes[c["node"]]
            n["calls"] += 1
            n["tokens"] += c["prompt_tokens"] + c["completion_tokens"]
            n["lat"].append(c["latency_s"])
            if c["cost_usd"] is None:
                n["unpriced"] += 1
            else:
                n["cost"] += c["cost_usd"]
        priced = all(c["cost_usd"] is not None for c in cs)
        rows.append(dict(run=r, tokens=sum(c["prompt_tokens"] + c["completion_tokens"] for c in cs),
                         cost=round(sum(c["cost_usd"] or 0 for c in cs), 6) if priced else None,
                         wall_s=max(c["ts"] + c["latency_s"] for c in cs) - min(c["ts"] for c in cs),
                         proposal=any(c["node"] == "writer" for c in cs)))
    return dict(
        runs_measured=len(real), runs_excluded_because_cached=len(runs) - len(real),
        per_node={k: dict(calls=v["calls"], tokens=v["tokens"], cost_usd=round(v["cost"], 6),
                          unpriced_calls=v["unpriced"], latency_p50=pct(v["lat"], 50), latency_p95=pct(v["lat"], 95))
                  for k, v in sorted(nodes.items())},
        per_job_analysed=_stats(rows),
        per_proposal=_stats([r for r in rows if r["proposal"]]),
        note="per_proposal = runs that reached the writer, so it includes the analysis cost of that job. "
             "Wall time is the span of LLM calls, excluding time the human spends approving.")