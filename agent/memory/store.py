"""Long-term memory (C2/R7): a LangGraph Postgres store. Namespaces per persona:
   (persona,'style_candidates') and (persona,'style')     - learned from the user's edits
   (persona,'outcome_candidates') and (persona,'outcome') - what won or got replies, per category
Only promotion_rules.py writes the promoted namespaces."""
from contextlib import asynccontextmanager

from langgraph.store.postgres.aio import AsyncPostgresStore

from agent.checkpoint import db_uri  # importing this also sets the Windows event-loop policy


@asynccontextmanager
async def open_store():
    async with AsyncPostgresStore.from_conn_string(db_uri()) as store:
        await store.setup()
        yield store


CATEGORY_WORDS = {
    "ai_ml": ["rag", "langchain", "pytorch", "nlp", "llm", "scikit", "computer vision", "mlops", "machine learning"],
    "web_dev": ["react", "next.js", "typescript", "node", "fastapi", "postgresql", "tailwind", "docker", "rest"],
    "data_analysis": ["sql", "tableau", "power bi", "dbt", "pandas", "etl", "excel", "statistics"],
}


def category_of(skills: list[str]) -> str:
    low = " ".join(skills).lower()
    score = {c: sum(w in low for w in ws) for c, ws in CATEGORY_WORDS.items()}
    best = max(score, key=score.get)
    return best if score[best] else "other"


async def load_context(store, persona: str, category: str) -> dict:
    """What the Writer may see. Fails soft: if memory is unavailable, drafting still works."""
    if store is None:
        return {"rules": [], "outcome": ""}
    try:
        rules = [i.value["rule"] for i in await store.asearch((persona, "style"), limit=20)]
        o = await store.aget((persona, "outcome"), category)
        return {"rules": rules, "outcome": o.value["summary"] if o else ""}
    except Exception:
        return {"rules": [], "outcome": ""}