import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from agent.llm import chat, prompt  # noqa: E402
from rag import verify as V  # noqa: E402
from rag.retriever import get_retriever  # noqa: E402

ev = get_retriever("v0")("ai_engineer", "fine-tune LLM LangChain FastAPI", 5)
draft = ("I fine-tuned a 7B model with LoRA and raised answer accuracy from 61% to 79%. "
         "I also built a RAG assistant with LangChain and FastAPI.")
sents = V.split_claims(draft)
evt = "\n".join(f"[{e['evidence_id']}] {e['title']}: {e['text']}" for e in ev)
user = f"<evidence>\n{evt}\n</evidence>\n<sentences>\n{json.dumps(list(enumerate(sents)))}\n</sentences>"
try:
    print(repr(chat("verifier", prompt("verify_claim"), user, 2500)))
except Exception as e:
    print("EXCEPTION:", type(e).__name__, e)