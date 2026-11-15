"""python evals/runners/measure.py ai_engineer 10   (run with LLM_CACHE=0 for real timings)"""
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agent.checkpoint import saver  # noqa: E402  (sets the Windows event-loop policy)
from agent.graphs.bid_graph import build  # noqa: E402
from agent.llm import run_id  # noqa: E402
from agent.usage import summarize  # noqa: E402


async def main(persona, n):
    jobs = [j["job_id"] for j in json.loads((ROOT / "gigsim_local/data/jobs_stream.json").read_text())][:n]
    stamp = int(time.time())
    async with saver() as cp:
        graph = build(cp)
        for jid in jobs:
            run_id.set(f"measure:{persona}:{jid}:{stamp}")
            s = await graph.ainvoke({"job_id": jid, "persona_id": persona},
                                    {"configurable": {"thread_id": f"measure:{stamp}:{persona}:{jid}"}})
            print(jid, s.get("status"))
    out = summarize()
    (ROOT / "evals" / "results").mkdir(parents=True, exist_ok=True)
    (ROOT / "evals" / "results" / "usage.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))


asyncio.run(main(sys.argv[1], int(sys.argv[2])))