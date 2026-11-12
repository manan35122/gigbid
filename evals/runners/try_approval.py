"""python evals/runners/try_approval.py start|resume|replay <persona> <job_id> [approve|reject|edit]"""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agent.checkpoint import saver  # noqa: E402  (also sets the Windows event-loop policy)
from agent.graphs.bid_graph import build  # noqa: E402
from langgraph.types import Command  # noqa: E402


async def main(mode, persona, job_id, arg=None):
    cfg = {"configurable": {"thread_id": f"{persona}:{job_id}"}}
    async with saver() as cp:
        graph = build(cp)
        if mode == "start":
            await graph.ainvoke({"job_id": job_id, "persona_id": persona}, cfg)
        elif mode == "resume":
            ans = {"action": arg}
            if arg == "reject":
                ans["reason"] = "not a good fit"
            if arg == "edit":
                text = (await graph.aget_state(cfg)).values["proposal_draft"]["cover_letter"]
                ans["edited_text"] = text.split(". ", 1)[-1]  # demo edit: drop the first sentence
            await graph.ainvoke(Command(resume=ans), cfg)
        elif mode == "replay":
            target = None
            async for snap in graph.aget_state_history(cfg):
                if snap.next == ("submit",):
                    target = snap.config
                    break
            print("replaying from checkpoint:", target is not None)
            if target:
                await graph.ainvoke(None, target)
        st = await graph.aget_state(cfg)
        print("status:", st.values.get("status"), "| next:", st.next)
        for t in st.tasks:
            for i in t.interrupts:
                v = i.value
                print("WAITING FOR APPROVAL:", v["title"], "| bid", v["price"]["bid_amount"],
                      "| connects", v["preview"].get("connects_cost"))
                print(v["draft"]["cover_letter"])
                print("warnings:", v["warnings"])
        if st.values.get("submission"):
            print("submission:", st.values["submission"])


asyncio.run(main(*sys.argv[1:]))