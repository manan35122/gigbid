"""python evals/runners/try_draft.py ai_engineer 12  -> run N stream jobs, show what the graph produced."""
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agent.graphs.bid_graph import build  # noqa: E402


async def main(persona, n):
    jobs = [j["job_id"] for j in json.loads((ROOT / "gigsim_local/data/jobs_stream.json").read_text())][:n]
    graph, shown = build(), False
    for jid in jobs:
        s = await graph.ainvoke({"job_id": jid, "persona_id": persona})
        line = [jid, s.get("status"), s.get("decision", {}).get("action")]
        if "price_quote" in s:
            q, cv = s["price_quote"], s["claim_verification"]
            line += [f"bid={q['bid_amount']}", f"revisions={s.get('revisions', 0)}",
                     f"unsupported_removed={cv['unsupported_before']}/{cv['graded']}",
                     f"critic_ok={s['critique']['approved']}"]
        print(*line)
        if s.get("status") == "ready_for_approval" and not shown:
            shown = True
            print("--- price:", s["price_quote"]["rationale"])
            print("--- DRAFT:\n", s["proposal_draft"]["cover_letter"])
            print("--- evidence:", s["proposal_draft"]["evidence_ids"])
            print("--- removed claims:", s["claim_verification"]["removed"])
            print("--- critique:", s["critique"]["issues"])
            print("--- compliance:", s["compliance_verdict"]["violations"])


asyncio.run(main(sys.argv[1], int(sys.argv[2])))