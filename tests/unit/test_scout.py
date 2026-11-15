from agent.nodes.scout import fingerprint


def test_repost_has_same_fingerprint():
    a = dict(job_id="new-1", client_id="c1", title="Build a RAG chatbot for retail")
    b = dict(job_id="new-1-dup", client_id="c1", title="Build a RAG chatbot for retail (repost)")
    c = dict(job_id="new-2", client_id="c2", title="Build a RAG chatbot for retail")
    assert fingerprint(a) == fingerprint(b)
    assert fingerprint(a) != fingerprint(c)