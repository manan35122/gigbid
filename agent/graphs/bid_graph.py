"""Bid graph: load -> [analyst | risk | fit parallel] -> decide -> pricing -> writer -> verifier -> critic
   (back to writer at most twice) -> compliance. Approval interrupt + Postgres checkpointer come in 9e."""
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send
from agent.llm import run_tokens
from agent.handoffs import BidDecision
from agent.nodes.analysis import analyst, fit_matcher, load_job, risk_assessor
from agent.nodes.common import cfg, step
from agent.nodes.compliance import compliance
from agent.nodes.drafting import critic, verifier, writer
from agent.nodes.pricing import pricing
from agent.state import GigBidState
from agent.nodes.approval import apply_edit, approval, preview, submit
from agent.nodes.scout import NS, fingerprint



def fan_out(state):
    if state.get("status") == "needs_attention":
        return END
    return [Send(n, state) for n in ("analyst", "risk_assessor", "fit_matcher")]


async def decide(state, *, store=None):
    t, risk, fit = cfg()["thresholds"], state["risk_report"], state["fit_report"]

    # duplicate guard: a repost of a job we already bid on is skipped
    if store is not None:
        try:
            hit = await store.aget((state["persona_id"], NS), fingerprint(state["job"]))
            if hit and hit.value["job_id"] != state["job_id"]:
                d = BidDecision(action="skip", reasons=[f"duplicate of {hit.value['job_id']}"])
                return {"decision": d.model_dump(), "status": "skipped",
                        **step("decide", action="skip", duplicate=True)}
        except Exception:
            pass  # dedup must never block a decision

    hard = {"prompt_injection", "off_platform_contact", "unpaid_work"} & set(risk["flags"])
    if hard:
        d = BidDecision(action="skip", reasons=[f"risk flags: {sorted(hard)}"])
    elif risk["score"] >= t["maximum_risk_score"]:
        d = BidDecision(action="skip", reasons=[f"risk {risk['score']} >= {t['maximum_risk_score']}"])
    elif fit["score"] < t["minimum_fit_score"] - 0.1:
        d = BidDecision(action="skip", reasons=[f"fit {fit['score']} well below {t['minimum_fit_score']}"])
    elif fit["score"] < t["minimum_fit_score"]:
        d = BidDecision(action="watch", reasons=[f"fit {fit['score']} slightly below threshold"])
    else:
        d = BidDecision(action="bid", reasons=[f"fit {fit['score']}, risk {risk['score']}"])

    # register the fingerprint so a later repost is recognised
    if store is not None and d.action == "bid":
        try:
            await store.aput((state["persona_id"], NS), fingerprint(state["job"]), {"job_id": state["job_id"]})
        except Exception:
            pass

    status = {"skip": "skipped", "watch": "watching", "bid": "running"}[d.action]
    return {"decision": d.model_dump(), "status": status, **step("decide", action=d.action)}

def after_decide(state):
    return "pricing" if state["decision"]["action"] == "bid" else END


def after_writer(state):
    return END if state.get("status") == "needs_attention" else "verifier"

def over_budget(state):  # C4: step budget and token budget
    b = cfg()["budgets"]
    return state.get("steps", 0) >= b["max_graph_steps"] or run_tokens() > b["max_tokens_per_job"]


async def needs_attention(state):
    return {"status": "needs_attention",
            "errors": [f"budget exceeded ({state.get('steps', 0)} steps, {run_tokens()} tokens)"],
            **step("needs_attention")}


def after_critic(state):
    if over_budget(state):
        return "needs_attention"
    return "writer" if state["critique"]["send_back"] else "compliance"


def after_compliance(state):
    if over_budget(state):
        return "needs_attention"
    return "preview" if state["compliance_verdict"]["passed"] else END


def after_approval(state):
    return {"approve": "submit", "edit": "apply_edit"}.get(state["approval"].get("action"), END)


def build(checkpointer=None, store=None):
    g = StateGraph(GigBidState)
    for name, fn in [("load_job", load_job), ("analyst", analyst), ("risk_assessor", risk_assessor),
                     ("fit_matcher", fit_matcher), ("decide", decide), ("pricing", pricing), ("writer", writer),
                     ("verifier", verifier), ("critic", critic), ("compliance", compliance),
                     ("preview", preview), ("approval", approval), ("apply_edit", apply_edit),
                     ("submit", submit), ("needs_attention", needs_attention)]:
        g.add_node(name, fn)
    g.add_edge(START, "load_job")
    g.add_conditional_edges("load_job", fan_out, ["analyst", "risk_assessor", "fit_matcher", END])
    for n in ("analyst", "risk_assessor", "fit_matcher"):
        g.add_edge(n, "decide")
    g.add_conditional_edges("decide", after_decide, ["pricing", END])
    g.add_edge("pricing", "writer")
    g.add_conditional_edges("writer", after_writer, ["verifier", END])
    g.add_conditional_edges("verifier", lambda s: END if s.get("status") == "needs_attention" else "critic",
        ["critic", END])
    g.add_conditional_edges("critic", after_critic, ["writer", "compliance", "needs_attention"])
    g.add_conditional_edges("compliance", after_compliance, ["preview", "needs_attention", END])
    g.add_edge("preview", "approval")
    g.add_conditional_edges("approval", after_approval, ["submit", "apply_edit", END])
    g.add_edge("apply_edit", "compliance")  # an edited draft is re-checked, then re-approved
    g.add_edge("submit", END)
    g.add_edge("needs_attention", END)
    return g.compile(checkpointer=checkpointer, store=store)



