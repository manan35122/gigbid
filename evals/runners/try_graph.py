"""Run the graph on N stream jobs, compare scam flags and decisions to gold. python evals/runners/try_graph.py ai_engineer 40"""
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agent.graphs.bid_graph import build  # noqa: E402


async def main(persona, n):
    gold = {g["job_id"]: g for g in json.loads((ROOT / "gigsim_local/data/gold.json").read_text())}
    jobs = [j["job_id"] for j in json.loads((ROOT / "gigsim_local/data/jobs_stream.json").read_text())][:n]
    graph, tp = build(), []
    rows = []
    for jid in jobs:
        s = await graph.ainvoke({"job_id": jid, "persona_id": persona})
        if s.get("status") == "needs_attention":
            print(jid, "NEEDS ATTENTION", s["errors"]); continue
        hard = {"prompt_injection", "off_platform_contact", "unpaid_work"} & set(s["risk_report"]["flags"])
        rows.append((jid, gold[jid]["is_scam"], bool(hard), s["decision"]["action"], s["fit_report"]["score"]))
        print(*rows[-1])
    tp = sum(1 for r in rows if r[1] and r[2]); fp = sum(1 for r in rows if not r[1] and r[2])
    fn = sum(1 for r in rows if r[1] and not r[2])
    print(f"scam precision={tp/max(tp+fp,1):.2f} recall={tp/max(tp+fn,1):.2f} (n={len(rows)}, tp={tp} fp={fp} fn={fn})")


asyncio.run(main(sys.argv[1], int(sys.argv[2])))