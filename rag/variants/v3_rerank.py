"""V3: hybrid (V2) candidates reranked by a cross-encoder. Improves precision at small k."""
from functools import lru_cache

from rag.variants import v2_hybrid

MODEL = "Xenova/ms-marco-MiniLM-L-6-v2"  # CHECK against the supported-models list
POOL = 30


@lru_cache(maxsize=1)
def _encoder():
    from fastembed.rerank.cross_encoder import TextCrossEncoder
    return TextCrossEncoder(MODEL)


def retrieve(persona_id: str, query: str, k: int = 5, filters: dict | None = None):
    cands = v2_hybrid.retrieve(persona_id, query, POOL, filters)
    if not cands:
        return []
    docs = [f"{c['title']}. {c['text']} Skills: {', '.join(c.get('skills') or [])}" for c in cands]
    scores = list(_encoder().rerank(query, docs))
    ranked = sorted(zip(cands, scores), key=lambda x: -x[1])[:k]
    return [dict(c, score=round(float(s), 4)) for c, s in ranked]