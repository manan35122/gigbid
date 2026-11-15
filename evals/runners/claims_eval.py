"""python evals/runners/claims_eval.py ai_engineer 30 -> evals/results/claims_<persona>.json"""
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agent.checkpoint import saver  # noqa: E402
from agent.graphs.bid_graph import build  # noqa: E402
from agent.llm import run_id  # noqa: E402
from rag.verify import verify  # noqa: E402


async def main(persona, n):
    jobs = [j["job_id"] for j in json.loads((ROOT / "gigsim_local/data/jobs_stream.json").read_text())][:n]
    stamp = int(time.time())
    b_unsup = b_graded = a_unsup = a_graded = drafts = proposals = 0
    per, samples = [], []
    async with saver() as cp:
        graph = build(cp)
        for jid in jobs:
            run_id.set(f"claims:{persona}:{jid}:{stamp}")
            s = await graph.ainvoke({"job_id": jid, "persona_id": persona},
                                    {"configurable": {"thread_id": f"claims:{stamp}:{persona}:{jid}"}})
            ver = [t for t in s.get("trace", []) if t["node"] == "verifier"]
            if not ver or "proposal_draft" not in s:
                continue
            proposals += 1
            ju, jg = sum(t["unsupported_before"] for t in ver), sum(t["graded"] for t in ver)
            drafts += len(ver)
            b_unsup += ju
            b_graded += jg
            final = s["proposal_draft"]["cover_letter"]
            r = verify(final, s.get("evidence", []))
            au, ag = r["unsupported"], sum(c["verdict"] != "no_claim" for c in r["claims"])
            a_unsup += au
            a_graded += ag
            per.append(dict(job=jid, passes=len(ver), before=f"{ju}/{jg}", after=f"{au}/{ag}"))
            samples += [dict(job=jid, sentence=c["sentence"], verdict=c["verdict"]) for c in r["claims"]]
            print(jid, per[-1])
    out = dict(persona=persona, proposals=proposals, writer_drafts=drafts,
               before=dict(unsupported=b_unsup, graded=b_graded,
                           rate=round(b_unsup / b_graded, 3) if b_graded else None,
                           unsupported_per_proposal=round(b_unsup / proposals, 2) if proposals else None,
                           unsupported_per_draft=round(b_unsup / drafts, 2) if drafts else None),
               after=dict(unsupported=a_unsup, graded=a_graded,
                          rate=round(a_unsup / a_graded, 3) if a_graded else None,
                          unsupported_per_proposal=round(a_unsup / proposals, 2) if proposals else None),
               note="before = all writer drafts incl. critic revisions; after = re-verification of the final "
                    "cover letter by the same verifier model (not independent). Cover letter only.",
               per_job=per, sentences_for_hand_check=samples[:40])
    (ROOT / "evals/results" / f"claims_{persona}.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: out[k] for k in ("proposals", "writer_drafts", "before", "after")}, indent=1))


asyncio.run(main(sys.argv[1], int(sys.argv[2])))