"""Corpus loading + embedding index (numpy, cached on disk). Embeddings run on CPU via fastembed."""
from functools import lru_cache
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
PERSONAS = ROOT / "data" / "personas"
CACHE = ROOT / "data" / "processed"
MODEL = "BAAI/bge-small-en-v1.5"
EVIDENCE_TYPES = ["case_study", "repo_readme", "repo_code", "review"]  # past_proposal is NOT evidence


@lru_cache(maxsize=1)
def _embedder():
    from fastembed import TextEmbedding
    return TextEmbedding(MODEL)


def embed(texts: list[str]) -> np.ndarray:
    m = np.array(list(_embedder().embed(texts)), dtype="float32")
    return m / np.linalg.norm(m, axis=1, keepdims=True)


def doc_text(it: dict) -> str:
    return f"{it['title']}. {it['text']} Skills: {', '.join(it.get('skills') or [])}"


@lru_cache(maxsize=8)
def load_corpus(persona_id: str) -> list[dict]:
    return json.loads((PERSONAS / persona_id / "corpus.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=8)
def get_index(persona_id: str):
    items = load_corpus(persona_id)
    src = PERSONAS / persona_id / "corpus.json"
    f = CACHE / persona_id / "emb_bge_small.npy"
    if f.exists() and f.stat().st_mtime > src.stat().st_mtime:
        mat = np.load(f)
        if len(mat) == len(items):
            return items, mat
    mat = embed([doc_text(i) for i in items])
    f.parent.mkdir(parents=True, exist_ok=True)
    np.save(f, mat)
    return items, mat


def allowed_mask(items: list[dict], filters: dict | None) -> np.ndarray:
    f = filters or {}
    types = f.get("types") or EVIDENCE_TYPES
    skills = {s.lower() for s in f.get("skills", [])}
    industry = f.get("industry")
    ok = []
    for it in items:
        good = it["type"] in types
        if good and skills:
            good = bool(skills & {s.lower() for s in it.get("skills") or []})
        if good and industry:
            good = it.get("industry") == industry
        ok.append(good)
    return np.array(ok)


def get_item(persona_id: str, evidence_id: str) -> dict | None:
    return next((i for i in load_corpus(persona_id) if i["evidence_id"] == evidence_id), None)