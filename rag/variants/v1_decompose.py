"""V1: requirement decomposition. One retrieval per extracted requirement, merged round-robin."""
import json
import re

from agent.llm import chat, prompt


def decompose(job_text: str) -> list[str]:
    try:
        out = chat("analyst", prompt("decompose_requirements"), f"<job_post>\n{job_text}\n</job_post>")
        m = re.search(r"\[.*\]", out, re.S)
        reqs = [str(x) for x in json.loads(m.group(0))] if m else []
        return reqs[:6] or [job_text]
    except Exception:
        return [job_text]  # degraded: fall back to whole-post retrieval


def retrieve_with(base, persona_id, query, k=5, filters=None):
    reqs = decompose(query)
    per = max(3, -(-k // len(reqs)))
    lists = [base(persona_id, r, per, filters) for r in reqs]
    seen, out = set(), []
    for rank in range(per):
        for lst in lists:
            if rank < len(lst) and lst[rank]["evidence_id"] not in seen:
                seen.add(lst[rank]["evidence_id"])
                out.append(dict(lst[rank], matched_requirement=reqs[lists.index(lst)]))
    return out[:k]


def retrieve_v0(persona_id, query, k=5, filters=None):
    from rag.variants.v0_naive import retrieve
    return retrieve_with(retrieve, persona_id, query, k, filters)


def retrieve_v2(persona_id, query, k=5, filters=None):
    from rag.variants.v2_hybrid import retrieve
    return retrieve_with(retrieve, persona_id, query, k, filters)