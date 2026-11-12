"""V2: BM25 + dense, fused with reciprocal rank fusion (RRF). Helps exact tool names."""
import re
from functools import lru_cache

import numpy as np
from rank_bm25 import BM25Okapi

from rag.index.store import allowed_mask, doc_text, embed, get_index


def tok(s: str) -> list[str]:
    return re.findall(r"[a-z0-9+#.]+", s.lower())


@lru_cache(maxsize=8)
def _bm25(pid: str) -> BM25Okapi:
    items, _ = get_index(pid)
    return BM25Okapi([tok(doc_text(i)) for i in items])


def retrieve(persona_id: str, query: str, k: int = 5, filters: dict | None = None, pool: int = 50):
    items, mat = get_index(persona_id)
    mask = allowed_mask(items, filters)
    dense = mat @ embed([query])[0]
    bm = np.array(_bm25(persona_id).get_scores(tok(query)), dtype="float32")
    dense[~mask], bm[~mask] = -np.inf, -np.inf
    ranks = []
    for sc in (dense, bm):
        order = [i for i in np.argsort(-sc)[:pool] if mask[i]]
        ranks.append({i: r for r, i in enumerate(order)})
    fused = {i: sum(1 / (60 + rk[i] + 1) for rk in ranks if i in rk) for i in set(ranks[0]) | set(ranks[1])}
    top = sorted(fused, key=fused.get, reverse=True)[:k]
    return [dict(items[i], score=round(fused[i], 5)) for i in top]