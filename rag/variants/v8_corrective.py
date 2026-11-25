"""V8: corrective retrieval as a LangGraph loop. retrieve -> grade -> (rewrite -> retrieve) once -> done.
If evidence is still weak the requirement is returned as 'no_evidence', so the writer must not claim it."""
import json
import operator
import re
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from agent.llm import chat, prompt

MAX_REWRITES = 1


class S(TypedDict, total=False):
    persona_id: str
    requirement: str
    query: str
    k: int
    hits: list
    relevant: bool
    tries: int
    log: Annotated[list, operator.add]


def _base(pid, q, k):
    from rag.variants.v2_hybrid import retrieve
    return retrieve(pid, q, k)


def retrieve_node(s):
    return {"hits": _base(s["persona_id"], s["query"], s["k"]), "tries": s.get("tries", 0) + 1}


def grade_node(s):
    ev = "\n".join(f"[{h['evidence_id']}] {h['title']}: {h['text']}" for h in s["hits"][:3])
    try:
        out = chat("fit_matcher", prompt("grade_evidence"),
                   f"<requirement>{s['requirement']}</requirement>\n<evidence>\n{ev}\n</evidence>", 300)
        ok = bool(json.loads(re.search(r"\{.*\}", out, re.S).group(0)).get("relevant"))
    except Exception:
        ok = True  # grader unavailable: do not discard evidence
    return {"relevant": ok, "log": [dict(query=s["query"], relevant=ok)]}


def rewrite_node(s):
    try:
        q = chat("fit_matcher", prompt("rewrite_query"), f"<requirement>{s['requirement']}</requirement>", 100).strip()
    except Exception:
        q = s["requirement"]
    return {"query": q or s["requirement"]}


def route(s):
    if s["relevant"] or s["tries"] > MAX_REWRITES:
        return END
    return "rewrite"


def _build():
    g = StateGraph(S)
    g.add_node("retrieve", retrieve_node)
    g.add_node("grade", grade_node)
    g.add_node("rewrite", rewrite_node)
    g.add_edge(START, "retrieve")
    g.add_edge("retrieve", "grade")
    g.add_conditional_edges("grade", route, ["rewrite", END])
    g.add_edge("rewrite", "retrieve")
    return g.compile()


_G = None


def retrieve_one(persona_id: str, requirement: str, k: int = 5) -> dict:
    global _G
    _G = _G or _build()
    s = _G.invoke(dict(persona_id=persona_id, requirement=requirement, query=requirement, k=k))
    if not s["relevant"]:
        return dict(hits=[], no_evidence=True, log=s["log"])
    return dict(hits=s["hits"], no_evidence=False, log=s["log"])


def retrieve(persona_id: str, query: str, k: int = 5, filters=None):
    """Same signature as other variants: decompose, run the loop per requirement, merge.
    Requirements with no evidence contribute nothing (that is the 'refuse to claim' behaviour)."""
    from rag.variants.v1_decompose import decompose
    reqs = decompose(query)
    per = max(3, -(-k // len(reqs)))
    lists = []
    for r in reqs:
        res = retrieve_one(persona_id, r, per)
        lists.append([dict(h, matched_requirement=r) for h in res["hits"]])
    seen, out = set(), []
    for rank in range(per):
        for lst in lists:
            if rank < len(lst) and lst[rank]["evidence_id"] not in seen:
                seen.add(lst[rank]["evidence_id"])
                out.append(lst[rank])
    return out[:k]