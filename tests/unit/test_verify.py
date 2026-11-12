from rag.retriever import get_retriever
from rag.verify import verify

DRAFT = ("I built a RAG assistant that cut ticket handling time by 31%. "
         "I have five years of Celery and Kubernetes experience. "
         "Happy to discuss your setup?")


def test_unsupported_claim_is_removed():
    ev = get_retriever("v0")("ai_engineer", "RAG assistant, Celery, Kubernetes", 5)
    r = verify(DRAFT, ev)
    verdicts = {c["sentence"][:12]: c["verdict"] for c in r["claims"]}
    assert verdicts["I have five "] == "unsupported"
    assert "Celery" not in r["clean_text"]