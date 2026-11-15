"""python evals/runners/decision_eval.py ai_engineer 60 -> evals/results/decision_eval_<persona>.json
Runs the bid graph (no approval step reached: it stops at the interrupt) on N stream jobs and scores:
 - bid/skip F1 against the synthetic gold rule
 - scam precision/recall
 - price inside the fair band (bid jobs only)"""
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

HARD = {"prompt_injection", "off_platform_contact", "unpaid_work"}


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return dict(precision=round(p, 3), recall=round(r, 3),
                f1=round(2 * p * r / (p + r), 3) if p + r else 0.0, tp=tp, fp=fp, fn=fn)


async def main(persona, n):
    prof = json.loads((ROOT / "data/personas" / persona / "profile.json").read_text())
    gold = {g["job_id"]: g for g in json.loads((ROOT / "gigsim_local/data/gold.json").read_text())}
    jobs = [j["job_id"] for j in json.loads((ROOT / "gigsim_local/data/jobs_stream.json").read_text())][:n]
    stamp = int(time.time())
    rows = []
    async with saver() as cp:
        graph = build(cp)
        for jid in jobs:
            run_id.set(f"dec:{persona}:{jid}:{stamp}")
            s = await graph.ainvoke({"job_id": jid, "persona_id": persona},
                                    {"configurable": {"thread_id": f"dec:{stamp}:{persona}:{jid}"}})
            if s.get("status") == "needs_attention":
                print(jid, "NEEDS ATTENTION", s.get("errors"))
                continue
            g = gold[jid]
            gold_bid = (not g["is_scam"]) and g["category"] == prof["category"]
            pred_bid = s["decision"]["action"] == "bid"
            flagged = bool(HARD & set(s["risk_report"]["flags"]))
            in_band = None
            if pred_bid and "price_quote" in s:
                lo, hi = g["fair_price_band"]
                in_band = lo <= s["price_quote"]["bid_amount"] <= hi
            rows.append(dict(job=jid, gold_bid=gold_bid, pred_bid=pred_bid, scam=g["is_scam"],
                             flagged=flagged, action=s["decision"]["action"], in_band=in_band,
                             fit=s["fit_report"]["score"]))
            print(jid, "gold_bid" if gold_bid else "gold_skip", s["decision"]["action"], rows[-1]["fit"])
    cnt = lambda f: sum(1 for r in rows if f(r))  # noqa: E731
    band = [r["in_band"] for r in rows if r["in_band"] is not None]
    out = dict(persona=persona, n=len(rows), gold_rule="bid = not scam AND job category == persona category",
               bid_skip=prf(cnt(lambda r: r["gold_bid"] and r["pred_bid"]),
                            cnt(lambda r: not r["gold_bid"] and r["pred_bid"]),
                            cnt(lambda r: r["gold_bid"] and not r["pred_bid"])),
               scam=prf(cnt(lambda r: r["scam"] and r["flagged"]), cnt(lambda r: not r["scam"] and r["flagged"]),
                        cnt(lambda r: r["scam"] and not r["flagged"])),
               price_in_fair_band=dict(n=len(band), rate=round(sum(band) / len(band), 3) if band else None),
               watch_count=cnt(lambda r: r["action"] == "watch"),
               false_negatives=[r["job"] for r in rows if r["gold_bid"] and not r["pred_bid"]][:15],
               false_positives=[r["job"] for r in rows if not r["gold_bid"] and r["pred_bid"]][:15])
    (ROOT / "evals/results").mkdir(parents=True, exist_ok=True)
    (ROOT / "evals/results" / f"decision_eval_{persona}.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


asyncio.run(main(sys.argv[1], int(sys.argv[2])))