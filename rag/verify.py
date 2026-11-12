"""Claim verification: split a draft into sentences, grade each against evidence, drop unsupported."""
import json
import re

from agent.llm import chat, prompt


def split_claims(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text.strip())
    return [p.strip() for p in parts if len(p.strip()) > 3]


def verify(draft: str, evidence: list[dict]) -> dict:
    sents = split_claims(draft)
    ev = "\n".join(f"[{e['evidence_id']}] {e['title']}: {e['text']}" for e in evidence)
    user = f"<evidence>\n{ev}\n</evidence>\n<sentences>\n{json.dumps(list(enumerate(sents)))}\n</sentences>"
    verdicts = {}
    try:
        out = chat("verifier", prompt("verify_claim"), user, max_tokens=2500)
        m = re.search(r"\[.*\]", out, re.S)
        verdicts = {v["i"]: v for v in json.loads(m.group(0))}
    except Exception:
        pass  # fail closed: anything not graded is treated as unsupported below
    claims = []
    for i, s in enumerate(sents):
        v = verdicts.get(i, {})
        claims.append(dict(sentence=s, verdict=v.get("verdict", "unsupported"),
                           evidence_ids=v.get("evidence_ids", []), reason=v.get("reason", "ungraded")))
    kept = [c["sentence"] for c in claims if c["verdict"] != "unsupported"]
    graded = [c for c in claims if c["verdict"] != "no_claim"]
    unsup = sum(c["verdict"] == "unsupported" for c in graded)
    return dict(claims=claims, clean_text=" ".join(kept),
                unsupported=unsup, unsupported_rate=round(unsup / len(graded), 3) if graded else 0.0)