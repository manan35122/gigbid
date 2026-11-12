"""V0: naive dense retrieval. Top-k cosine over the whole query. The baseline everything must beat."""
import numpy as np

from rag.index.store import allowed_mask, embed, get_index


def retrieve(persona_id: str, query: str, k: int = 5, filters: dict | None = None) -> list[dict]:
    items, mat = get_index(persona_id)
    scores = mat @ embed([query])[0]
    scores[~allowed_mask(items, filters)] = -np.inf
    top = [i for i in np.argsort(-scores)[:k] if np.isfinite(scores[i])]
    return [dict(items[i], score=round(float(scores[i]), 4)) for i in top]