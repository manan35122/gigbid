"""Map the Kaggle Upwork CSV onto GigSim's history format (REAL data, fixed-price jobs only).
Run: python gigsim_local/ingest_kaggle.py   ->   gigsim_local/data/jobs_history_real.json"""
import json
import re
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
RAW = HERE.parent / "data" / "raw" / "upwork-jobs.csv"
OUT = HERE / "data" / "jobs_history_real.json"

CATS = {
    "ai_ml": ["machine learning", "deep learning", "nlp", "natural language", "llm", "openai", "chatgpt",
              "computer vision", "pytorch", "tensorflow", "scikit-learn", "langchain", "artificial intelligence"],
    "web_dev": ["react", "next.js", "node.js", "typescript", "javascript", "fastapi", "django", "flask",
                "web development", "rest api", "postgresql", "tailwind"],
    "data_analysis": ["sql", "data analysis", "tableau", "power bi", "pandas", "dbt", "data visualization",
                      "statistics", "etl", "data cleaning", "excel"],
}


def parse_skills(desc: str) -> list[str]:
    m = re.search(r"Skills:\s*(.*?)(?:Skills:|click to apply|$)", desc, re.S)
    return [s.strip() for s in m.group(1).split(",") if s.strip()][:10] if m else []


def category(skills: list[str]) -> str | None:
    low = " ".join(skills).lower()
    hits = {c: sum(k in low for k in kws) for c, kws in CATS.items()}
    best = max(hits, key=hits.get)
    return best if hits[best] else None


def main():
    df = pd.read_csv(RAW, usecols=["title", "description", "budget", "published_date"])
    df = df[df["budget"].notna() & (df["budget"] >= 20) & (df["budget"] <= 20000)]
    rows = []
    for r in df.itertuples():
        skills = parse_skills(str(r.description))
        cat = category(skills)
        if skills and cat:
            rows.append(dict(title=r.title, required_skills=skills, category=cat,
                             budget=dict(min=float(r.budget), max=float(r.budget), currency="USD"),
                             duration_days=None, posted_at=str(r.published_date)[:10], data_origin="real"))
    OUT.write_text(json.dumps(rows[:6000]), encoding="utf-8")
    by = pd.Series([x["category"] for x in rows]).value_counts().to_dict()
    print(f"kept {len(rows)} of {len(df)} fixed-price rows; by category: {by}")


if __name__ == "__main__":
    main()