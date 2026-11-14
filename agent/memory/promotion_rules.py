"""Explicit promotion rules (R7). Nothing reaches long-term memory except through these functions."""
import re
import time

from agent.nodes.common import cfg

WORDS = ["passionate", "excited", "thrilled", "hardworking", "comfortable", "eager"]


def _sents(t: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", t.strip()) if s]


def detect_patterns(before: str, after: str) -> dict[str, str]:
    """Compare a draft with the user's edited version -> {pattern_key: rule_text}."""
    out = {}
    b, a = _sents(before), _sents(after)
    if b and b[0] not in a and len(a) < len(b):
        out["drop_opening"] = ("Do not open by restating the job. Start with the strongest relevant "
                               "result from the evidence.")
    for w in WORDS:
        if re.search(rf"\b{w}\b", before, re.I) and not re.search(rf"\b{w}\b", after, re.I):
            out[f"avoid_word:{w}"] = f'Never use the word "{w}".'
    bw, aw = len(before.split()), len(after.split())
    if bw and aw <= 0.8 * bw:
        out["shorter"] = "Keep the cover letter concise. The freelancer usually shortens drafts."
    return out


async def record_edit(store, persona: str, job_id: str, before: str, after: str) -> list[str]:
    """RULE: a pattern becomes a style rule only after it appears in `style_min_jobs` DIFFERENT jobs."""
    need = cfg()["memory"]["style_min_jobs"]
    promoted = []
    for key, rule in detect_patterns(before, after).items():
        cur = await store.aget((persona, "style_candidates"), key)
        v = cur.value if cur else {"rule": rule, "jobs": []}
        if job_id not in v["jobs"]:          # the same job counted twice never promotes anything
            v["jobs"].append(job_id)
        await store.aput((persona, "style_candidates"), key, v)
        if len(v["jobs"]) >= need and not await store.aget((persona, "style"), key):
            await store.aput((persona, "style"), key,
                             {"rule": rule, "evidence_jobs": v["jobs"], "promoted_at": time.time()})
            promoted.append(key)
    return promoted


async def record_outcome(store, persona: str, category: str, job_id: str, outcome: str, letter: str) -> bool:
    """RULE: a category's stats are promoted once it has `outcome_min_n` outcomes. Each job counts once."""
    need = cfg()["memory"]["outcome_min_n"]
    cur = await store.aget((persona, "outcome_candidates"), category)
    v = cur.value if cur else {"jobs": {}}
    if job_id in v["jobs"]:
        return False
    v["jobs"][job_id] = {"outcome": outcome, "has_number": bool(re.search(r"\d", letter))}
    await store.aput((persona, "outcome_candidates"), category, v)
    rows = list(v["jobs"].values())
    n = len(rows)
    if n < need:
        return False
    replies = sum(r["outcome"] != "ignored" for r in rows)
    hires = sum(r["outcome"] == "hired" for r in rows)
    summary = f"{category}: {n} proposals so far, {replies / n:.0%} got a reply, {hires / n:.0%} led to a hire."
    num = [r for r in rows if r["has_number"]]
    non = [r for r in rows if not r["has_number"]]
    if len(num) >= 2 and len(non) >= 2:
        rate = lambda g: sum(r["outcome"] != "ignored" for r in g) / len(g)  # noqa: E731
        summary += (f" Letters citing a concrete number: {rate(num):.0%} replied (n={len(num)}); "
                    f"without: {rate(non):.0%} (n={len(non)}).")
    await store.aput((persona, "outcome"), category,
                     dict(summary=summary, n=n, reply_rate=replies / n, hire_rate=hires / n,
                          promoted_at=time.time()))
    return True