"""Conversation graph: load client message -> classify -> draft reply -> interrupt -> send."""
import asyncio
import json
import re

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from agent.llm import chat, prompt
from agent.mcp_client import call
from agent.nodes.common import step
from agent.state import ConversationState

OFFPLATFORM = re.compile(r"whatsapp|telegram|paypal|skype|outside (of )?the platform|ignore (all )?(previous|prior)", re.I)
FORBIDDEN = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+|https?://\S+|\+?\d[\d\s().-]{8,}\d|guarantee|whatsapp|telegram|paypal", re.I)
def clean_text(t: str) -> str:
    for a, b in {"\u2011": "-", "\u2010": "-", "\u2013": "-", "\u2014": "-", "\u2019": "'", "\u2018": "'",
                 "\u201c": '"', "\u201d": '"', "\u202f": " ", "\u00a0": " "}.items():
        t = t.replace(a, b)
    return t.strip()

async def load(state):
    try:
        msgs = await call("liaison", "marketplace", "list_messages", {"proposal_id": state["proposal_id"]})
        client = [m for m in msgs if m["sender"] == "client"]
        if not client:
            return {"status": "no_message", **step("load")}
        return {"message": client[-1], "status": "running", **step("load")}
    except Exception as e:
        return {"status": "needs_attention", "errors": [f"marketplace unavailable: {e}"], **step("load", error=str(e))}


async def classify(state):
    text = state["message"]["text"]
    intent = {"intent": "other", "reason": "default"}
    try:
        out = await asyncio.to_thread(chat, "client_liaison", prompt("liaison_classify"),
                                      f"<client_message>\n{text}\n</client_message>")
        intent = json.loads(re.search(r"\{.*\}", out, re.S).group(0))
    except Exception:
        pass
    if OFFPLATFORM.search(text):  # rule layer: cannot be talked out of it by the model
        intent = {"intent": "scam_signal", "reason": "off-platform or instruction-like text"}
    return {"intent": intent, **step("classify", intent=intent.get("intent"))}


def after_classify(state):
    if state.get("status") == "needs_attention":
        return END
    return END if state["intent"]["intent"] == "scam_signal" else "draft"


async def draft(state):
    intent, text = state["intent"]["intent"], state["message"]["text"]
    slots = []
    if intent == "interview_request":
        try:
            slots = (await call("liaison", "workspace", "free_slots", {}))[:3]
        except Exception as e:
            return {"status": "needs_attention", "errors": [f"calendar unavailable: {e}"], **step("draft", error=str(e))}
    try:
        ev = await call("liaison", "portfolio", "search_evidence",
                        {"requirement": text[:500], "k": 3, "persona_id": state["persona_id"]})
    except Exception:
        ev = []
    ev_txt = "\n".join(f"[{e['evidence_id']}] {e['title']}: {e['text']}" for e in ev)
    user = (f"INTENT: {intent}\nSLOTS: {json.dumps([s['start'] for s in slots])}\n"
            f"<evidence>\n{ev_txt}\n</evidence>\n<client_message>\n{text}\n</client_message>")
    reply = clean_text(await asyncio.to_thread(chat, "client_liaison", prompt("liaison_reply"), user, 1500))
    bad = FORBIDDEN.findall(reply)
    if bad or not reply:  # guard: unsafe output is dropped, human writes it instead
        return {"reply": "", "slots": slots, "errors": ["draft blocked by compliance; write the reply yourself"],
                **step("draft", blocked=True)}
    return {"reply": reply, "slots": slots, **step("draft", words=len(reply.split()))}


async def approval(state):
    ans = interrupt(dict(proposal_id=state["proposal_id"], message=state["message"], intent=state["intent"],
                         reply=state.get("reply", ""), slots=state.get("slots", []),
                         warnings=state.get("errors", [])))
    action = ans.get("action") if isinstance(ans, dict) else None
    if action not in ("approve", "edit"):
        return {"approval": {"action": "reject"}, "status": "rejected", **step("approval", action="reject")}
    text = (ans.get("edited_text") or state.get("reply") or "").strip()
    if not text or FORBIDDEN.search(text):
        return {"approval": {"action": "reject"}, "status": "needs_attention",
                "errors": ["reply empty or breaks marketplace rules"], **step("approval", action="blocked")}
    return {"approval": {"action": action, "text": text, "slot": ans.get("slot")}, "status": "approved",
            **step("approval", action=action)}


def after_approval(state):
    return "send" if state["approval"].get("action") in ("approve", "edit") and state["status"] == "approved" else END


async def send(state):
    a, pid = state["approval"], state["proposal_id"]
    try:
        sent = await call("liaison_send", "marketplace", "send_message",
                          dict(proposal_id=pid, text=a["text"], idempotency_key=f"{state['persona_id']}:{pid}:reply"))
        if a.get("slot"):
            await call("liaison_send", "workspace", "create_tentative_hold",
                       dict(start=a["slot"], title=f"Interview ({pid})", idempotency_key=f"{pid}:hold"))
    except Exception as e:
        return {"status": "needs_attention", "errors": [f"send failed: {e}"], **step("send", error=str(e))}
    return {"sent": sent, "status": "sent", **step("send")}


def build(checkpointer=None, store=None):
    g = StateGraph(ConversationState)
    for n, f in [("load", load), ("classify", classify), ("draft", draft), ("approval", approval), ("send", send)]:
        g.add_node(n, f)
    g.add_edge(START, "load")
    g.add_conditional_edges("load", lambda s: "classify" if s.get("status") == "running" else END, ["classify", END])
    g.add_conditional_edges("classify", after_classify, ["draft", END])
    g.add_edge("draft", "approval")
    g.add_conditional_edges("approval", after_approval, ["send", END])
    g.add_edge("send", END)
    return g.compile(checkpointer=checkpointer, store=store)