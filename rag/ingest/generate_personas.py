"""Generate SYNTHETIC freelancer persona corpora (seeded).
Run: python rag/ingest/generate_personas.py
Output per persona in data/personas/<id>/: profile.json, cv.md, corpus.json
"""
import json
import random
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "personas"
rng = random.Random(7)
TODAY = date(2026, 11, 11)
INDUSTRIES = ["retail", "healthcare", "fintech", "logistics", "education", "real estate", "SaaS", "travel"]

# seed = (slug, title, skills, what [past tense, lowercase], result)
PERSONAS = {
    "ai_engineer": dict(
        name="Ayesha Khan", headline="AI/ML engineer: RAG, NLP and computer vision", floor=35,
        category="ai_ml", seeds=[
            ("rag_support", "RAG assistant over support documents",
             ["RAG", "LangChain", "FastAPI", "pgvector", "reranking"],
             "built a retrieval pipeline combining BM25 and dense search with a cross-encoder reranker",
             "cut average ticket handling time by 31%"),
            ("churn_model", "Customer churn prediction model",
             ["Python", "scikit-learn", "XGBoost", "classification", "model evaluation"],
             "trained and calibrated a gradient boosting churn model with a leakage-safe validation split",
             "lifted recall at fixed precision from 0.52 to 0.68"),
            ("defect_vision", "Visual defect detection pipeline",
             ["PyTorch", "computer vision", "ONNX", "OpenCV"],
             "trained a CNN to flag surface defects and exported it to ONNX for edge inference",
             "reached 94% defect recall on a held-out line"),
            ("llm_finetune", "Fine-tuned LLM for domain Q&A",
             ["LLM", "LoRA", "PEFT", "Hugging Face", "PyTorch"],
             "fine-tuned a 7B model with LoRA on curated question-answer pairs",
             "raised answer accuracy from 61% to 79% on an internal test set"),
            ("ticket_nlp", "Support ticket classification",
             ["NLP", "transformers", "Python", "text classification"],
             "built a multi-label ticket classifier on top of a transformer encoder",
             "routed 82% of tickets correctly without manual triage"),
            ("mlops_deploy", "Model deployment with MLOps tooling",
             ["MLOps", "MLflow", "Docker", "GitHub Actions", "FastAPI"],
             "containerised models, tracked experiments in MLflow and added CI checks before release",
             "shortened release cycles from two weeks to two days"),
            ("demand_forecast", "Demand forecasting service",
             ["Python", "LightGBM", "time series", "pandas"],
             "built a weekly demand forecaster with backtesting across 40 product groups",
             "reduced forecast error (MAPE) by 18%"),
        ]),
    "fullstack_dev": dict(
        name="Bilal Ahmed", headline="Full-stack web developer: React, Next.js, FastAPI, PostgreSQL", floor=30,
        category="web_dev", seeds=[
            ("analytics_dashboard", "Analytics dashboard web app",
             ["React", "TypeScript", "FastAPI", "PostgreSQL", "REST API"],
             "built a role-based analytics dashboard with a typed API client generated from OpenAPI",
             "replaced manual weekly reporting for a team of 25"),
            ("storefront", "Next.js storefront with payments",
             ["Next.js", "TypeScript", "Stripe", "Tailwind"],
             "shipped a server-rendered storefront with Stripe checkout and image optimisation",
             "improved mobile conversion by 22%"),
            ("rest_api", "Secure REST API platform",
             ["Node.js", "REST API", "PostgreSQL", "JWT", "rate limiting"],
             "designed a REST API with JWT auth, rate limiting and request validation",
             "handled 3x traffic growth without downtime"),
            ("realtime", "Realtime notifications service",
             ["WebSockets", "Node.js", "Redis", "React"],
             "implemented live notifications over WebSockets with Redis pub/sub fan-out",
             "delivered updates in under 300 ms for 5,000 concurrent users"),
            ("php_migration", "Legacy PHP to Next.js migration",
             ["Next.js", "TypeScript", "PostgreSQL", "migration"],
             "migrated a legacy PHP site to Next.js in stages while keeping the old URLs working",
             "cut page load time from 4.1 s to 1.3 s"),
            ("ci_docker", "Dockerised deployment and CI/CD",
             ["Docker", "GitHub Actions", "CI/CD", "Nginx"],
             "containerised a multi-service app and automated tests and deploys with GitHub Actions",
             "removed manual deploy steps and cut failed releases to near zero"),
            ("react_perf", "React performance overhaul",
             ["React", "performance", "Webpack", "TypeScript"],
             "profiled render bottlenecks, split bundles and memoised expensive components",
             "reduced time-to-interactive by 45%"),
        ]),
    "data_analyst": dict(
        name="Sana Raza", headline="Data analyst: SQL, dbt, Power BI and experimentation", floor=25,
        category="data_analysis", seeds=[
            ("sales_dashboard", "Sales performance dashboard",
             ["Power BI", "SQL", "DAX", "data modeling"],
             "modelled a star schema and built an interactive sales dashboard with row-level security",
             "gave regional managers self-serve reporting and retired three spreadsheets"),
            ("dbt_pipeline", "dbt analytics pipeline",
             ["dbt", "SQL", "BigQuery", "ETL", "data testing"],
             "set up a dbt project with staging and mart layers, tests and documentation",
             "cut broken-report incidents by 60%"),
            ("ab_test", "A/B test analysis",
             ["statistics", "Python", "A/B testing", "pandas"],
             "designed and analysed A/B tests with power calculations and sequential checks",
             "identified a variant that lifted sign-ups by 9% with a clear confidence interval"),
            ("survey_cleaning", "Survey data cleaning and modelling",
             ["pandas", "Python", "statistics", "data cleaning"],
             "cleaned a messy 12,000-response survey and built weighted summary tables",
             "delivered a report the client reused for its board pack"),
            ("cohort_retention", "Cohort retention analysis",
             ["SQL", "cohort analysis", "Tableau", "Python"],
             "built cohort retention queries and a Tableau view showing drop-off by acquisition channel",
             "pinpointed a week-two churn spike that product then fixed"),
            ("finance_report", "Monthly finance reporting",
             ["Tableau", "SQL", "Excel", "ETL"],
             "automated month-end reporting from three source systems into one reconciled view",
             "saved about 12 analyst hours every month"),
            ("excel_automation", "Excel reporting automation",
             ["Excel", "Python", "openpyxl", "automation"],
             "automated recurring Excel reports with Python and scheduled delivery",
             "removed a four-hour weekly manual task"),
        ]),
}


def describe(seed, industry, style):
    slug, title, skills, what, result = seed
    if style == "narrative":
        return f"For a {industry} client, I {what}. Outcome: {result}. Stack: {', '.join(skills)}."
    if style == "terse":
        return f"- Project: {title} ({industry})\n- Delivered: {what}\n- Result: {result}"
    return f"{result.capitalize()}. I {what}."  # 'implied': tools often not listed


def rdate(lo=20, hi=900):
    return (TODAY - timedelta(days=rng.randint(lo, hi))).isoformat()


def proposal(seed, industry):
    slug, title, skills, what, result = seed
    kind = rng.choices(["specific", "medium", "generic"], [0.45, 0.3, 0.25])[0]
    if kind == "specific":
        text = (f"I recently {what} for a {industry} client, which {result}. Your job needs "
                f"{', '.join(skills[:3])}, and I have used them together on this kind of problem. "
                f"What does your current setup look like?")
        probs = (0.22, 0.38)
    elif kind == "medium":
        text = (f"Hello, I read your post and can help. I have experience with {', '.join(skills[:3])}. "
                f"I can start immediately. Let me know the next steps.")
        probs = (0.06, 0.24)
    else:
        text = ("Dear Sir, I am the best freelancer for your project. I have many years of experience "
                "and will deliver quality work on time. Please hire me. I am hardworking and passionate.")
        probs = (0.01, 0.08)
    r = rng.random()
    outcome = "won" if r < probs[0] else "replied" if r < probs[0] + probs[1] else "ignored"
    return kind, text, outcome


def build(pid, p):
    seeds, items = p["seeds"], []
    # 18 case studies: same seeds recur across industries and styles
    for i in range(18):
        seed, ind = seeds[i % 7], INDUSTRIES[(i + i // 7) % len(INDUSTRIES)]
        items.append(dict(
            evidence_id=f"{pid}-cs-{i:02d}", persona_id=pid, type="case_study", project=seed[0],
            title=f"{seed[1]} ({ind})", industry=ind, skills=seed[2], date=rdate(),
            outcome=seed[4], text=describe(seed, ind, rng.choice(["narrative", "terse", "implied"]))))
    # repos: README + code for 5 projects (README alone often hides the skills)
    for i, seed in enumerate(seeds[:5]):
        items.append(dict(
            evidence_id=f"{pid}-readme-{i}", persona_id=pid, type="repo_readme", project=seed[0],
            title=f"{seed[0]} README", industry=None, skills=seed[2][:2], date=rdate(),
            outcome=None, text=f"# {seed[0]}\n\n{seed[1]}.\n\n## Setup\nInstall requirements and run the "
                               f"entry script.\n\n## Usage\nSee the examples folder."))
        items.append(dict(
            evidence_id=f"{pid}-code-{i}", persona_id=pid, type="repo_code", project=seed[0],
            title=f"{seed[0]} core module", industry=None, skills=seed[2], date=rdate(), outcome=None,
            text=f"# {seed[0]}/core.py\n# implements: {', '.join(seed[2])}\n"
                 f"def run(config):\n    # {seed[3]}\n    ..."))
    # reviews
    for i in range(8):
        seed, ind = seeds[i % 7], rng.choice(INDUSTRIES)
        items.append(dict(
            evidence_id=f"{pid}-rev-{i}", persona_id=pid, type="review", project=seed[0],
            title=f"Client review: {seed[1]}", industry=ind, skills=seed[2][:2], date=rdate(),
            outcome=None, rating=rng.choice([4.5, 4.8, 5.0]),
            text=f"Delivered {seed[1].lower()} on time and communicated clearly. {seed[4].capitalize()}."))
    # 150 labelled past proposals
    for i in range(150):
        seed, ind = rng.choice(seeds), rng.choice(INDUSTRIES)
        kind, text, outcome = proposal(seed, ind)
        items.append(dict(
            evidence_id=f"{pid}-pr-{i:03d}", persona_id=pid, type="past_proposal", project=seed[0],
            title=f"Past proposal: {seed[1]}", industry=ind, skills=seed[2], date=rdate(),
            outcome=outcome, style=kind, text=text))
    for it in items:
        it["data_origin"] = "synthetic"
    return items


def main():
    for pid, p in PERSONAS.items():
        d = OUT / pid
        d.mkdir(parents=True, exist_ok=True)
        items = build(pid, p)
        skills = sorted({s for sd in p["seeds"] for s in sd[2]})
        (d / "profile.json").write_text(json.dumps(dict(
            persona_id=pid, name=p["name"], headline=p["headline"], hourly_floor_usd=p["floor"],
            category=p["category"], skills=skills, data_origin="synthetic"), indent=1), encoding="utf-8")
        cv = [f"# {p['name']}", f"_{p['headline']}_  (SYNTHETIC PERSONA)", "", "## Skills", ", ".join(skills),
              "", "## Selected projects"] + [f"- {sd[1]}: {sd[4]}" for sd in p["seeds"]]
        (d / "cv.md").write_text("\n".join(cv), encoding="utf-8")
        (d / "corpus.json").write_text(json.dumps(items, indent=1), encoding="utf-8")
        won = sum(i["outcome"] == "won" for i in items if i["type"] == "past_proposal")
        print(f"{pid}: {len(items)} items, past proposals won={won}")


if __name__ == "__main__":
    main()