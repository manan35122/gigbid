"""Arq worker. Run: arq worker.main.WorkerSettings"""
import asyncio
import os
import sys

from arq import cron
from arq.connections import RedisSettings

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from agent.checkpoint import saver  # noqa: E402
from agent.graphs.bid_graph import build  # noqa: E402
from agent.llm import run_id  # noqa: E402
from agent.memory.store import open_store  # noqa: E402
from agent.nodes.common import cfg  # noqa: E402
from agent.nodes.scout import scout  # noqa: E402
from mcp_servers.marketplace.adapters.gigsim import GigSimAdapter  # noqa: E402


async def startup(ctx):
    ctx["cp_cm"], ctx["store_cm"] = saver(), open_store()
    cp = await ctx["cp_cm"].__aenter__()
    ctx["store"] = await ctx["store_cm"].__aenter__()
    ctx["graph"] = build(cp, ctx["store"])
    ctx["adapter"] = GigSimAdapter()


async def shutdown(ctx):
    await ctx["store_cm"].__aexit__(None, None, None)
    await ctx["cp_cm"].__aexit__(None, None, None)


async def analyse(ctx, persona: str, job_id: str):
    """Run the bid graph; it stops at the approval interrupt (or earlier). Never submits."""
    c = {"configurable": {"thread_id": f"{persona}:{job_id}"}}
    if (await ctx["graph"].aget_state(c)).values:
        return "already_processed"          # idempotent: a restart never re-analyses
    run_id.set(f"{persona}:{job_id}")
    s = await ctx["graph"].ainvoke({"job_id": job_id, "persona_id": persona}, c)
    return s.get("status")


async def scout_job(ctx):
    w, queued = cfg()["worker"], 0
    for persona in w["personas"]:
        for q in w["saved_searches"]:
            try:
                jobs = await ctx["adapter"].search_jobs(q, 50, 0)
            except Exception as e:      # marketplace down: skip this round, try again next schedule
                print("scout: marketplace unavailable:", e)
                continue
            res = await scout(ctx["store"], persona, jobs)
            for j in res["new"][: w["scout_batch"]]:
                await ctx["redis"].enqueue_job("analyse", persona, j["job_id"],
                                               _job_id=f"{persona}:{j['job_id']}")  # dedup by id
                queued += 1
    print(f"scout: queued {queued} jobs")
    return queued


class WorkerSettings:
    functions = [analyse]
    cron_jobs = [cron(scout_job, minute=set(range(0, 60, max(cfg()["worker"]["scout_every_minutes"], 1))),
                      run_at_startup=True)]
    on_startup, on_shutdown = startup, shutdown
    redis_settings = RedisSettings.from_dsn(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    max_jobs = 2           # polite: at most two analyses at once