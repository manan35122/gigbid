"""Usage: python evals/runners/rag_eval.py v0 v2 v1 v1_v2   -> evals/results/rag_eval.json"""
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from rag.retriever import VARIANTS, get_retriever  # noqa: E402


def metrics(hits, gold_ids, gold_projects):
    covered = {h["project"] for h in hits[:5]} & set(gold_projects)
    recall = len(covered) / len(gold_projects)
    mrr = next((1 / r for r, h in enumerate(hits, 1) if h["evidence_id"] in gold_ids), 0.0)
    dcg = sum(1 / math.log2(r + 1) for r, h in enumerate(hits[:10], 1) if h["evidence_id"] in gold_ids)
    ideal = sum(1 / math.log2(r + 1) for r in range(1, min(len(gold_ids), 10) + 1))
    return dict(recall5=recall, mrr=mrr, ndcg10=dcg / ideal if ideal else 0.0)


def mean(xs):
    return round(sum(xs) / len(xs), 4)


def main(names):
    data = json.loads((ROOT / "evals" / "datasets" / "rag_dev.json").read_text(encoding="utf-8"))
    path = ROOT / "evals" / "results" / "rag_eval.json"
    results = json.loads(path.read_text()) if path.exists() else {}
    for name in names:
        retr = get_retriever(name)
        rows = []
        for q in data:
            m = metrics(retr(q["persona_id"], q["query"], 10), set(q["gold_ids"]), q["gold_projects"])
            rows.append((q, m))
        agg = {"overall": {k: mean([m[k] for _, m in rows]) for k in ("recall5", "mrr", "ndcg10")}}
        for dim in ("n_requirements", "persona_id"):
            grp = defaultdict(list)
            for q, m in rows:
                grp[str(q[dim])].append(m)
            agg[dim] = {g: {k: mean([m[k] for m in ms]) for k in ("recall5", "mrr", "ndcg10")}
                        for g, ms in sorted(grp.items())}
        results[name] = agg
        print(name, agg["overall"], "by n_req recall5:",
              {g: v["recall5"] for g, v in agg["n_requirements"].items()})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(results, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1:] or [n for n in VARIANTS])