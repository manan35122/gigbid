"""Build the RAG dev set. Gold comes from generator project slugs, independent of any retriever."""
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from rag.ingest.generate_personas import INDUSTRIES, PERSONAS  # noqa: E402

PHRASE = {
    "rag_support": "a search assistant that answers questions from our help-centre articles and needs precise retrieval",
    "churn_model": "a model that predicts which subscribers will cancel next month",
    "defect_vision": "automatic detection of scratches and flaws in product photos on a factory line",
    "llm_finetune": "adapt an open language model to answer questions in our specialised domain",
    "ticket_nlp": "automatically sort incoming customer emails into the right queue",
    "mlops_deploy": "packaging our models so they ship reliably with experiment tracking and automated checks",
    "demand_forecast": "weekly sales forecasts for our product groups with proper backtesting",
    "analytics_dashboard": "an internal dashboard with user roles that shows our key numbers",
    "storefront": "an online shop with card payments that loads fast on phones",
    "rest_api": "a secure backend API with token login and protection against abuse",
    "realtime": "live in-app alerts that reach thousands of users instantly",
    "php_migration": "move our old PHP website to a modern framework without breaking existing links",
    "ci_docker": "containerise our services and automate testing and releases",
    "react_perf": "our front end feels slow and needs profiling and speed-ups",
    "sales_dashboard": "an interactive sales report for regional managers with restricted access per region",
    "dbt_pipeline": "a tested, documented transformation layer on our data warehouse",
    "ab_test": "analyse our experiment results and tell us whether the new variant really won",
    "survey_cleaning": "clean a large messy survey export and produce weighted summaries",
    "cohort_retention": "show where users drop off by acquisition channel over time",
    "finance_report": "consolidate month-end figures from several systems into one reconciled view",
    "excel_automation": "automate our repetitive weekly spreadsheet reports",
}
EVIDENCE = {"case_study", "repo_readme", "repo_code", "review"}
rng = random.Random(11)
out = []
for pid, p in PERSONAS.items():
    corpus = json.loads((ROOT / "data" / "personas" / pid / "corpus.json").read_text(encoding="utf-8"))
    slugs = [s[0] for s in p["seeds"]]
    for n in (1, 2, 3, 4):
        for j in range(12):
            chosen = rng.sample(slugs, n)
            text = (f"We are a {rng.choice(INDUSTRIES)} company looking for a freelancer. Scope: "
                    + " Also, ".join(PHRASE[s] for s in chosen) + ". Please share relevant past work.")
            gold = [i["evidence_id"] for i in corpus if i["type"] in EVIDENCE and i["project"] in chosen]
            out.append(dict(id=f"{pid}-{n}-{j}", persona_id=pid, n_requirements=n, query=text,
                            gold_projects=chosen, gold_ids=gold))
(ROOT / "evals" / "datasets" / "rag_dev.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
print(f"{len(out)} dev queries")