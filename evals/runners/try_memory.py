"""Shows the promotion rule: the same edit in 3 different jobs promotes a style rule. Uses persona 'demo'."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from agent.memory.promotion_rules import record_edit  # noqa: E402
from agent.memory.store import open_store  # noqa: E402

BEFORE = "I am passionate about data. I built a churn model with 31% gains. Could you share how your data is stored?"
AFTER = "I built a churn model with 31% gains. Could you share how your data is stored?"


async def main():
    async with open_store() as s:
        for i in range(3):
            print(f"edit in job-{i}: newly promoted =", await record_edit(s, "demo", f"job-{i}", BEFORE, AFTER))
            if i == 0:
                print("  (same job again, must not count twice):", await record_edit(s, "demo", "job-0", BEFORE, AFTER))
        for it in await s.asearch(("demo", "style"), limit=20):
            print("STYLE RULE:", it.key, "->", it.value["rule"])
        for kind in ("style", "style_candidates"):
            for it in await s.asearch(("demo", kind), limit=50):
                await s.adelete(("demo", kind), it.key)


asyncio.run(main())